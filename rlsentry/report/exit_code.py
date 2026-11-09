"""report/exit_code.py: the CI exit code from fail_on (FR-13; ADR-044)."""
from __future__ import annotations

from rlsentry.contracts.models import SEVERITY_RANK, Profile, ScanReport
from rlsentry.contracts.policy import FailOn
from rlsentry.contracts.report import EVIDENCE_RANK, EXIT_CLEANUP, EXIT_FINDINGS, EXIT_OK


def exit_code(report: ScanReport, fail_on: FailOn) -> int:
    """Map a report to a process exit code.

    Why only ci: SPEC §2 gives dev/audit no failure threshold, so a human-run scan never
    breaks a pipeline. A leftover canary (CLEANUP_FAILED) fails ci with its own code.
    """
    if report.profile is not Profile.CI:
        return EXIT_OK
    need_ev = EVIDENCE_RANK[fail_on.evidence]
    need_sev = SEVERITY_RANK[fail_on.severity]
    for f in report.findings:
        if EVIDENCE_RANK[f.evidence] >= need_ev and SEVERITY_RANK[f.severity] >= need_sev:
            return EXIT_FINDINGS
    if any(f.rule == "CLEANUP_FAILED" for f in report.findings):
        return EXIT_CLEANUP
    return EXIT_OK
