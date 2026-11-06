"""report/enrich.py: M5 adds title, repro, references and fix SQL, then sorts (SPEC §5 M5; ADR-044)."""
from __future__ import annotations

from rlsentry.contracts.models import Evidence, Op, PolicyRow, Role
from rlsentry.contracts.policy import RoleScopes, RowScope, ScanConfig, TablePolicy
from rlsentry.contracts.report import REFERENCES
from rlsentry.contracts.rules import RULES
from rlsentry.report.enrich import enrich, sort_findings
from tests.report.helpers import JWT, finding, report

CONFIG = ScanConfig(target="http://app.test", tables={"notes": TablePolicy(
    owner_column="owner_id", select=RoleScopes(anon=RowScope.DENY, user=RowScope.OWN_ROWS_ONLY))})


def test_sorted_by_evidence_then_severity() -> None:
    out = enrich(report(), CONFIG).findings
    assert [(f.evidence, f.rule) for f in out] == [
        (Evidence.CONFIRMED, "SECRET_KEY_IN_BUNDLE"),       # critical
        (Evidence.CONFIRMED, "CROSS_TENANT_READ"),          # medium
        (Evidence.SUSPECTED, "INCONCLUSIVE_CELL"),
        (Evidence.CONFIG_WARNING, "SECURITY_DEFINER_EXECUTABLE")]


def test_sort_tie_breakers_are_deterministic() -> None:
    fs = [finding("CROSS_TENANT_READ", "b", Role.USER_A, Op.SELECT), finding("CROSS_TENANT_READ", "a", Role.USER_B, Op.SELECT),
          finding("CROSS_TENANT_READ", "a", Role.USER_A, Op.SELECT)]
    assert [(f.target, f.role) for f in sort_findings(fs)] == [("a", Role.USER_A), ("a", Role.USER_B), ("b", Role.USER_A)]


def test_fields_added_and_nothing_else_changed() -> None:
    rep = report()
    out = {f.id: f for f in enrich(rep, CONFIG).findings}
    for f in rep.findings:
        g = out[f.id]
        assert (g.rule, g.evidence, g.severity, g.correlation, g.probes) == (f.rule, f.evidence, f.severity,
                                                                              f.correlation, f.probes)
        assert g.title == RULES[f.rule].description
        assert g.references == list(REFERENCES.get(f.rule, ()))
    cross = next(f for f in out.values() if f.rule == "CROSS_TENANT_READ")
    assert cross.repro is not None and cross.repro.startswith("curl -sS -X GET")
    assert JWT not in cross.repro and "****" in cross.repro
    assert cross.fix_sql is not None and 'USING (auth.uid() = "owner_id")' in cross.fix_sql
    key = next(f for f in out.values() if f.rule == "SECRET_KEY_IN_BUNDLE")
    assert key.repro is None and key.fix_sql is not None
    rpc = next(f for f in out.values() if f.rule == "SECURITY_DEFINER_EXECUTABLE")
    assert rpc.fix_sql is not None and 'ALTER FUNCTION "public"."ping" SECURITY INVOKER;' in rpc.fix_sql
    assert next(f for f in out.values() if f.rule == "INCONCLUSIVE_CELL").fix_sql is None


def test_policies_of_the_first_db_schema_feed_the_drop_lines() -> None:
    pols = [PolicyRow(schema="public", table="notes", name="notes_select", command="SELECT",
                      roles=["authenticated"], permissive=True),
            PolicyRow(schema="other", table="notes", name="elsewhere", command="SELECT",
                      roles=["authenticated"], permissive=True)]
    cross = next(f for f in enrich(report(policies=pols), CONFIG).findings if f.rule == "CROSS_TENANT_READ")
    assert cross.fix_sql is not None
    assert 'DROP POLICY "notes_select" ON "public"."notes";' in cross.fix_sql and "elsewhere" not in cross.fix_sql


def test_input_report_is_not_mutated() -> None:
    rep = report()
    before = rep.model_dump_json()
    enrich(rep, CONFIG)
    assert rep.model_dump_json() == before
