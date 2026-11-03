"""labctl.query() is read-only and labctl.execute() is the only write path (ADR-022 #3, ADR-023 #7).
Contract: rlsentry/contracts/lab.py. Needs Docker."""
import httpx
import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import row_pk
from rlsentry.contracts.lab import POSTGREST_ROLES, LabInfo

B_ROW = row_pk("C03", 9)
INSERT_B = (f"insert into public.announcements (id, owner_id) values ('{B_ROW}', "
            "'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')")


@pytest.mark.safety
def test_query_refuses_writes(lab_info: LabInfo) -> None:
    labctl.apply("C03")
    with pytest.raises(RuntimeError):
        labctl.query(INSERT_B)
    assert labctl.query("select count(*) from public.announcements") == [("0",)]


@pytest.mark.safety
def test_execute_is_one_transaction(lab_info: LabInfo) -> None:
    labctl.apply("C03")
    with pytest.raises(RuntimeError):
        labctl.execute(INSERT_B + "; select 1 / 0;")
    assert labctl.query("select count(*) from public.announcements") == [("0",)]
    labctl.execute(INSERT_B)
    assert labctl.query("select count(*) from public.announcements") == [("1",)]
    labctl.apply("C03")
    assert labctl.query("select count(*) from public.announcements") == [("0",)]


def anon_sees(info: LabInfo) -> int:
    r = httpx.get(f"{info.api_url}/rest/v1/todos", params={"select": "id"},
                  headers={"apikey": info.anon_key, "Authorization": f"Bearer {info.anon_key}"})
    assert r.status_code == 200
    return len(r.json())


@pytest.mark.safety
def test_execute_change_is_served_at_once_and_apply_restores(lab_info: LabInfo) -> None:
    labctl.apply("C01")
    assert anon_sees(lab_info) == 0
    labctl.execute("alter table public.todos disable row level security;")
    assert anon_sees(lab_info) == 2
    labctl.apply("C01")
    assert anon_sees(lab_info) == 0


@pytest.mark.safety
def test_openapi_fetch_logs_no_write(lab_info: LabInfo) -> None:
    """ADR-024: PostgREST's OpenAPI query has 'TRUNCATE' inside a string literal; not a write.
    A real write right after it must still be found (string stripping must not hide writes)."""
    labctl.apply("L04")
    h = {"apikey": lab_info.anon_key, "Authorization": f"Bearer {lab_info.anon_key}"}
    marker = labctl.db_log_marker()
    assert httpx.get(f"{lab_info.api_url}/rest/v1/", headers=h).status_code == 200
    assert [w for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES] == []
    marker = labctl.db_log_marker()
    r = httpx.patch(f"{lab_info.api_url}/rest/v1/notes", headers={**h, "Prefer": "return=minimal"},
                    params={"id": f"eq.{row_pk('L04', 1)}"}, json={"body": "it's TRUNCATE 'quoted'"})
    assert r.status_code in (200, 204)
    assert [w.command for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES] == ["UPDATE"]
