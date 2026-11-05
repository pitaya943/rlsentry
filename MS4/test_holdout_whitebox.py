"""MS4 holdout: correlation, scoring and typed seeding with DIFFERENT inputs than the visible
tests. Pure, no Docker. Contracts: rlsentry/contracts/whitebox.py, bench.py, probe.py (ADR-032–034)."""
from datetime import datetime

from rlsentry.bench.score import aggregate, score_scenario, splinter_status
from rlsentry.contracts.ground_truth import GroundTruth
from rlsentry.contracts.models import (
    AccessMatrix,
    Evidence,
    Finding,
    Op,
    Outcome,
    ProbeResult,
    Profile,
    Role,
    Target,
    finding_id,
)
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.whitebox import Lint
from rlsentry.discovery.openapi import parse_openapi
from rlsentry.probe.fill import fill_required
from rlsentry.whitebox.correlate import correlate

U1 = "11111111-1111-4111-8111-111111111111"


def f(target: str, role: Role | None, op: Op | None, rule: str, ev: Evidence | None = None) -> Finding:
    s = RULES[rule]
    return Finding(id=finding_id(target, role, op, rule), rule=rule, evidence=ev or s.evidence,
                   severity=s.severity, target=target, role=role, op=op)


def lint(name: str, obj: str, cat: str = "SECURITY", schema: str = "public") -> Lint:
    return Lint(name=name, level="WARN", categories=["EXTERNAL", cat], object_schema=schema, object_name=obj)


# --- correlate ---------------------------------------------------------------------------------

def test_definer_view_with_data_vs_definer_fn_without() -> None:
    view_hit = f("order_totals", Role.USER_B, Op.SELECT, "CROSS_TENANT_READ")
    out = correlate([view_hit], [lint("security_definer_view", "order_totals"),
                                 lint("authenticated_security_definer_function_executable", "bump_counter")])
    assert out[0].correlation == "confirmed" and out[0].lint == "security_definer_view"
    sd = [x for x in out if x.rule == "SECURITY_DEFINER_EXECUTABLE"]
    assert len(sd) == 1 and sd[0].role is None and sd[0].target == "bump_counter"
    assert sd[0].evidence is Evidence.CONFIG_WARNING
    assert all(x.evidence is not Evidence.CONFIRMED for x in out[1:])


def test_mixed_definer_and_other_lints_on_dataless_object() -> None:
    out = correlate([], [lint("anon_security_definer_function_executable", "fx"),
                         lint("function_search_path_mutable", "fx"), lint("rls_policy_always_true", "fx")])
    rules = sorted((x.rule, x.lint) for x in out)
    assert rules == [("LINT_ONLY", "function_search_path_mutable,rls_policy_always_true"),
                     ("SECURITY_DEFINER_EXECUTABLE", "anon_security_definer_function_executable")]


def test_write_finding_is_probe_only_and_order_kept() -> None:
    a = f("feedback", Role.ANON, Op.INSERT, "ANON_WRITE")
    b = f("feedback", Role.ANON, Op.SELECT, "INCONCLUSIVE_CELL")
    c = f("wallets", Role.USER_A, Op.UPDATE, "CROSS_TENANT_WRITE")
    out = correlate([a, b, c], [lint("rls_policy_always_true", "feedback", cat="PERFORMANCE")])
    assert [x.id for x in out] == [a.id, b.id, c.id]
    assert [x.correlation for x in out] == ["probe_only", None, "probe_only"]


# --- scoring -----------------------------------------------------------------------------------

def gt() -> GroundTruth:
    return GroundTruth.model_validate({
        "scenario": "L09", "title": "t", "plant": "p",
        "schema": {"wallets": {"kind": "table", "columns": ["id", "owner_id"], "primary_key": ["id"]}},
        "rows": {"w1": {"target": "wallets", "pk": "5ce01009-0000-4000-8000-000000000001", "owner": "user_a"}},
        "policy": ExpectedPolicy().model_dump(),
        "vulnerable_cases": [
            {"id": "L09-V1", "target": "wallets", "op": "insert", "role": "anon", "new_owner": "user_a",
             "expect": "allowed", "rule": "ANON_WRITE", "severity": "critical", "profiles": ["dev", "ci"]},
            {"id": "L09-V2", "target": "wallets", "op": "select", "role": "anon", "rows": ["w1"],
             "expect": "allowed", "rule": "ANON_READ_OWNER_SCOPED", "severity": "high"}],
        "safe_cases": [
            {"id": "L09-S1", "target": "wallets", "op": "select", "role": "user_b", "rows": ["w1"], "expect": "denied"},
            {"id": "L09-S2", "target": "wallets", "op": "delete", "role": "user_b", "rows": ["w1"],
             "expect": "denied", "profiles": ["dev", "ci"]}],
    })


