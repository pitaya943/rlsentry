"""report/exit_code.py: fail_on (FR-13). MS6 focus: CI fails only on Confirmed findings.

SPEC §2: only ci has a failure threshold; default fail_on = Confirmed and severity >= high.
"""
from __future__ import annotations

import pytest

from rlsentry.contracts.models import Evidence, Finding, Op, Profile, Role, Severity
from rlsentry.contracts.policy import FailOn
from rlsentry.contracts.report import EXIT_CLEANUP, EXIT_FINDINGS, EXIT_OK
from rlsentry.report.exit_code import exit_code
from tests.report.helpers import finding, report

pytestmark = pytest.mark.safety
DEFAULT = FailOn()


def one(evidence: Evidence, severity: Severity, rule: str = "CROSS_TENANT_WRITE") -> list[Finding]:
    return [finding(rule, "t", Role.USER_A, Op.UPDATE, severity=severity, evidence=evidence)]


@pytest.mark.parametrize("evidence, severity, code", [
    (Evidence.CONFIRMED, Severity.CRITICAL, EXIT_FINDINGS),
    (Evidence.CONFIRMED, Severity.HIGH, EXIT_FINDINGS),
    (Evidence.CONFIRMED, Severity.MEDIUM, EXIT_OK),
    (Evidence.SUSPECTED, Severity.CRITICAL, EXIT_OK),        # not confirmed → never fails CI
    (Evidence.CONFIG_WARNING, Severity.CRITICAL, EXIT_OK),
    (Evidence.SUSPECTED, Severity.REVIEW, EXIT_OK),
])
def test_ci_default_fails_only_on_confirmed_high_or_worse(evidence: Evidence, severity: Severity, code: int) -> None:
    assert exit_code(report(findings=one(evidence, severity), profile=Profile.CI), DEFAULT) == code


@pytest.mark.parametrize("profile", [Profile.DEV, Profile.AUDIT])
def test_dev_and_audit_never_fail(profile: Profile) -> None:
    rep = report(findings=one(Evidence.CONFIRMED, Severity.CRITICAL) + [finding("CLEANUP_FAILED", "t")], profile=profile)
    assert exit_code(rep, DEFAULT) == EXIT_OK


def test_custom_threshold_ranks_evidence_and_severity() -> None:
    lax = FailOn(evidence=Evidence.SUSPECTED, severity=Severity.MEDIUM)
    assert exit_code(report(findings=one(Evidence.SUSPECTED, Severity.MEDIUM), profile=Profile.CI), lax) == EXIT_FINDINGS
    assert exit_code(report(findings=one(Evidence.CONFIRMED, Severity.MEDIUM), profile=Profile.CI), lax) == EXIT_FINDINGS
    assert exit_code(report(findings=one(Evidence.CONFIG_WARNING, Severity.CRITICAL), profile=Profile.CI), lax) == EXIT_OK
    assert exit_code(report(findings=one(Evidence.SUSPECTED, Severity.LOW), profile=Profile.CI), lax) == EXIT_OK


def test_cleanup_failure_fails_ci_with_its_own_code() -> None:
    assert exit_code(report(findings=[finding("CLEANUP_FAILED", "t")], profile=Profile.CI), DEFAULT) == EXIT_CLEANUP
    both = one(Evidence.CONFIRMED, Severity.HIGH) + [finding("CLEANUP_FAILED", "t")]
    assert exit_code(report(findings=both, profile=Profile.CI), DEFAULT) == EXIT_FINDINGS


def test_no_findings_is_ok() -> None:
    assert exit_code(report(findings=[], profile=Profile.CI), DEFAULT) == EXIT_OK
