"""`python -m rlsentry.bench` entry point on one scenario (SPEC §8 執行方式; ADR-033). Needs Docker."""
from __future__ import annotations

from pathlib import Path

import pytest

from rlsentry.bench.__main__ import main
from rlsentry.contracts.ground_truth import BenchReport
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile


def test_single_scenario_json(lab_info: LabInfo, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "sub" / "bench.json"
    assert main(["--scenario", "C01", "--json", str(out)]) == 0
    rep = BenchReport.model_validate_json(out.read_text("utf-8"))
    assert [(s.scenario, s.profile) for s in rep.scenarios] == [("C01", Profile.DEV), ("C01", Profile.AUDIT)]
    dev, audit = rep.scenarios
    assert audit.db_writes == 0                       # NFR-01: audit never writes
    assert dev.db_writes is not None and dev.db_writes > 0   # dev write probes really ran
    assert dev.splinter == "not_reported"
    assert rep.fp == 0 and rep.fp_safe == 0 and rep.tn > 0 and rep.runtime == {}
    assert "recall" in capsys.readouterr().out


def test_unknown_scenario_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scenario", "L99"]) == 2
    assert "L99" in capsys.readouterr().err
