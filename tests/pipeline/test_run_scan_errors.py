"""MS6 audit (ADR-047): a crash after seeding still cleans up; the CLI reports a crash with its own
exit code and without secrets; correlate never touches key findings."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import rlsentry.pipeline as pl
from rlsentry import cli
from rlsentry.contracts.models import Profile
from rlsentry.contracts.report import EXIT_ERROR
from rlsentry.contracts.whitebox import Lint
from rlsentry.whitebox.correlate import correlate
from tests.pipeline.fake_supabase import FakeSupabase, notes_table
from tests.pipeline.helpers import cfg, scan
from tests.report.helpers import finding


def test_crash_in_probe_still_deletes_the_seeded_canaries(monkeypatch: pytest.MonkeyPatch) -> None:
    table = notes_table()
    fake = FakeSupabase(tables={"notes": table})

    async def boom(*a: Any, **k: Any) -> Any:
        assert len(table.rows) == 4                    # seeding happened first
        raise RuntimeError("probe crashed")
    monkeypatch.setattr(pl, "probe", boom)
    with pytest.raises(RuntimeError):
        scan(fake, cfg(profile=Profile.DEV))
    assert len(table.rows) == 2 and "DELETE" in fake.methods()


def test_cli_crash_has_its_own_exit_code_and_no_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_scan(config: Any, **kw: Any) -> Any:
        raise httpx.ConnectError("could not reach postgresql://u:secretpw@db/x")
    monkeypatch.setattr(cli, "run_scan", run_scan)
    conf = tmp_path / "rlsentry.yaml"
    conf.write_text("target: http://app.test\nauthorized: true\n", "utf-8")
    res = CliRunner().invoke(cli.app, ["scan", "--config", str(conf), "--out", str(tmp_path / "o")])
    assert res.exit_code == EXIT_ERROR
    assert "scan failed: ConnectError" in res.output and "secretpw" not in res.output


def test_typer_never_prints_locals() -> None:
    assert cli.app.pretty_exceptions_show_locals is False


def test_key_findings_are_never_correlated() -> None:
    key = finding("SECRET_KEY_IN_BUNDLE", "jwt:service_role")
    lint = Lint(name="rls_disabled_in_public", level="ERROR", categories=["SECURITY"], object_schema="public",
                object_name="jwt:service_role")
    out = correlate([key], [lint])
    assert out[0].correlation is None and out[0].rule == "SECRET_KEY_IN_BUNDLE"
