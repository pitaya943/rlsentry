"""Pure benchmark scoring (SPEC §9; ADR-011, ADR-033). No I/O: the lab driver lives in run.py."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from rlsentry.contracts.bench import SCORING_PROFILE
from rlsentry.contracts.ground_truth import (
    BenchReport,
    Case,
    CaseKind,
    CaseResult,
    GroundTruth,
    ScenarioResult,
)
from rlsentry.contracts.models import (
    AccessMatrix,
    Evidence,
    Finding,
    Outcome,
    ProbeResult,
    Profile,
)
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.whitebox import Lint

_TESTED = (Outcome.ALLOWED, Outcome.DENIED, Outcome.INCONCLUSIVE)


def splinter_status(gt: GroundTruth, lints: list[Lint],
                    db_schemas: Sequence[str] = ("public",)) -> Literal["reported", "not_reported"]:
    """Whether splinter flags an object planted as vulnerable (ADR-033).

    Only ACCESS/STORAGE vulnerable targets count, so lints on unrelated objects cannot make a
    scenario look reported."""
    targets = {c.target for c in gt.vulnerable_cases if c.kind in (CaseKind.ACCESS, CaseKind.STORAGE)}
    for lint in lints:
        if "SECURITY" in lint.categories and lint.object_schema in db_schemas \
                and lint.object_name in targets:
            return "reported"
    return "not_reported"


def lint_labels(lints: list[Lint]) -> list[str]:
    """Sorted distinct '<name>:<object_name>' of SECURITY lints."""
    return sorted({f"{lint.name}:{lint.object_name or ''}" for lint in lints
                   if "SECURITY" in lint.categories})


def _proven(f: Finding) -> bool:
    return f.evidence is Evidence.CONFIRMED and RULES[f.rule].vulnerability


def _matches(f: Finding, c: Case) -> bool:
    if c.kind is CaseKind.KEY:
        return f.target == c.target and f.rule == c.rule
    return (f.target, f.op, f.role, f.rule) == (c.target, c.op, c.role, c.rule)


def _find_cell(matrix: AccessMatrix, c: Case) -> ProbeResult | None:
    for p in matrix.cells:
        if (p.target, p.role, p.op) == (c.target, c.role, c.op):
            return p
    return None


def score_scenario(gt: GroundTruth, profile: Profile, matrix: AccessMatrix,
                   findings: list[Finding], runtime_s: float, *,
                   lints: list[Lint] | None = None, db_writes: int | None = None,
                   db_schemas: Sequence[str] = ("public",)) -> ScenarioResult:
    """Score one scenario run against its ground truth (definitions in contracts/bench.py)."""
    def in_profile(cases: list[Case]) -> list[Case]:
        return [c for c in cases if profile in c.profiles]

    vulns, safes = in_profile(gt.vulnerable_cases), in_profile(gt.safe_cases)
    incs, warns = in_profile(gt.inconclusive_cases), in_profile(gt.warning_cases)
    proven = [f for f in findings if _proven(f)]
    results: list[CaseResult] = []
    probe_only: list[str] = []

    for c in vulns:
        hits = [f for f in proven if _matches(f, c)]
        if hits:
            results.append(CaseResult(case_id=c.id, verdict="tp"))
            if hits[0].correlation == "probe_only":
                probe_only.append(c.id)
        else:
            if c.kind is CaseKind.KEY:
                detail = "no finding"
            else:
                found = _find_cell(matrix, c)
                detail = f"{found.outcome.value}: {found.reason}" if found else "no cell"
            results.append(CaseResult(case_id=c.id, verdict="fn", detail=detail))

    unmatched = sorted(f.id for f in proven if not any(_matches(f, c) for c in vulns))

    for c in safes:
        hit = any((f.target, f.role, f.op) == (c.target, c.role, c.op) for f in proven)
        results.append(CaseResult(case_id=c.id, verdict="fp" if hit else "tn"))

    for c in incs:
        found = _find_cell(matrix, c)
        on_cell = any((f.target, f.role, f.op) == (c.target, c.role, c.op) for f in proven)
        ok = found is not None and found.outcome is Outcome.INCONCLUSIVE and not on_cell
        results.append(CaseResult(
            case_id=c.id, verdict="inconclusive_ok" if ok else "inconclusive_violation",
            detail="" if ok else (found.outcome.value if found else "no cell")))

    for c in warns:
        seen = any(f.rule == c.rule and f.evidence == c.evidence and f.target == c.target
                   and f.role == c.role and f.op == c.op for f in findings)
        results.append(CaseResult(case_id=c.id, verdict="warning_seen" if seen else "warning_missing"))

    outcomes: dict[tuple[str | None, str | None, str | None], Outcome | None] = {}
    for c in vulns + safes + incs:
        if c.kind is CaseKind.ACCESS:
            found = _find_cell(matrix, c)
            outcomes[(c.target, c.role.value if c.role else None, c.op.value if c.op else None)] = \
                found.outcome if found else None
    denied_safe = [c for c in safes if c.expect is Outcome.DENIED]
    decided = [c for c in denied_safe
               if (p := _find_cell(matrix, c)) is not None and p.outcome is Outcome.DENIED]

    res = ScenarioResult(
        scenario=gt.scenario, profile=profile, scored=gt.priority != "P2", cases=results,
        unmatched_findings=unmatched, runtime_s=runtime_s, cells_total=len(outcomes),
        cells_tested=sum(1 for o in outcomes.values() if o in _TESTED),
        cells_inconclusive=sum(1 for o in outcomes.values() if o is Outcome.INCONCLUSIVE),
        safe_denied_total=len(denied_safe), safe_denied_decided=len(decided),
        probe_only=sorted(probe_only), db_writes=db_writes)
    if lints is not None:
        status = splinter_status(gt, lints, db_schemas)
        res.splinter = status
        res.splinter_lints = lint_labels(lints)
        res.splinter_match = None if gt.splinter_expected == "measure" \
            else gt.splinter_expected == status
    return res


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def aggregate(results: Sequence[ScenarioResult], runtime: dict[str, float]) -> BenchReport:
    """Sum scored DEV results into the SPEC §9 metrics; zero denominators give 0.0 (ADR-033)."""
    counted = [r for r in results if r.scored and r.profile == SCORING_PROFILE]

    def count(verdict: str) -> int:
        return sum(1 for r in counted for c in r.cases if c.verdict == verdict)

    tp, fn, tn, fp_safe = count("tp"), count("fn"), count("tn"), count("fp")
    fp = sum(len(r.unmatched_findings) for r in counted)
    total = sum(r.cells_total for r in counted)
    return BenchReport(
        tp=tp, fp=fp, fn=fn, tn=tn, fp_safe=fp_safe,
        recall=_ratio(tp, tp + fn), precision=_ratio(tp, tp + fp), fpr=_ratio(fp_safe, fp_safe + tn),
        coverage=_ratio(sum(r.cells_tested for r in counted), total),
        inconclusive_ratio=_ratio(sum(r.cells_inconclusive for r in counted), total),
        safe_decided_ratio=_ratio(sum(r.safe_denied_decided for r in counted),
                                  sum(r.safe_denied_total for r in counted)),
        runtime=runtime, scenarios=list(results),
        probe_only={r.scenario: r.probe_only for r in counted if r.probe_only})
