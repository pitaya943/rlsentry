"""Write-probe HTTP shapes over a real SafeClient + MockTransport (SPEC §5 M3 writes; ADR-029).
Contract: contracts/probe.py (seed_known_rows, send_write, read_back, after_filter,
cleanup_seeded). The real SafeClient means audit would raise WriteRefused before any send."""
import json

import httpx
import pytest

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Op, Profile, Role, Target
from rlsentry.contracts.probe import (
    CANARY_PREFIX,
    SeededRow,
    Sessions,
    WriteAttempt,
    WritePlan,
)
from rlsentry.probe.cleanup import cleanup_seeded
from rlsentry.probe.seed import seed_known_rows
from rlsentry.probe.write import after_filter, read_back, seed_work_row, send_write
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: fake_jwt(A), Role.USER_B: fake_jwt(B)},
                user_ids={Role.USER_A: A, Role.USER_B: B})


def tgt() -> Target:
    return Target(name="customers", kind="table", columns=["id", "owner_id", "name"],
                  primary_key=["id"], discovered_by="openapi", confidence="confirmed")


def created(r: httpx.Request) -> httpx.Response:
    return httpx.Response(201, headers={"Content-Range": "*/1"})


# --- seed_known_rows -----------------------------------------------------------------------

def test_seed_posts_one_owned_canary_per_user() -> None:
    rec = Recorder(created)
    rows, notes = run(lambda c: seed_known_rows(c, URL, ANON, tgt(), "owner_id", None, "name", SESS),
                      rec, Profile.DEV)
    assert notes == [] and len(rows) == 2 and {r.owner for r in rows} == {Role.USER_A, Role.USER_B}
    for req in rec.requests:
        assert req.method == "POST" and req.url.path == "/rest/v1/customers"
        assert req.headers["prefer"] == "return=minimal"
        body = json.loads(req.content)
        assert body["owner_id"] in (A, B) and body["name"].startswith(CANARY_PREFIX)
    # each user used its own token
    owners = {json.loads(r.content)["owner_id"]: r.headers["authorization"] for r in rec.requests}
    assert owners[A] == f"Bearer {SESS.tokens[Role.USER_A]}"


def test_seed_public_column_makes_public_and_private_rows() -> None:
    rec = Recorder(created)
    rows, _ = run(lambda c: seed_known_rows(c, URL, ANON, tgt(), "owner_id", "is_public", "name", SESS),
                  rec, Profile.DEV)
    assert {r.public for r in rows} == {True, False}


def test_seed_without_owner_column_sends_nothing() -> None:
    rec = Recorder(created)
    rows, notes = run(lambda c: seed_known_rows(c, URL, ANON, tgt(), None, None, "name", SESS), rec, Profile.DEV)
    assert rows == [] and rec.requests == [] and notes


def test_seed_non_2xx_adds_note_not_row() -> None:
    rec = Recorder(lambda r: httpx.Response(403, json={"code": "42501"}))
    rows, notes = run(lambda c: seed_known_rows(c, URL, ANON, tgt(), "owner_id", None, "name", SESS), rec, Profile.DEV)
    assert rows == [] and any("403" in n for n in notes)


# --- seed_work_row -------------------------------------------------------------------------

def test_seed_work_row_creates_one_fresh_owned_canary() -> None:
    rec = Recorder(created)
    row = run(lambda c: seed_work_row(c, URL, ANON, tgt(), Role.USER_B, "name", "owner_id", SESS),
              rec, Profile.DEV)
    (req,) = rec.requests
    assert req.method == "POST" and req.headers["prefer"] == "return=minimal"
    assert req.headers["authorization"] == f"Bearer {SESS.tokens[Role.USER_B]}"
    body = json.loads(req.content)
    assert body["owner_id"] == B and body["name"].startswith(CANARY_PREFIX)
    assert row is not None and row.owner is Role.USER_B and row.pk == body["id"]


def test_seed_work_row_none_on_refusal() -> None:
    rec = Recorder(lambda r: httpx.Response(403, json={"code": "42501"}))
    row = run(lambda c: seed_work_row(c, URL, ANON, tgt(), Role.USER_B, "name", "owner_id", SESS),
              rec, Profile.DEV)
    assert row is None


# --- send_write ----------------------------------------------------------------------------

def insert_plan() -> WritePlan:
    return WritePlan(op=Op.INSERT, actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A, new_owner=Role.USER_A)


def work(owner: Role = Role.USER_B, pk: str = "wrk") -> SeededRow:
    return SeededRow(target="customers", pk=pk, owner=owner, marker="rlsentry_canary_w", text_column="name")


def test_send_insert_posts_canary_owned_by_new_owner() -> None:
    rec = Recorder(created)
    att = run(lambda c: send_write(c, URL, ANON, tgt(), insert_plan(), None, "owner_id", SESS), rec, Profile.DEV)
    (req,) = rec.requests
    assert req.method == "POST" and req.headers["prefer"] == "return=minimal"
    body = json.loads(req.content)
    assert body["owner_id"] == A and body["id"] == att.new_pk and att.status == 201


def test_send_update_value_patches_work_row_text_column_with_marker() -> None:
    plan = WritePlan(op=Op.UPDATE, actor=Role.USER_A, rule="CROSS_TENANT_WRITE", reader=Role.USER_B,
                     work_owner=Role.USER_B, text_column="name")
    rec = Recorder(created)
    att = run(lambda c: send_write(c, URL, ANON, tgt(), plan, work(), "owner_id", SESS), rec, Profile.DEV)
    (req,) = rec.requests
    assert req.method == "PATCH" and dict(req.url.params)["id"] == "eq.wrk"
    assert req.headers["authorization"] == f"Bearer {SESS.tokens[Role.USER_A]}"  # the ACTOR writes
    assert json.loads(req.content)["name"] == att.new_value and att.new_value.startswith(CANARY_PREFIX)


