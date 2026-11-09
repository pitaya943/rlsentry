"""ADR-019 (T-077): PostgREST writes must be visible in the DB log. Needs Docker."""
import httpx
import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import POSTGREST_ROLES, LabInfo


@pytest.mark.safety
def test_postgrest_writes_are_attributed_and_reads_are_not(lab_info: LabInfo) -> None:
    """ADR-019: PostgREST wraps writes in a CTE that log_statement = mod never logs. A write
    attempt (even one RLS filters to 0 rows) must appear as a PostgREST-role write; a read must
    not appear at all."""
    labctl.apply("L04")
    h = {"apikey": lab_info.anon_key, "Authorization": f"Bearer {lab_info.anon_key}"}
    marker = labctl.db_log_marker()
    r = httpx.get(f"{lab_info.api_url}/rest/v1/notes", headers=h, params={"select": "id"})
    assert r.status_code == 200
    assert [w for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES] == []
    marker = labctl.db_log_marker()
    r = httpx.patch(f"{lab_info.api_url}/rest/v1/notes", headers={**h, "Prefer": "return=minimal"},
                    params={"id": "eq.5ce01004-0000-4000-8000-000000000001"}, json={"body": "x"})
    assert r.status_code in (200, 204)
    writes = [w for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES]
    assert [w.command for w in writes] == ["UPDATE"]
