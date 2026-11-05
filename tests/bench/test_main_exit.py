"""`python -m rlsentry.bench` exit codes (contracts/bench.py main): 1 iff an AUDIT run wrote to the
DB (NFR-01 breach), else 0 — metrics are reported, not enforced. No lab: run_bench is replaced."""
from __future__ import annotations

import pytest

import rlsentry.bench.__main__ as cli
from rlsentry.contracts.ground_truth import BenchReport, ScenarioResult
from rlsentry.contracts.models import Profile


def report(audit_writes: int) -> BenchReport:
    scen = [ScenarioResult(scenario="C01", profile=Profile.DEV, scored=True, runtime_s=0.1, db_writes=5),
            ScenarioResult(scenario="C01", profile=Profile.AUDIT, scored=True, runtime_s=0.1, db_writes=audit_writes)]
    return BenchReport(tp=0, fp=0, fn=0, tn=0, fp_safe=0, recall=0.0, precision=0.0, fpr=0.0, coverage=0.0,
                       inconclusive_ratio=0.0, safe_decided_ratio=0.0, runtime={}, scenarios=scen)


@pytest.mark.parametrize(("writes", "code"), [(0, 0), (1, 1)])
def test_exit_code_follows_audit_writes(monkeypatch: pytest.MonkeyPatch, writes: int, code: int) -> None:
    monkeypatch.setattr(cli, "run_bench", lambda *a, **k: report(writes))
    assert cli.main(["--scenario", "C01"]) == code
