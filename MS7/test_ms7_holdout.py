"""MS7 holdout: same behaviour as the visible tests, different inputs (never shown to subagents)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from rlsentry.contracts.ground_truth import GroundTruth
from rlsentry.contracts.models import (
    Evidence,
    Finding,
    Op,
    PolicyRow,
    Profile,
    Role,
    Severity,
    finding_id,
)
from rlsentry.contracts.policy import FailOn
from rlsentry.report.exit_code import exit_code
from rlsentry.report.fix_sql import fix_sql, policy_name
from rlsentry.rules.severity import read_rule, read_severity
from rlsentry.whitebox.correlate import correlate
from tests.pipeline.fake_supabase import A, B, FakeSupabase, Table, notes_table
from tests.probe.test_escalation import esc
from tests.report.helpers import finding, report
from tests.report.test_fix_sql import ctx
from tests.whitebox.test_correlate import lint


def m3(role: Role, cols: list[str], target: str = "list_people") -> Finding:
    rule = read_rule("rpc", role)
    return Finding(id=finding_id(target, role, Op.SELECT, rule), rule=rule, evidence=Evidence.CONFIRMED,
                   severity=read_severity(rule, cols), target=target, role=role, op=Op.SELECT)


def test_default_relabel_keeps_critical_for_anon_with_sensitive_columns() -> None:
    lints = [lint("anon_security_definer_function_executable", "list_people"),
             lint("authenticated_security_definer_function_executable", "list_people")]
    out = correlate([m3(Role.ANON, ["id", "phone_number"]), m3(Role.USER_B, ["id", "phone_number"])], lints)
    assert [(f.rule, f.severity) for f in out[:2]] == [
        ("SECURITY_DEFINER_RPC_DATA", Severity.CRITICAL), ("SECURITY_DEFINER_RPC_DATA", Severity.MEDIUM)]


def test_fail_on_matches_without_m4_for_api_tokens() -> None:
    base = [m3(Role.ANON, ["id", "api_token"])]
    after = correlate(base, [lint("anon_security_definer_function_executable", "list_people")])
    for fo in (FailOn(), FailOn(severity=Severity.CRITICAL)):
        assert exit_code(report(findings=base, profile=Profile.CI), fo) == \
            exit_code(report(findings=after, profile=Profile.CI), fo)


def test_user_finding_without_the_authenticated_lint_is_not_relabelled() -> None:
    out = correlate([m3(Role.USER_A, ["id"])], [lint("anon_security_definer_function_executable", "list_people")])
    assert (out[0].rule, out[0].severity) == ("CROSS_TENANT_READ", Severity.MEDIUM)


def test_l07_ground_truth_severities() -> None:
    root = Path.cwd()
    gt = GroundTruth.model_validate(yaml.safe_load(
        next(root.glob("lab/L07_*/expected.yaml")).read_text("utf-8")))
    assert {c.id: c.severity for c in gt.vulnerable_cases} == {
        "L07-V1": Severity.HIGH, "L07-V2": Severity.MEDIUM, "L07-V3": Severity.MEDIUM}


def pol(name: str, cmd: str, roles: list[str]) -> PolicyRow:
    return PolicyRow(schema="public", table="docs", name=name, command=cmd, roles=roles, permissive=True)


def test_delete_fix_drops_only_policies_for_signed_in_users() -> None:
    sql = fix_sql(finding("CROSS_TENANT_WRITE", "docs", Role.USER_B, Op.DELETE),
                  ctx(policies=[pol("d_pub", "DELETE", ["public"]), pol("d_anon", "ALL", ["anon"]),
                                pol("d_editor", "DELETE", ["editor"])]))
    assert sql is not None
    assert [ln for ln in sql.splitlines() if ln.startswith("DROP")] == ['DROP POLICY "d_pub" ON "public"."docs";']


def test_policy_name_boundary_and_hash() -> None:
    t63 = "q" * (63 - len("rlsentry__delete_anon"))
    assert policy_name(t63, "delete", True) == f"rlsentry_{t63}_delete_anon"
    t64 = t63 + "q"
    n = policy_name(t64, "delete", True)
    full = f"rlsentry_{t64}_delete_anon"
    assert len(n.encode()) <= 63 and n == full.encode()[:54].decode() + "_" + hashlib.sha256(full.encode()).hexdigest()[:8]


def test_restore_puts_back_viewer_and_unreadable_writes_nothing() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)},
                        metadata_role={A: "viewer", B: "viewer"})
    findings, _ = esc(fake)
    assert len(findings) == 2 and fake.metadata_role == {A: "viewer", B: "viewer"}
    fake2 = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)}, get_user_status=403)
    findings2, notes2 = esc(fake2)
    assert findings2 == [] and not [r for r in fake2.requests if r.method == "PUT"]
    assert all("viewer" not in json.dumps(n) for n in notes2)
