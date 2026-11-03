"""finding = actual - expected (SPEC §5 M3 差分, FR-10; ADR-023 #3, #4). Pure functions."""
from __future__ import annotations

from rlsentry.contracts.models import Finding, Op, Outcome, ProbeResult, Role, Severity, Target, finding_id
from rlsentry.contracts.probe import ReadObservation
from rlsentry.contracts.rules import RULES
from rlsentry.rules.severity import is_sensitive_column, read_rule, read_severity


def _finding(target: str, role: Role | None, op: Op | None, rule: str,
             probes: list[ProbeResult], severity: Severity | None = None) -> Finding:
    spec = RULES[rule]
    return Finding(id=finding_id(target, role, op, rule), rule=rule, evidence=spec.evidence,
                   severity=severity or spec.severity,
                   target=target, role=role, op=op, probes=probes)


def read_findings(target: Target, obs: ReadObservation, cell: ProbeResult) -> list[Finding]:
    """Why: turn one read cell plus its permitted-row count into findings; DENIED/NOT_TESTED give none."""
    out: list[Finding] = []
    probes = [cell]
    if cell.outcome is Outcome.ALLOWED:
        rule = read_rule(target.kind, cell.role)
        out.append(_finding(target.name, cell.role, Op.SELECT, rule, probes,
                            read_severity(rule, target.columns)))
    elif cell.outcome is Outcome.INCONCLUSIVE:
        rule = "NO_OWNER_COLUMN" if obs.expected.is_review else "INCONCLUSIVE_CELL"
        out.append(_finding(target.name, cell.role, Op.SELECT, rule, probes))
    p = obs.permitted
    if p is not None and p.status in (200, 206) and p.total is not None:
        if p.total < p.queried:
            out.append(_finding(target.name, cell.role, Op.SELECT, "EXPECTED_ACCESS_DENIED", probes))
        if (cell.role is Role.ANON and p.total > 0
                and any(is_sensitive_column(c) for c in target.columns)):
            out.append(_finding(target.name, cell.role, Op.SELECT, "SENSITIVE_COLUMN_PUBLIC", probes))
    return out


def target_findings(target: Target) -> list[Finding]:
    """INFERRED_TARGET for bundle-only targets, so an unconfirmed target is never silent."""
    if target.confidence == "inferred":
        return [_finding(target.name, None, None, "INFERRED_TARGET", [])]
    return []
