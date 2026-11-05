"""bench.score.aggregate (SPEC §9 formulas; ADR-033): sums over scored DEV results only."""
from __future__ import annotations

from typing import Any

from rlsentry.bench.score import aggregate
from rlsentry.contracts.ground_truth import CaseResult, ScenarioResult
from rlsentry.contracts.models import Profile


def res(sid: str, verdicts: list[Any], *, profile: Profile = Profile.DEV, scored: bool = True,
        unmatched: int = 0, cells: tuple[int, int, int] = (0, 0, 0), safe: tuple[int, int] = (0, 0),
        probe_only: list[str] | None = None) -> ScenarioResult:
    return ScenarioResult(
        scenario=sid, profile=profile, scored=scored, runtime_s=1.0,
        cases=[CaseResult(case_id=f"{sid}-X{i}", verdict=v) for i, v in enumerate(verdicts)],
        unmatched_findings=[f"u{i}" for i in range(unmatched)],
        cells_total=cells[0], cells_tested=cells[1], cells_inconclusive=cells[2],
        safe_denied_total=safe[0], safe_denied_decided=safe[1], probe_only=probe_only or [])


def test_formulas_and_raw_counts() -> None:
    results = [
        res("L04", ["tp", "tp", "tn", "fp"], unmatched=1, cells=(4, 4, 0), safe=(2, 2), probe_only=["L04-X0"]),
        res("L01", ["tp", "fn", "tn", "inconclusive_ok"], cells=(6, 5, 1), safe=(2, 1)),
        res("L02", ["tp", "tn"], cells=(2, 2, 0), safe=(1, 1), probe_only=["L02-X0"]),
    ]
    r = aggregate(results, {"5": 3.2})
    assert (r.tp, r.fn, r.fp, r.tn, r.fp_safe) == (4, 1, 1, 3, 1)
    assert r.recall == 4 / 5 and r.precision == 4 / 5 and r.fpr == 1 / 4
    assert r.coverage == 11 / 12 and r.inconclusive_ratio == 1 / 12
    assert r.safe_decided_ratio == 4 / 5
    assert r.probe_only == {"L04": ["L04-X0"], "L02": ["L02-X0"]}
    assert r.runtime == {"5": 3.2} and [s.scenario for s in r.scenarios] == ["L04", "L01", "L02"]


def test_audit_and_p2_results_are_listed_but_not_counted() -> None:
    results = [
        res("L04", ["tp", "tn"], cells=(2, 2, 0), safe=(1, 1)),
        res("L04", ["fn", "fp", "fp"], profile=Profile.AUDIT, unmatched=5, cells=(9, 1, 1), safe=(4, 0),
            probe_only=["L04-X9"]),
        res("L11", ["fn", "fp"], scored=False, unmatched=3, cells=(3, 0, 0)),
    ]
    r = aggregate(results, {})
    assert (r.tp, r.fn, r.fp, r.tn, r.fp_safe) == (1, 0, 0, 1, 0)
    assert r.coverage == 1.0 and r.probe_only == {}
    assert len(r.scenarios) == 3


def test_zero_denominators_are_zero_not_nan() -> None:
    r = aggregate([res("C03", ["inconclusive_ok"])], {})
    assert (r.recall, r.precision, r.fpr, r.coverage, r.inconclusive_ratio, r.safe_decided_ratio) == \
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert r.model_dump_json()           # serialisable (no NaN)
