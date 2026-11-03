"""probe/cross_tenant.py (FR-08 known rows). Contract: rlsentry/contracts/probe.py collect_known_rows."""
import httpx

from rlsentry.contracts.models import Role, Target
from rlsentry.contracts.probe import KNOWN_ROWS_LIMIT, KnownRow, Sessions
from rlsentry.probe.cross_tenant import collect_known_rows
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TA, TB = fake_jwt(A), fake_jwt(B)
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: TA, Role.USER_B: TB},
                user_ids={Role.USER_A: A, Role.USER_B: B})
ROWS = [  # (pk, owner id, public)
    ("r1", A, False), ("r2", A, True), ("r3", B, False),
]


def table(name: str = "notes", kind: str = "table", pk: list[str] | None = None) -> Target:
    return Target(name=name, kind=kind, columns=["id", "owner_id", "is_public"],
                  primary_key=["id"] if pk is None else pk, discovered_by="openapi", confidence="confirmed")


def fake(r: httpx.Request) -> httpx.Response:
    """Each user sees only own rows (owner-scoped RLS); honours eq / is filters."""
    who = {f"Bearer {TA}": A, f"Bearer {TB}": B}[r.headers["authorization"]]
    p = r.url.params
    rows = [x for x in ROWS if x[1] == who and p.get("owner_id") == f"eq.{x[1]}"]
    if "is_public" in p:
        rows = [x for x in rows if p["is_public"] == ("is.true" if x[2] else "is.false")]
    return httpx.Response(200, json=[{"id": x[0]} for x in rows])


def test_owner_only_one_get_per_user() -> None:
    rec = Recorder(fake)
    got = run(lambda c: collect_known_rows(c, URL, ANON, table(), "owner_id", None, SESS), rec)
    assert got.rows == [KnownRow(pk="r1", owner=Role.USER_A), KnownRow(pk="r2", owner=Role.USER_A),
                        KnownRow(pk="r3", owner=Role.USER_B)]
    assert [r.method for r in rec.requests] == ["GET", "GET"]
    a = rec.requests[0]
    assert a.url.path == "/rest/v1/notes" and a.headers["authorization"] == f"Bearer {TA}"
    assert a.headers["apikey"] == ANON
    assert dict(a.url.params) == {"select": "id", "owner_id": f"eq.{A}", "limit": str(KNOWN_ROWS_LIMIT)}


def test_public_column_splits_rows() -> None:
    rec = Recorder(fake)
    got = run(lambda c: collect_known_rows(c, URL, ANON, table(), "owner_id", "is_public", SESS), rec)
    assert sorted((r.pk, r.owner, r.public) for r in got.rows) == [
        ("r1", Role.USER_A, False), ("r2", Role.USER_A, True), ("r3", Role.USER_B, False)]
    assert len(rec.requests) == 4


def test_rpc_path() -> None:
    rec = Recorder(fake)
    run(lambda c: collect_known_rows(c, URL, ANON, table("get_all", "rpc"), "owner_id", None, SESS), rec)
    assert {r.url.path for r in rec.requests} == {"/rest/v1/rpc/get_all"}


def test_no_request_without_single_pk_or_owner_column() -> None:
    def check(tgt: Target, owner: str | None) -> None:
        rec = Recorder(fake)
        got = run(lambda c: collect_known_rows(c, URL, ANON, tgt, owner, None, SESS), rec)
        assert got.rows == [] and got.notes and rec.requests == []

    check(table(pk=[]), "owner_id")
    check(table(pk=["a", "b"]), "owner_id")
    check(table(), None)


def test_failed_user_adds_note_and_keeps_other() -> None:
    def h(r: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if r.headers["authorization"] == f"Bearer {TB}" else fake(r)
    got = run(lambda c: collect_known_rows(c, URL, ANON, table(), "owner_id", None, SESS), Recorder(h))
    assert [r.pk for r in got.rows] == ["r1", "r2"] and got.notes == ["user_b: HTTP 404"]


def test_odd_bodies_and_duplicates() -> None:
    body = [{"id": "x"}, {"id": None}, "junk", {"other": 1}, {"id": "x"}, {"id": 7}]
    got = run(lambda c: collect_known_rows(c, URL, ANON, table(), "owner_id", None, SESS),
              Recorder(lambda r: httpx.Response(200, json=body)))
    assert [(r.pk, r.owner) for r in got.rows] == [("x", Role.USER_A), ("7", Role.USER_A)]


def test_user_without_session_is_skipped() -> None:
    rec = Recorder(fake)
    s = Sessions(tokens={Role.ANON: ANON, Role.USER_A: TA}, user_ids={Role.USER_A: A},
                 missing={Role.USER_B: "RLS_B_PW is not set"})
    got = run(lambda c: collect_known_rows(c, URL, ANON, table(), "owner_id", None, s), rec)
    assert len(rec.requests) == 1 and {r.owner for r in got.rows} == {Role.USER_A}
