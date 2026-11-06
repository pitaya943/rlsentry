"""MS6 approval note 1 (option B), ADR-049: M4's relabel never lowers a severity.

When correlate turns a proven read on a SECURITY DEFINER function into
SECURITY_DEFINER_RPC_DATA, the severity is max(the M3 severity, Medium). So supplying a DB
connection (M4) can never make `fail_on: high` pass where the scan without M4 failed:
anon + sensitive columns stays Critical, anon stays High, a user's cross-tenant read stays Medium.
The M3 severities below come from the real rule functions, not from hand-picked values.
"""
from __future__ import annotations

import pytest

from rlsentry.contracts import whitebox as wb_contract
from rlsentry.contracts.models import Evidence, Finding, Op, Profile, Role, Severity, finding_id
from rlsentry.contracts.policy import FailOn
from rlsentry.report.exit_code import exit_code
from rlsentry.rules.severity import read_rule, read_severity
from rlsentry.whitebox.correlate import correlate
from tests.report.helpers import report
from tests.whitebox.test_correlate import lint

ANON_LINT = "anon_security_definer_function_executable"
AUTH_LINT = "authenticated_security_definer_function_executable"
LINTS = [lint(ANON_LINT, "get_rows"), lint(AUTH_LINT, "get_rows")]
PLAIN = ["id", "owner_id", "balance"]
SENSITIVE = ["id", "owner_id", "contact_email"]


def m3(role: Role, columns: list[str]) -> Finding:
    """The finding M3 produces for a confirmed read through an RPC (ADR-039: rule by role)."""
    rule = read_rule("rpc", role)
    return Finding(id=finding_id("get_rows", role, Op.SELECT, rule), rule=rule,
                   evidence=Evidence.CONFIRMED, severity=read_severity(rule, columns),
                   target="get_rows", role=role, op=Op.SELECT)


CASES = [
    (Role.ANON, SENSITIVE, Severity.CRITICAL),
    (Role.ANON, PLAIN, Severity.HIGH),
    (Role.USER_A, PLAIN, Severity.MEDIUM),
    (Role.USER_B, SENSITIVE, Severity.MEDIUM),     # CROSS_TENANT_READ never escalates
]


@pytest.mark.parametrize("role, columns, want", CASES)
def test_relabel_keeps_the_higher_severity(role: Role, columns: list[str], want: Severity) -> None:
    before = m3(role, columns)
    assert before.severity is want                                   # M3 alone already says this
    [got] = [f for f in correlate([before], LINTS, keep_higher=True) if f.target == "get_rows"
             and f.rule == "SECURITY_DEFINER_RPC_DATA"]
    assert (got.severity, got.correlation, got.evidence) == (want, "confirmed", Evidence.CONFIRMED)
    assert got.id == finding_id("get_rows", role, Op.SELECT, "SECURITY_DEFINER_RPC_DATA")
    assert before.severity is want and before.rule != "SECURITY_DEFINER_RPC_DATA"   # not mutated


def test_spec_table_mode_is_always_medium() -> None:
    # keep_higher=False is the SPEC §5 M5 table read literally (the MS6 behaviour, option A)
    out = correlate([m3(Role.ANON, SENSITIVE), m3(Role.USER_A, PLAIN)], LINTS, keep_higher=False)
    assert [(f.rule, f.severity) for f in out[:2]] == [("SECURITY_DEFINER_RPC_DATA", Severity.MEDIUM)] * 2


@pytest.mark.parametrize("flag, want", [(True, Severity.HIGH), (False, Severity.MEDIUM)])
def test_default_reads_the_contract_flag_at_call_time(monkeypatch: pytest.MonkeyPatch, flag: bool,
                                                      want: Severity) -> None:
    monkeypatch.setattr(wb_contract, "RELABEL_KEEPS_HIGHER_SEVERITY", flag)
    [got] = correlate([m3(Role.ANON, PLAIN)], [lint(ANON_LINT, "get_rows")])
    assert (got.rule, got.severity) == ("SECURITY_DEFINER_RPC_DATA", want)


@pytest.mark.parametrize("role, columns, want", CASES)
def test_ci_fail_on_is_the_same_with_and_without_a_db_connection(role: Role, columns: list[str],
                                                                  want: Severity) -> None:
    without_m4 = [m3(role, columns)]
    with_m4 = correlate(without_m4, LINTS, keep_higher=True)
    for fail_on in (FailOn(), FailOn(severity=Severity.CRITICAL), FailOn(severity=Severity.MEDIUM)):
        a = exit_code(report(findings=without_m4, profile=Profile.CI), fail_on)
        b = exit_code(report(findings=with_m4, profile=Profile.CI), fail_on)
        assert a == b, f"{role.value} {want.value} fail_on={fail_on.severity.value}: {a} != {b}"


def test_only_the_severity_depends_on_the_flag() -> None:
    fs = [m3(Role.ANON, PLAIN), m3(Role.USER_A, PLAIN)]
    hi, lo = correlate(fs, LINTS, keep_higher=True), correlate(fs, LINTS, keep_higher=False)
    strip = [f.model_dump(exclude={"severity"}) for f in hi]
    assert strip == [f.model_dump(exclude={"severity"}) for f in lo]
