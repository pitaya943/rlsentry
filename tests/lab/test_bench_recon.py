"""Bench runs M1 recon on the served lab frontend (ADR-036; T-191). Needs Docker.

MS5: L08-V1 (service_role key in the bundle) becomes a TP, the anon key stays a TN, the key
finding is not counted as probe_only (it never goes through correlate), and M2 bundle inference
now uses what recon actually fetched (L12 is found only through the bundle).
"""
from __future__ import annotations

from rlsentry.bench.run import run_scenario
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile


def test_l08_key_is_scored(lab_info: LabInfo) -> None:
    for profile in (Profile.DEV, Profile.AUDIT):
        res = run_scenario("L08", profile, lab_info)
        verdicts = {c.case_id: c.verdict for c in res.cases}
        assert verdicts["L08-V1"] == "tp", (profile, verdicts)
        assert verdicts["L08-S1"] == "tn", (profile, verdicts)
        assert res.unmatched_findings == [] and res.probe_only == []
        if profile is Profile.AUDIT:
            assert res.db_writes == 0


def test_l12_bundle_inference_uses_recon_sources(lab_info: LabInfo) -> None:
    res = run_scenario("L12", Profile.DEV, lab_info)
    assert {c.case_id: c.verdict for c in res.cases}["L12-V1"] == "tp"
