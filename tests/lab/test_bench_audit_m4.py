"""Bench runs M4 in audit too, and an empty lint list is a measurement (ADR-033 補記). Needs Docker."""
from __future__ import annotations

from pathlib import Path

from rlsentry.bench.__main__ import main
from rlsentry.contracts.ground_truth import BenchReport
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile


def run(sid: str, tmp_path: Path) -> BenchReport:
    out = tmp_path / f"{sid}.json"
    assert main(["--scenario", sid, "--json", str(out)]) == 0
    return BenchReport.model_validate_json(out.read_text("utf-8"))


def test_l07_audit_sees_the_definer_warning(lab_info: LabInfo, tmp_path: Path) -> None:
    rep = run("L07", tmp_path)
    by = {s.profile: s for s in rep.scenarios}
    audit = by[Profile.AUDIT]
    assert {c.case_id: c.verdict for c in audit.cases}["L07-W1"] == "warning_seen"
    assert audit.splinter == by[Profile.DEV].splinter == "reported"
    assert audit.db_writes == 0


def test_l11_no_lints_is_not_reported(lab_info: LabInfo, tmp_path: Path) -> None:
    rep = run("L11", tmp_path)
    dev = next(s for s in rep.scenarios if s.profile is Profile.DEV)
    assert dev.splinter == "not_reported" and dev.splinter_lints == []
