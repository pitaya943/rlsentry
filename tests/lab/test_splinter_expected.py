"""Ground truth `splinter_expected` matches the pinned splinter on the real lab (SPEC §8: splinter
「必須實測，不可預設」; ADR-033 #4, ADR-035). Needs Docker.

If this fails after a splinter upgrade or a scenario change, re-measure and update the
expected.yaml values with an ADR; never edit the value to make the test pass without measuring."""
from __future__ import annotations

import pytest

from lab._shared import labctl
from rlsentry.bench.score import splinter_status
from rlsentry.contracts.ground_truth import SCENARIO_IDS
from rlsentry.contracts.lab import LabInfo
from rlsentry.whitebox.splinter import run_splinter
from tests.lab.oracle import load_gt

REPORTED = {"L01", "L03", "L05", "L06", "L07", "L09"}


def test_ground_truth_is_measured_not_default() -> None:
    for sid in SCENARIO_IDS:
        gt = load_gt(sid)
        assert gt.splinter_expected != "measure", sid
        assert (gt.splinter_expected == "reported") == (sid in REPORTED), sid


@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_measured_equals_expected(lab_info: LabInfo, sid: str) -> None:
    labctl.apply(sid)
    assert splinter_status(load_gt(sid), run_splinter(lab_info.db_url)) == load_gt(sid).splinter_expected
