"""Design premises the scanner and the lab tooling rely on, checked on the real lab (ADR-022 #3).

If Supabase/PostgREST/Postgres ever change one of these behaviours, the matching design decision
must be revisited: the test names the ADR. Needs Docker.
"""
from __future__ import annotations

import httpx
import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS, row_pk
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Role

pytestmark = pytest.mark.safety


def h(info: LabInfo, token: str | None = None, **extra: str) -> dict[str, str]:
    return {"apikey": info.anon_key, "Authorization": f"Bearer {token or info.anon_key}", **extra}


def login(info: LabInfo, role: Role) -> str:
    r = httpx.post(f"{info.api_url}/auth/v1/token", params={"grant_type": "password"}, headers=h(info),
                   json={"email": LAB_USERS[role]["email"], "password": labctl.lab_password(role)})
    assert r.status_code == 200
    return str(r.json()["access_token"])


def head_count(info: LabInfo, path: str, token: str | None, pks: list[str], col: str = "id") -> httpx.Response:
    return httpx.head(f"{info.api_url}/rest/v1/{path}", headers=h(info, token, Prefer="count=exact"),
                      params={"select": col, col: "in.(" + ",".join(pks) + ")"})


def test_cte_wrapped_write_is_not_logged_by_log_statement_mod(lab_info: LabInfo) -> None:
    """ADR-019: Postgres classifies `WITH … AS (INSERT …) SELECT` as SELECT, so log_statement =
    mod misses it; that is why authenticator logs everything and writes are found by keyword."""
    labctl.apply("C03")
    try:
        marker = labctl.db_log_marker()
        labctl.execute(f"with s as (insert into public.announcements (id, owner_id) values "
                       f"('{row_pk('C03', 8)}', '{LAB_USERS[Role.USER_A]['id']}') returning 1) select count(*) from s;")
        assert [w for w in labctl.db_writes_since(marker) if w.role == "postgres"] == []
        assert labctl.query("select count(*) from public.announcements") == [("1",)]
        marker = labctl.db_log_marker()
        labctl.execute(f"insert into public.announcements (id, owner_id) values "
                       f"('{row_pk('C03', 9)}', '{LAB_USERS[Role.USER_A]['id']}');")
        assert [w.command for w in labctl.db_writes_since(marker) if w.role == "postgres"] == ["INSERT"]
    finally:
        labctl.apply("C03")


def test_head_count_gives_total_without_body(lab_info: LabInfo) -> None:
    """FR-06 / ADR-023 #3: HEAD + Prefer: count=exact returns the total in Content-Range, no rows."""
    labctl.apply("L04")
    r = head_count(lab_info, "notes", login(lab_info, Role.USER_B), [row_pk("L04", 1), row_pk("L04", 2)])
    assert r.status_code in (200, 206) and r.content == b""
    assert r.headers["content-range"].split("/")[1] == "2"   # L04 leaks every row to any user


def test_rls_hidden_rows_look_exactly_like_an_empty_table(lab_info: LabInfo) -> None:
    """SPEC §5 M3 三態: count = 0 is not denied. A row hidden by RLS and a table with no rows give
    the same answer, so only a KNOWN existing row can turn 0 into "denied"."""
    labctl.apply("C01")
    a = login(lab_info, Role.USER_A)
    hidden = head_count(lab_info, "todos", a, [row_pk("C01", 2)])   # user_b's row, exists
    assert labctl.query(f"select count(*) from public.todos where id = '{row_pk('C01', 2)}'") == [("1",)]
    labctl.apply("C03")
    empty = head_count(lab_info, "announcements", login(lab_info, Role.USER_A), [row_pk("C03", 1)])
    assert (hidden.status_code, hidden.headers["content-range"]) == (empty.status_code, empty.headers["content-range"])
    assert hidden.headers["content-range"] == "*/0"


def test_openapi_cannot_tell_a_view_from_a_table(lab_info: LabInfo) -> None:
    """ADR-023 #1: same methods and the same <pk/> marker for L06's table and view."""
    labctl.apply("L06")
    doc = httpx.get(f"{lab_info.api_url}/rest/v1/", headers=h(lab_info)).json()
    assert sorted(doc["paths"]["/invoices"]) == sorted(doc["paths"]["/invoice_summary"])
    assert doc["definitions"]["invoices"]["properties"]["id"]["description"] == \
        doc["definitions"]["invoice_summary"]["properties"]["id"]["description"]


def test_rpc_results_accept_row_filters(lab_info: LabInfo) -> None:
    """ADR-023 #3: HEAD counts and owner filters work on set-returning RPCs, like on tables."""
    labctl.apply("L07")
    r = head_count(lab_info, "rpc/get_all_accounts", None, [row_pk("L07", 1)])
    assert r.status_code in (200, 206) and r.headers["content-range"].split("/")[1] == "1"


def test_restricted_openapi_answers_404(lab_info: LabInfo) -> None:
    """FR-05: L12's restricted OpenAPI is a 404 (PGRST126), which must trigger the bundle fallback."""
    labctl.apply("L12")
    r = httpx.get(f"{lab_info.api_url}/rest/v1/", headers=h(lab_info))
    assert r.status_code == 404 and r.json()["code"] == "PGRST126"


def test_bad_filter_value_is_an_error_not_an_empty_result(lab_info: LabInfo) -> None:
    """ADR-023 #3: a malformed key gives 400 without Content-Range, so it can never read as 0."""
    labctl.apply("C01")
    r = head_count(lab_info, "todos", None, ["not-a-uuid"])
    assert r.status_code == 400 and "content-range" not in r.headers
