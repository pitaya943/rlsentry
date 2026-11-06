"""MS4 approval note 5 (a)(b), ADR-039: correlate judges SECURITY DEFINER per (object, role).

(a) proof for one role never silences the SECURITY_DEFINER_EXECUTABLE warning of another role;
(b) only splinter can prove a function is SECURITY DEFINER, so M4 (not M3) turns a proven read
    on such a function into SECURITY_DEFINER_RPC_DATA; a function without that lint keeps M3's rule.
"""
from __future__ import annotations

from rlsentry.contracts.models import Evidence, Op, Role, Severity, finding_id
from rlsentry.whitebox.correlate import correlate
from tests.whitebox.test_correlate import by_rule, fnd, lint

ANON_LINT = "anon_security_definer_function_executable"
AUTH_LINT = "authenticated_security_definer_function_executable"


def test_anon_proof_does_not_silence_the_authenticated_warning() -> None:
    out = correlate([fnd("f", "ANON_READ_OWNER_SCOPED", role=Role.ANON)], [lint(ANON_LINT, "f"), lint(AUTH_LINT, "f")])
    warn = by_rule(out, "SECURITY_DEFINER_EXECUTABLE")
    assert [(w.role, w.lint, w.correlation) for w in warn] == [(None, AUTH_LINT, "lint_only")]
    assert warn[0].evidence is Evidence.CONFIG_WARNING
    assert warn[0].id == finding_id("f", None, Op.SELECT, "SECURITY_DEFINER_EXECUTABLE")


def test_user_proof_does_not_silence_the_anon_warning() -> None:
    out = correlate([fnd("f", "CROSS_TENANT_READ", role=Role.USER_B)], [lint(ANON_LINT, "f"), lint(AUTH_LINT, "f")])
    assert [(w.role, w.lint) for w in by_rule(out, "SECURITY_DEFINER_EXECUTABLE")] == [(Role.ANON, ANON_LINT)]


def test_every_role_proven_means_no_warning() -> None:
    fs = [fnd("f", "ANON_READ_OWNER_SCOPED", role=Role.ANON), fnd("f", "CROSS_TENANT_READ", role=Role.USER_A)]
    out = correlate(fs, [lint(ANON_LINT, "f"), lint(AUTH_LINT, "f")])
    assert by_rule(out, "SECURITY_DEFINER_EXECUTABLE") == [] and len(out) == 2


def test_proven_reads_on_a_definer_function_are_relabelled_by_m4() -> None:
    fs = [fnd("f", "ANON_READ_OWNER_SCOPED", role=Role.ANON), fnd("f", "CROSS_TENANT_READ", role=Role.USER_A)]
    out = correlate(fs, [lint(ANON_LINT, "f"), lint(AUTH_LINT, "f")])
    # ADR-049: the relabel keeps the higher severity (anon High, user Medium)
    for got, role, sev in zip(out, (Role.ANON, Role.USER_A), (Severity.HIGH, Severity.MEDIUM), strict=True):
        assert (got.rule, got.severity, got.correlation, got.role) == (
            "SECURITY_DEFINER_RPC_DATA", sev, "confirmed", role)
        assert got.id == finding_id("f", role, Op.SELECT, "SECURITY_DEFINER_RPC_DATA")
        assert got.lint == f"{ANON_LINT},{AUTH_LINT}"
    assert fs[0].rule == "ANON_READ_OWNER_SCOPED"                         # inputs not mutated


def test_relabel_needs_the_lint_for_that_role() -> None:
    # only the anon lint: a user's proven read stays CROSS_TENANT_READ (no proof for that role)
    out = correlate([fnd("f", "CROSS_TENANT_READ", role=Role.USER_A)], [lint(ANON_LINT, "f")])
    assert out[0].rule == "CROSS_TENANT_READ" and out[0].correlation == "confirmed"


def test_invoker_function_or_table_keeps_the_m3_rule() -> None:
    out = correlate([fnd("list_notes", "ANON_READ_OWNER_SCOPED", role=Role.ANON),
                     fnd("customers", "ANON_READ_OWNER_SCOPED", role=Role.ANON)],
                    [lint("rls_disabled_in_public", "customers")])
    assert [(f.target, f.rule, f.correlation) for f in out] == [
        ("list_notes", "ANON_READ_OWNER_SCOPED", "probe_only"),
        ("customers", "ANON_READ_OWNER_SCOPED", "confirmed")]


def test_writes_are_never_relabelled() -> None:
    out = correlate([fnd("f", "ANON_WRITE", role=Role.ANON, op=Op.INSERT)], [lint(ANON_LINT, "f")])
    assert out[0].rule == "ANON_WRITE"
    # the anon role is not proven *for reading the function*, but it is proven on the object:
    assert by_rule(out, "SECURITY_DEFINER_EXECUTABLE") == []


def test_lint_only_still_needs_no_proof_at_all_on_the_object() -> None:
    out = correlate([fnd("v", "ANON_READ_OWNER_SCOPED", role=Role.ANON)],
                    [lint("security_definer_view", "v"), lint(AUTH_LINT, "v")])
    assert by_rule(out, "LINT_ONLY") == []
    assert [(w.role, w.lint) for w in by_rule(out, "SECURITY_DEFINER_EXECUTABLE")] == [(None, AUTH_LINT)]
