"""apply() storage handling (T-080; ADR-018 #5 #6). Needs Docker and lab/L11_*."""
import httpx

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from tests.lab.oracle import load_gt

FRESH = ("select count(*) from pg_policies where schemaname = 'storage' "
         "and tablename in ('objects', 'buckets')")


def test_storage_scenario_applies_twice_and_is_cleaned_up(lab_info: LabInfo) -> None:
    base = labctl.query(FRESH)            # whatever the current lab state, measure after a non-storage scenario
    labctl.apply("L04")
    clean = labctl.query(FRESH)
    labctl.apply("L11")
    labctl.apply("L11")                    # must not fail on objects the first apply created
    assert int(labctl.query(FRESH)[0][0]) > int(clean[0][0])
    labctl.apply("L04")
    assert labctl.query(FRESH) == clean
    assert labctl.query("select count(*) from storage.buckets") == [("0",)]
    assert base  # query works


def test_storage_files_are_uploaded(lab_info: LabInfo) -> None:
    labctl.apply("L11")
    gt = load_gt("L11")
    h = {"apikey": lab_info.service_role_key, "Authorization": f"Bearer {lab_info.service_role_key}"}
    for row in gt.rows.values():
        r = httpx.get(f"{lab_info.api_url}/storage/v1/object/{row.target}/{row.pk}", headers=h)
        assert r.status_code == 200, f"{row.target}/{row.pk}: HTTP {r.status_code}"
        assert len(r.content) > 0
