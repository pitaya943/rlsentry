"""cli.py: the Typer CLI (SPEC §2 用法, §4; FR-13, FR-15, FR-16; ADR-044).

Why thin: the scan itself lives in pipeline.run_scan (shared with the Python API and the
GitHub Action); the CLI only maps arguments, writes reports and turns errors into exit codes.
Passwords and keys are never accepted as arguments; everything printed is masked.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import ValidationError

from rlsentry.contracts.interfaces import AuthorizationRefused, WriteRefused
from rlsentry.contracts.models import Evidence, Profile, ScanReport
from rlsentry.contracts.pipeline import EndpointRefused, ScanSetupError
from rlsentry.contracts.policy import ConfigError, ScanConfig
from rlsentry.contracts.report import (
    DEFAULT_FORMATS,
    EXIT_ERROR,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    REPORT_FILE_STEM,
)
from rlsentry.pipeline import run_init, run_scan
from rlsentry.policy.load import load_config
from rlsentry.report.exit_code import exit_code
from rlsentry.report.html import render_html
from rlsentry.report.json import render_json
from rlsentry.report.sarif import render_sarif
from rlsentry.safety.mask import mask_text

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False, no_args_is_help=True,
                  help="RLSentry: verify Supabase authorization from an attacker's point of view.")

_FORMATS = ("json", "html", "sarif")
_LEVELS = ((Evidence.CONFIRMED, "Confirmed"), (Evidence.SUSPECTED, "Suspected"),
           (Evidence.CONFIG_WARNING, "Configuration warning"))


def _echo(text: str, err: bool = False) -> None:
    typer.echo(mask_text(text), err=err)


def _fail(message: str, code: int) -> typer.Exit:
    _echo(message, err=True)
    return typer.Exit(code)


def _read_config(path: Path, target: str | None) -> ScanConfig:
    """Load the config file; with no file, TARGET alone gives an all-defaults config."""
    try:
        if path.is_file():
            config = load_config(path.read_text("utf-8"))
            if target is not None and target.rstrip("/") != config.target.rstrip("/"):
                raise _fail("TARGET and config target differ", EXIT_USAGE)
            return config
        if target is None:
            raise _fail(f"config file not found: {path}; pass --config or a TARGET", EXIT_USAGE)
        return ScanConfig(target=target)
    except (ConfigError, ValidationError, OSError, UnicodeError) as e:
        kind = e.__class__.__name__
        msg = str(e) if isinstance(e, ConfigError) else f"cannot use config ({kind})"
        raise _fail(msg, EXIT_USAGE) from None


def _parse_formats(value: str | None, profile: Profile) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_FORMATS[profile]
    items = tuple(dict.fromkeys(s.strip() for s in value.split(",") if s.strip()))
    bad = [s for s in items if s not in _FORMATS]
    if bad or not items:
        raise _fail(f"unknown --format {bad or value!r}; use json,html,sarif", EXIT_USAGE)
    return items


def _summary(report: ScanReport) -> list[str]:
    lines: list[str] = []
    for ev, label in _LEVELS:
        counts = Counter(f.severity.value for f in report.findings if f.evidence is ev)
        detail = ", ".join(f"{n} {sev}" for sev, n in counts.items()) or "none"
        lines.append(f"{label}: {sum(counts.values())} ({detail})")
    for f in report.findings:
        if f.evidence is Evidence.CONFIRMED:
            parts = [f.severity.value.upper(), f.rule, f.target or "-",
                     f.role.value if f.role else "-", f.op.value if f.op else "-"]
            lines.append(" ".join(parts))
    return lines


@app.command()
def scan(
    target: Annotated[str | None, typer.Argument(help="Target URL (optional when the config names it).")] = None,
    config: Annotated[Path, typer.Option("--config", "-c", help="Config file.")] = Path("rlsentry.yaml"),
    profile: Annotated[Profile | None, typer.Option("--profile", help="dev, ci or audit (stricter wins).")] = None,
    i_own_this_target: Annotated[bool, typer.Option("--i-own-this-target", help="Confirm you are authorized to test the target.")] = False,
    supabase_url: Annotated[str | None, typer.Option("--supabase-url", help="Supabase API URL.")] = None,
    out: Annotated[Path, typer.Option("--out", help="Output directory.")] = Path("rlsentry-report"),
    fmt: Annotated[str | None, typer.Option("--format", help="Comma list: json,html,sarif.")] = None,
) -> None:
    """Scan a Supabase-backed app and write reports."""
    cfg = _read_config(config, target)
    try:
        report = asyncio.run(run_scan(cfg, cli_confirmed=i_own_this_target, cli_profile=profile,
                                      cli_supabase_url=supabase_url))
    except (AuthorizationRefused, EndpointRefused, WriteRefused) as e:
        raise _fail(str(e), EXIT_REFUSED) from None
    except (ConfigError, ScanSetupError) as e:
        raise _fail(str(e), EXIT_USAGE) from None
    except (httpx.HTTPError, OSError, RuntimeError) as e:
        raise _fail(f"scan failed: {type(e).__name__}", EXIT_ERROR) from None
    formats = _parse_formats(fmt, report.profile)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in formats:
        if name == "json":
            text = render_json(report)
        elif name == "html":
            text = render_html(report)
        else:
            text = render_sarif(report, str(config))
        path = out / f"{REPORT_FILE_STEM}.{name}"
        path.write_text(text, "utf-8")
        written.append(path)
    for line in _summary(report):
        _echo(line)
    for path in written:
        _echo(f"wrote {path}")
    raise typer.Exit(exit_code(report, cfg.fail_on))


@app.command()
def init(
    config: Annotated[Path, typer.Option("--config", "-c", help="Config file.")] = Path("rlsentry.yaml"),
    i_own_this_target: Annotated[bool, typer.Option("--i-own-this-target", help="Confirm you are authorized to test the target.")] = False,
    supabase_url: Annotated[str | None, typer.Option("--supabase-url", help="Supabase API URL.")] = None,
    out: Annotated[Path, typer.Option("--out", help="Draft file to write.")] = Path("rlsentry.draft.yaml"),
) -> None:
    """Write a draft policy file from the target's OpenAPI (GET requests only)."""
    cfg = _read_config(config, None)
    if out.exists():
        raise _fail(f"{out} already exists; refusing to overwrite", EXIT_USAGE)
    try:
        text = asyncio.run(run_init(cfg, cli_confirmed=i_own_this_target,
                                    cli_supabase_url=supabase_url))
    except (AuthorizationRefused, EndpointRefused, WriteRefused) as e:
        raise _fail(str(e), EXIT_REFUSED) from None
    except (ConfigError, ScanSetupError) as e:
        raise _fail(str(e), EXIT_USAGE) from None
    out.write_text(text, "utf-8")
    _echo(f"wrote {out}")
    raise typer.Exit(EXIT_OK)


def main() -> None:
    """Console-script entry point."""
    app()