def pr(target: str, role: Role, op: Op, o: Outcome) -> ProbeResult:
    return ProbeResult(target=target, role=role, op=op, outcome=o, known_rows_checked=1, reason="x",
                       evidence_curl="curl -I http://127.0.0.1:54321/rest/v1/wallets")


def test_score_dev_and_aggregate() -> None:
    m = AccessMatrix(cells=[pr("wallets", Role.ANON, Op.INSERT, Outcome.ALLOWED),
                            pr("wallets", Role.ANON, Op.SELECT, Outcome.INCONCLUSIVE),
                            pr("wallets", Role.USER_B, Op.SELECT, Outcome.DENIED),
                            pr("wallets", Role.USER_B, Op.DELETE, Outcome.ALLOWED)])
    ins = f("wallets", Role.ANON, Op.INSERT, "ANON_WRITE").model_copy(update={"correlation": "probe_only"})
    stray = f("wallets", Role.USER_B, Op.DELETE, "CROSS_TENANT_WRITE")
    r = score_scenario(gt(), Profile.DEV, m, [ins, stray], 2.0, db_writes=7)
    v = {c.case_id: c.verdict for c in r.cases}
    assert v == {"L09-V1": "tp", "L09-V2": "fn", "L09-S1": "tn", "L09-S2": "fp"}
    assert r.unmatched_findings == [stray.id] and r.probe_only == ["L09-V1"] and r.db_writes == 7
    assert (r.cells_total, r.cells_tested, r.cells_inconclusive) == (4, 4, 1)
    assert (r.safe_denied_total, r.safe_denied_decided) == (2, 1)
    audit = score_scenario(gt(), Profile.AUDIT, m, [], 1.0, db_writes=0)
    rep = aggregate([r, audit], {"5": 1.0, "20": 2.0})
    assert (rep.tp, rep.fn, rep.fp, rep.tn, rep.fp_safe) == (1, 1, 1, 1, 1)
    assert (rep.recall, rep.precision, rep.fpr) == (0.5, 0.5, 0.5)
    assert rep.coverage == 1.0 and rep.inconclusive_ratio == 0.25 and rep.safe_decided_ratio == 0.5
    assert rep.probe_only == {"L09": ["L09-V1"]} and len(rep.scenarios) == 2


def test_splinter_status_uses_vulnerable_targets_only() -> None:
    assert splinter_status(gt(), [lint("rls_policy_always_true", "wallets")]) == "reported"
    assert splinter_status(gt(), [lint("rls_policy_always_true", "wallets", cat="PERFORMANCE")]) == "not_reported"
    assert splinter_status(gt(), [lint("rls_policy_always_true", "other")]) == "not_reported"


# --- typed seeding -----------------------------------------------------------------------------

def test_openapi_types_and_fill() -> None:
    d = {"paths": {"/orders": {}}, "definitions": {"orders": {
        "required": ["ref", "user_ref", "qty", "placed_at", "paid"],
        "properties": {"ref": {"format": "uuid", "description": "<pk/>"}, "user_ref": {"format": "uuid"},
                       "qty": {"format": "smallint"}, "placed_at": {"format": "timestamp without time zone"},
                       "paid": {"format": "boolean"}, "memo": {"format": "character varying"}}}}}
    (t,) = parse_openapi(d)
    assert t.required == ["ref", "user_ref", "qty", "placed_at", "paid"] and t.column_formats["memo"] == "character varying"
    got = fill_required(t, U1, {"ref"})
    assert got is not None and list(got) == ["user_ref", "qty", "placed_at", "paid"]
    assert got["user_ref"] == U1 and got["qty"] == 0 and got["paid"] is False
    datetime.fromisoformat(got["placed_at"])
    t2 = Target(name="x", kind="table", required=["a"], column_formats={"a": "ARRAY"},
                discovered_by="openapi", confidence="confirmed")
    assert fill_required(t2, U1, set()) is None
