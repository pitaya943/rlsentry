"""SPEC §9 Profile 端到端: dev, ci and audit each run the full product path (run_scan) on the lab.

MS6 focus: audit cannot write (DB log, not the tool's claim); the report separates evidence
levels; CI fails only on Confirmed findings of severity high or worse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import rlsentry
from lab._shared import labctl
from rlsentry.cli import app
from rlsentry.contracts.lab import POSTGREST_ROLES, LabInfo
from rlsentry.contracts.models import Outcome, Profile
from rlsentry.contracts.policy import FailOn
from rlsentry.contracts.report import EXIT_FINDINGS, EXIT_OK
from rlsentry.pipeline import run_scan as pipeline_run_scan
from rlsentry.report.exit_code import exit_code
from rlsentry.report.html import render_html
from rlsentry.report.json import render_json
from rlsentry.report.sarif import render_sarif
from tests.e2e.conftest import lab_config, lab_env
from tests.e2e.helpers import Recording, gt, keys, proven, scan

pytestmark = pytest.mark.e2e_profiles


def test_python_api_is_the_pipeline() -> None:
    assert rlsentry.run_scan is pipeline_run_scan              # FR-16: one entry point


def test_dev_runs_every_module_and_confirms_the_l05_transfer(lab: LabInfo) -> None:
    labctl.apply("L05")
    with labctl.serve_frontend("L05") as url:
        rep = scan(lab_config(url, lab, gt("L05").policy, Profile.DEV), lab_env(lab))
    assert rep.modules == ["M1", "M2", "M3", "M4", "M5"] and rep.policies
    assert {("projects", "user_a", "CROSS_TENANT_WRITE"), ("projects", "user_b", "CROSS_TENANT_WRITE")} <= keys(proven(rep))
    assert keys(proven(rep)) <= {("projects", "user_a", "CROSS_TENANT_WRITE"), ("projects", "user_b", "CROSS_TENANT_WRITE")}
    assert exit_code(rep, FailOn()) == EXIT_OK                    # dev has no failure threshold
    for text in (render_json(rep), render_html(rep), render_sarif(rep)):
        assert lab.anon_key not in text and lab.db_url not in text


@pytest.mark.parametrize("sid, code", [("L05", EXIT_FINDINGS), ("L04", EXIT_OK), ("C01", EXIT_OK), ("L07", EXIT_OK)])
def test_ci_fails_only_on_confirmed_high(lab: LabInfo, sid: str, code: int) -> None:
    # L05 cross-tenant write = high → fail; L04 cross-tenant read and L07 definer RPC = medium,
    # plus warnings and inconclusive cells → pass (SPEC §5 M5 fail_on default)
    labctl.apply(sid)
    rep = scan(lab_config("http://127.0.0.1:1", lab, gt(sid).policy, Profile.CI), lab_env(lab))
    assert rep.modules == ["M2", "M3", "M4", "M5"] and rep.recon is None
    assert exit_code(rep, FailOn()) == code
    if sid in ("L04", "L07"):
        assert proven(rep)                                   # confirmed, but below the threshold


@pytest.mark.safety
def test_audit_never_writes_by_the_database_log(lab: LabInfo) -> None:
    labctl.apply("L05")
    marker = labctl.db_log_marker()
    rec = Recording()
    cfg = lab_config("http://127.0.0.1:1", lab, gt("L05").policy, Profile.DEV, with_db=False, authorized=False)
    with labctl.serve_frontend("L05") as url:
        rep = scan(cfg.model_copy(update={"target": url}), lab_env(lab), rec,
                   cli_profile=Profile.AUDIT, cli_confirmed=True)
    writes = [w for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES]
    assert writes == []
    assert rep.profile is Profile.AUDIT and rep.modules == ["M1", "M2", "M3", "M5"]
    assert rep.authorization.method == "cli_flag" and rep.authorization.confirmed_by == "e2e"
    assert {c.outcome for c in rep.matrix.cells if c.op.value != "select"} == {Outcome.NOT_TESTED}
    for r in rec.seen:
        assert r.method in ("GET", "HEAD") or (r.method, r.url.path) == ("POST", "/auth/v1/token")


def test_cli_ci_end_to_end(lab: LabInfo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    labctl.apply("L05")
    for k, v in lab_env(lab).items():
        monkeypatch.setenv(k, v)
    conf = tmp_path / "rlsentry.yaml"
    conf.write_text("\n".join([
        "target: http://127.0.0.1:1", "authorized: true", "profile: ci", "rate_limit_rps: 50",
        f"supabase_url: {lab.api_url}", "anon_key_env: E2E_ANON_KEY",
        "test_users:", "  - {name: user_a, email: a@test.dev, password_env: RLS_A_PW}",
        "  - {name: user_b, email: b@test.dev, password_env: RLS_B_PW}",
        "tables:", "  projects:", "    owner_column: owner_id",
        "    select: {anon: deny, user: own_rows_only}", "    update: {anon: deny, user: own_rows_only}",
    ]) + "\n", "utf-8")
    res = CliRunner().invoke(app, ["scan", "--config", str(conf), "--out", str(tmp_path / "out")])
    assert res.exit_code == EXIT_FINDINGS, res.output
    sarif = json.loads((tmp_path / "out" / "rlsentry-report.sarif").read_text("utf-8"))
    assert any(r["ruleId"] == "CROSS_TENANT_WRITE" and r["level"] == "error" for r in sarif["runs"][0]["results"])
    assert lab.anon_key not in res.output
