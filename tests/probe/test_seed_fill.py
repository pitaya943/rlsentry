"""seed_known_rows / seed_work_row / send_write carry fill_required values (ADR-034), over a real
SafeClient + MockTransport; an unfillable required column means no request at all."""
from __future__ import annotations

import json

import httpx

from rlsentry.contracts.models import Profile, Role, Target
from rlsentry.contracts.probe import CANARY_PREFIX, SEED_UNFILLABLE_REASON, Sessions, WritePlan
from rlsentry.probe.seed import seed_known_rows
from rlsentry.probe.write import seed_work_row, send_write
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: fake_jwt(A), Role.USER_B: fake_jwt(B)},
                user_ids={Role.USER_A: A, Role.USER_B: B})
FMT = {"id": "uuid", "owner_id": "uuid", "created_by": "uuid", "name": "text", "email": "text"}


def tgt(formats: dict[str, str] = FMT) -> Target:
    return Target(name="projects", kind="table", columns=list(formats), primary_key=["id"],
                  required=list(formats), column_formats=formats, discovered_by="openapi", confidence="confirmed")


def created(r: httpx.Request) -> httpx.Response:
    return httpx.Response(201)


def bodies(rec: Recorder) -> list[dict[str, object]]:
    return [json.loads(r.content) for r in rec.requests]


def test_seed_known_rows_fills_required_without_overriding() -> None:
    rec = Recorder(created)
    rows, notes = run(lambda c: seed_known_rows(c, URL, ANON, tgt(), "owner_id", None, "name", SESS), rec, Profile.DEV)
    assert notes == [] and len(rows) == 2
    for body in bodies(rec):
        assert body["created_by"] == body["owner_id"] and body["owner_id"] in (A, B)
        assert str(body["email"]).startswith(CANARY_PREFIX) and str(body["name"]).startswith(CANARY_PREFIX)
        assert body["id"] not in (A, B) and body["email"] != body["name"]


def test_seed_known_rows_unfillable_sends_nothing() -> None:
    rec = Recorder(created)
    bad = tgt({**FMT, "status": "public.state"})
    rows, notes = run(lambda c: seed_known_rows(c, URL, ANON, bad, "owner_id", None, "name", SESS), rec, Profile.DEV)
    assert rows == [] and rec.requests == []
    assert sorted(notes) == sorted(f"{r.value}: {SEED_UNFILLABLE_REASON}" for r in (Role.USER_A, Role.USER_B))


def test_seed_work_row_fills_and_refuses_unfillable() -> None:
    rec = Recorder(created)
    row = run(lambda c: seed_work_row(c, URL, ANON, tgt(), Role.USER_B, "name", "owner_id", SESS), rec, Profile.DEV)
    assert row is not None and bodies(rec)[0]["created_by"] == B
    rec2 = Recorder(created)
    none = run(lambda c: seed_work_row(c, URL, ANON, tgt({**FMT, "s": "public.state"}), Role.USER_B, "name",
                                       "owner_id", SESS), rec2, Profile.DEV)
    assert none is None and rec2.requests == []


def test_insert_probe_fills_with_new_owner_id() -> None:
    plan = WritePlan(op="insert", actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A, new_owner=Role.USER_A)
    rec = Recorder(created)
    att = run(lambda c: send_write(c, URL, ANON, tgt(), plan, None, "owner_id", SESS), rec, Profile.DEV)
    body = bodies(rec)[0]
    assert att.status == 201 and body["owner_id"] == A and body["created_by"] == A
    assert body["id"] == att.new_pk


def test_insert_probe_unfillable_is_unsent() -> None:
    plan = WritePlan(op="insert", actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A, new_owner=Role.USER_A)
    rec = Recorder(created)
    att = run(lambda c: send_write(c, URL, ANON, tgt({**FMT, "s": "public.state"}), plan, None, "owner_id", SESS),
              rec, Profile.DEV)
    assert rec.requests == [] and att.status is None and att.curl == ""
