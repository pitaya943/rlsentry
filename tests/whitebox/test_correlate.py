"""whitebox.correlate (SPEC §5 M4 第 3 點與解讀; ADR-032): pure correlation of probe findings and
splinter lints. The MS4 focus: a SECURITY DEFINER object is a vulnerability only when the probe
obtained protected rows through it; otherwise it is a Configuration warning, never confirmed."""
from __future__ import annotations

from rlsentry.contracts.models import Evidence, Finding, Op, Role, finding_id
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.whitebox import Lint
from rlsentry.whitebox.correlate import correlate


def fnd(target: str | None, rule: str, role: Role | None = Role.ANON, op: Op | None = Op.SELECT,
        evidence: Evidence | None = None) -> Finding:
    spec = RULES[rule]
    return Finding(id=finding_id(target, role, op, rule), rule=rule,
                   evidence=evidence or spec.evidence, severity=spec.severity,
                   target=target, role=role, op=op)


def lint(name: str, obj: str | None, cat: str = "SECURITY", schema: str | None = "public") -> Lint:
    return Lint(name=name, level="ERROR", categories=[cat], object_schema=schema, object_name=obj)


def by_rule(fs: list[Finding], rule: str) -> list[Finding]:
    return [f for f in fs if f.rule == rule]


def test_lint_and_probe_on_same_target_is_confirmed() -> None:
    f = fnd("customers", "ANON_READ_OWNER_SCOPED")
    out = correlate([f], [lint("rls_disabled_in_public", "customers")])
    assert len(out) == 1
    assert out[0].correlation == "confirmed" and out[0].lint == "rls_disabled_in_public"
    assert out[0].evidence is Evidence.CONFIRMED and out[0].id == f.id


def test_probe_without_lint_is_probe_only_and_not_a_splinter_bug() -> None:
    f = fnd("notes", "CROSS_TENANT_READ", role=Role.USER_B)
    out = correlate([f], [lint("rls_disabled_in_public", "other_table")])
    assert out[0].correlation == "probe_only" and out[0].lint is None
    # the lint on the unrelated object becomes a lint-only warning, never confirmed
    extra = out[1:]
    assert [(x.rule, x.target, x.correlation) for x in extra] == [("LINT_ONLY", "other_table", "lint_only")]
    assert extra[0].evidence is Evidence.CONFIG_WARNING and not RULES["LINT_ONLY"].vulnerability


def test_security_definer_without_data_is_only_a_configuration_warning() -> None:
    # L07 ping_definer: executable SECURITY DEFINER, probe could not get protected rows
    inconclusive = fnd("ping_definer", "INCONCLUSIVE_CELL")
    lints = [lint("anon_security_definer_function_executable", "ping_definer"),
             lint("authenticated_security_definer_function_executable", "ping_definer")]
    out = correlate([inconclusive], lints)
    assert out[0] == inconclusive                       # non-proven finding untouched
    sd = by_rule(out, "SECURITY_DEFINER_EXECUTABLE")
    assert sorted((x.role.value if x.role else "") for x in sd) == ["", "anon"]
    for x in sd:
        assert x.evidence is Evidence.CONFIG_WARNING and x.op is Op.SELECT
        assert x.correlation == "lint_only" and x.target == "ping_definer"
        assert x.id == finding_id("ping_definer", x.role, Op.SELECT, "SECURITY_DEFINER_EXECUTABLE")
    assert not any(x.evidence is Evidence.CONFIRMED for x in out)
    assert by_rule(out, "LINT_ONLY") == []


def test_security_definer_with_data_keeps_confirmed_and_gets_no_warning() -> None:
    # L07 get_all_accounts: probe obtained other users' rows through the RPC
    f = fnd("get_all_accounts", "SECURITY_DEFINER_RPC_DATA")
    lints = [lint("authenticated_security_definer_function_executable", "get_all_accounts"),
             lint("anon_security_definer_function_executable", "get_all_accounts")]
    out = correlate([f], lints)
    assert len(out) == 1
    assert out[0].correlation == "confirmed"
    assert out[0].lint == ("anon_security_definer_function_executable,"
                           "authenticated_security_definer_function_executable")


def test_non_security_and_foreign_schema_lints_are_ignored() -> None:
    f = fnd("todos", "CROSS_TENANT_READ", role=Role.USER_A)
    lints = [lint("auth_rls_initplan", "todos", cat="PERFORMANCE"),
             lint("rls_disabled_in_public", "todos", schema="private"),
             lint("extension_in_public", None)]
    out = correlate([f], lints)
    assert out == [f.model_copy(update={"correlation": "probe_only"})]


def test_lint_only_is_one_finding_per_object_with_all_names() -> None:
    lints = [lint("rls_enabled_no_policy", "audit_log"), lint("policy_exists_rls_disabled", "audit_log"),
             lint("rls_enabled_no_policy", "audit_log")]
    out = correlate([], lints)
    assert len(out) == 1
    x = out[0]
    assert (x.rule, x.target, x.role, x.op) == ("LINT_ONLY", "audit_log", None, None)
    assert x.lint == "policy_exists_rls_disabled,rls_enabled_no_policy"
    assert x.severity is RULES["LINT_ONLY"].severity


def test_unproven_findings_never_count_as_probe_evidence() -> None:
    # a suspected or non-vulnerability finding on the linted object does not make it confirmed
    warn = fnd("public_profiles", "SENSITIVE_COLUMN_PUBLIC")
    out = correlate([warn], [lint("rls_policy_always_true", "public_profiles")])
    assert out[0] == warn
    assert [(x.rule, x.correlation) for x in out[1:]] == [("LINT_ONLY", "lint_only")]


def test_inputs_not_mutated_and_new_findings_sorted() -> None:
    f = fnd("b_table", "ANON_WRITE", op=Op.INSERT)
    before = f.model_dump()
    lints = [lint("rls_disabled_in_public", "z_table"), lint("security_definer_view", "a_view"),
             lint("anon_security_definer_function_executable", "m_fn")]
    out = correlate([f], lints)
    assert f.model_dump() == before
    assert out[0].correlation == "probe_only"
    assert [(x.target, x.rule) for x in out[1:]] == [
        ("a_view", "LINT_ONLY"), ("m_fn", "SECURITY_DEFINER_EXECUTABLE"), ("z_table", "LINT_ONLY")]


def test_no_duplicate_ids_when_a_warning_already_exists() -> None:
    existing = fnd("ping_definer", "SECURITY_DEFINER_EXECUTABLE")
    out = correlate([existing], [lint("anon_security_definer_function_executable", "ping_definer")])
    assert [x.id for x in out].count(existing.id) == 1


def test_custom_db_schemas() -> None:
    f = fnd("t", "ANON_READ_OWNER_SCOPED")
    out = correlate([f], [lint("rls_disabled_in_public", "t", schema="api")], db_schemas=("api",))
    assert out[0].correlation == "confirmed"