def test_send_update_transfer_sets_owner_column() -> None:
    plan = WritePlan(op=Op.UPDATE, actor=Role.USER_A, rule="CROSS_TENANT_WRITE", reader=Role.USER_B,
                     work_owner=Role.USER_A, new_owner=Role.USER_B, transfer=True)
    rec = Recorder(created)
    run(lambda c: send_write(c, URL, ANON, tgt(), plan, work(Role.USER_A), "owner_id", SESS), rec, Profile.DEV)
    assert json.loads(rec.requests[0].content)["owner_id"] == B


def test_send_delete_filters_on_work_pk() -> None:
    plan = WritePlan(op=Op.DELETE, actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A, work_owner=Role.USER_A)
    rec = Recorder(created)
    run(lambda c: send_write(c, URL, ANON, tgt(), plan, work(Role.USER_A, "dpk"), "owner_id", SESS), rec, Profile.DEV)
    assert rec.requests[0].method == "DELETE" and dict(rec.requests[0].url.params)["id"] == "eq.dpk"


def test_audit_refuses_every_write() -> None:
    plan = insert_plan()
    with pytest.raises(WriteRefused):
        run(lambda c: send_write(c, URL, ANON, tgt(), plan, None, "owner_id", SESS), Recorder(created), Profile.AUDIT)


# --- after_filter --------------------------------------------------------------------------

def test_after_filter_per_op() -> None:
    ins = WritePlan(op=Op.INSERT, actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A, new_owner=Role.USER_A)
    att = WriteAttempt(status=201, curl="c", new_pk="np1")
    assert after_filter(ins, att, None, "id", "owner_id", {Role.USER_A: A}) == {"id": "eq.np1"}

    dele = WritePlan(op=Op.DELETE, actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A, work_owner=Role.USER_A)
    assert after_filter(dele, WriteAttempt(status=200, curl="c"), work(Role.USER_A, "dpk"),
                        "id", "owner_id", {}) == {"id": "eq.dpk"}

    upd = WritePlan(op=Op.UPDATE, actor=Role.USER_A, rule="CROSS_TENANT_WRITE", reader=Role.USER_B,
                    work_owner=Role.USER_B, text_column="name")
    assert after_filter(upd, WriteAttempt(status=200, curl="c", new_value="rlsentry_canary_z"),
                        work(Role.USER_B, "wpk"), "id", "owner_id", {}) == {"id": "eq.wpk", "name": "eq.rlsentry_canary_z"}

    tr = WritePlan(op=Op.UPDATE, actor=Role.USER_A, rule="CROSS_TENANT_WRITE", reader=Role.USER_B,
                   work_owner=Role.USER_A, new_owner=Role.USER_B, transfer=True)
    assert after_filter(tr, WriteAttempt(status=200, curl="c"), work(Role.USER_A, "tpk"), "id", "owner_id",
                        {Role.USER_B: B}) == {"id": "eq.tpk", "owner_id": f"eq.{B}"}


# --- read_back -----------------------------------------------------------------------------

@pytest.mark.parametrize("cr,status,present", [("*/1", 200, True), ("*/0", 200, False),
                                               ("*/2", 206, True), (None, 200, None), ("*/*", 200, None),
                                               (None, 403, None)])
def test_read_back_present_from_count(cr: str | None, status: int, present: bool | None) -> None:
    rec = Recorder(lambda r: httpx.Response(status, headers={"Content-Range": cr} if cr else {}))
    rb = run(lambda c: read_back(c, URL, ANON, tgt(), fake_jwt(A), {"id": "eq.sA"}), rec, Profile.DEV)
    (req,) = rec.requests
    assert req.method == "HEAD" and req.headers["prefer"] == "count=exact"
    assert dict(req.url.params) == {"select": "id", "id": "eq.sA"} and rb.present is present


# --- cleanup_seeded ------------------------------------------------------------------------

def test_cleanup_deletes_each_row_as_its_owner_and_reports_leftovers() -> None:
    rows = [SeededRow(target="customers", pk="p1", owner=Role.USER_A, marker="m"),
            SeededRow(target="customers", pk="p2", owner=Role.USER_B, marker="m")]

    def handler(r: httpx.Request) -> httpx.Response:
        if r.method == "DELETE":
            return httpx.Response(200)
        # HEAD confirm: p1 gone (*/0), p2 still present (*/1) → p2 is a leftover.
        present = "1" if "p2" in str(r.url) else "0"
        return httpx.Response(200, headers={"Content-Range": f"*/{present}"})

    rec = Recorder(handler)
    left = run(lambda c: cleanup_seeded(c, URL, ANON, tgt(), rows, SESS), rec, Profile.DEV)
    assert [r.pk for r in left] == ["p2"]
    deletes = [r for r in rec.requests if r.method == "DELETE"]
    assert {dict(d.url.params)["id"] for d in deletes} == {"eq.p1", "eq.p2"}
    owner_tokens = {dict(d.url.params)["id"]: d.headers["authorization"] for d in deletes}
    assert owner_tokens["eq.p1"] == f"Bearer {SESS.tokens[Role.USER_A]}"
