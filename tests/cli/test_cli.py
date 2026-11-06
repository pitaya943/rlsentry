"""cli.py: the Typer CLI (SPEC §2 用法, §4; FR-13, FR-15, FR-16; ADR-044).

run_scan / run_init are replaced by fakes here (the scan itself is covered by
tests/pipeline and the lab e2e tests); these tests pin what the CLI adds: argument mapping,
config handling, output files per profile, terminal summary, exit codes and masking.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from rlsentry import cli
from rlsentry.contracts.interfaces import AuthorizationRefused
from rlsentry.contracts.models import Evidence, Op, Profile, Role, ScanReport, Severity
from rlsentry.contracts.pipeline import EndpointRefused, ScanSetupError
from rlsentry.contracts.report import EXIT_FINDINGS, EXIT_OK, EXIT_REFUSED, EXIT_USAGE
from tests.report.helpers import JWT, finding, report

RUNNER = CliRunner()
CONF = "target: http://app.test\nauthorized: true\nprofile: ci\nsupabase_url: http://127.0.0.1:54321\n"


def fake_scan(monkeypatch: pytest.MonkeyPatch, rep: ScanReport | Exception) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def run_scan(config: Any, **kw: Any) -> ScanReport:
        calls.append({"config": config, **kw})
        if isinstance(rep, Exception):
            raise rep
        return rep
    monkeypatch.setattr(cli, "run_scan", run_scan)
    return calls


def invoke(tmp: Path, *args: str, conf: str | None = CONF) -> Any:
    if conf is not None:
        (tmp / "rlsentry.yaml").write_text(conf, "utf-8")
    return RUNNER.invoke(cli.app, ["scan", "--config", str(tmp / "rlsentry.yaml"), "--out", str(tmp / "out"), *args])


def high(profile: Profile = Profile.CI) -> ScanReport:
    return report(profile=profile, findings=[
        finding("CROSS_TENANT_WRITE", "projects", Role.USER_A, Op.UPDATE),
        finding("INCONCLUSIVE_CELL", "notes", Role.USER_A, Op.SELECT)])


def test_ci_writes_json_and_sarif_and_fails_on_confirmed_high(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, high())
    res = invoke(tmp_path)
    assert res.exit_code == EXIT_FINDINGS, res.output
    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == ["rlsentry-report.json", "rlsentry-report.sarif"]
    assert json.loads((out / "rlsentry-report.sarif").read_text("utf-8"))["version"] == "2.1.0"
    assert "CROSS_TENANT_WRITE" in res.output and "projects" in res.output


def test_ci_with_only_medium_or_unconfirmed_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, report(profile=Profile.CI, findings=[
        finding("CROSS_TENANT_READ", "notes", Role.USER_B, Op.SELECT),
        finding("CROSS_TENANT_WRITE", "p", Role.USER_A, Op.UPDATE, evidence=Evidence.SUSPECTED, severity=Severity.HIGH)]))
    assert invoke(tmp_path).exit_code == EXIT_OK


def test_dev_default_is_html_and_never_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, high(Profile.DEV))
    res = invoke(tmp_path, conf=CONF.replace("profile: ci", "profile: dev"))
    assert res.exit_code == EXIT_OK
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["rlsentry-report.html"]


def test_audit_default_is_html_and_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, high(Profile.AUDIT))
    assert invoke(tmp_path).exit_code == EXIT_OK
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["rlsentry-report.html", "rlsentry-report.json"]


def test_explicit_formats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, high(Profile.DEV))
    invoke(tmp_path, "--format", "json,html,sarif")
    assert len(list((tmp_path / "out").iterdir())) == 3


def test_flags_reach_run_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_scan(monkeypatch, high(Profile.AUDIT))
    invoke(tmp_path, "--profile", "audit", "--i-own-this-target", "--supabase-url", "http://127.0.0.1:54321")
    [c] = calls
    assert c["cli_profile"] is Profile.AUDIT and c["cli_confirmed"] is True
    assert c["cli_supabase_url"] == "http://127.0.0.1:54321" and c["config"].target == "http://app.test"


def test_defaults_do_not_confirm_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_scan(monkeypatch, high())
    invoke(tmp_path)
    assert calls[0].get("cli_confirmed", False) is False and calls[0].get("cli_profile") is None
    assert calls[0].get("cli_supabase_url") is None


def test_target_argument_without_a_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_scan(monkeypatch, high(Profile.AUDIT))
    res = invoke(tmp_path, "https://my-app.example.test", "--i-own-this-target", conf=None)
    assert res.exit_code == EXIT_OK and calls[0]["config"].target == "https://my-app.example.test"


def test_target_argument_must_match_the_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_scan(monkeypatch, high())
    res = invoke(tmp_path, "https://other.example.test")
    assert res.exit_code == EXIT_USAGE and calls == []


def test_missing_config_and_no_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_scan(monkeypatch, high())
    assert invoke(tmp_path, conf=None).exit_code == EXIT_USAGE and calls == []


def test_bad_config_is_usage_error_without_echoing_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, high())
    res = invoke(tmp_path, conf=f"target: http://app.test\nanon_key: {JWT}\n  bad: [\n")
    assert res.exit_code == EXIT_USAGE and JWT not in res.output


@pytest.mark.parametrize("exc, code", [
    (AuthorizationRefused("not authorized: pass --i-own-this-target"), EXIT_REFUSED),
    (EndpointRefused(f"the frontend bundle points at http://evil.test/?k={JWT}"), EXIT_REFUSED),
    (ScanSetupError("ci needs anon_key_env"), EXIT_USAGE),
])
def test_refusals_and_setup_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception, code: int) -> None:
    fake_scan(monkeypatch, exc)
    res = invoke(tmp_path)
    assert res.exit_code == code and JWT not in res.output
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_output_never_contains_a_full_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scan(monkeypatch, report(profile=Profile.CI))
    res = invoke(tmp_path, "--format", "json,html,sarif")
    assert JWT not in res.output
    for p in (tmp_path / "out").iterdir():
        assert JWT not in p.read_text("utf-8")


def test_init_writes_a_draft_and_refuses_to_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    async def run_init(config: Any, **kw: Any) -> str:
        seen.append(kw)
        return "target: http://app.test\ntables: {}\n"
    monkeypatch.setattr(cli, "run_init", run_init)
    (tmp_path / "rlsentry.yaml").write_text(CONF, "utf-8")
    args = ["init", "--config", str(tmp_path / "rlsentry.yaml"), "--out", str(tmp_path / "draft.yaml"),
            "--i-own-this-target"]
    assert RUNNER.invoke(cli.app, args).exit_code == EXIT_OK
    assert (tmp_path / "draft.yaml").read_text("utf-8") == "target: http://app.test\ntables: {}\n"
    assert seen[0]["cli_confirmed"] is True
    assert RUNNER.invoke(cli.app, args).exit_code == EXIT_USAGE


def test_help_lists_both_commands() -> None:
    out = RUNNER.invoke(cli.app, ["--help"]).output
    assert "scan" in out and "init" in out
