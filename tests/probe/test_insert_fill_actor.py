"""send_write INSERT: other required uuid columns carry the ATTACKER's id (ADR-034 補記 2; MS4 audit
P1-1), the owner column the victim's. Filling never changes how the end state is read back (by pk),
so this can only remove false 'denied' results, never add false 'allowed' ones."""
from __future__ import annotations

import json

import httpx

from rlsentry.contracts.models import Op, Profile, Role, Target
from rlsentry.contracts.probe import Sessions, WritePlan
from rlsentry.probe.write import send_write
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: fake_jwt(A), Role.USER_B: fake_jwt(B)},
                user_ids={Role.USER_A: A, Role.USER_B: B})
FMT = {"id": "uuid", "owner_id": "uuid", "created_by": "uuid", "name": "text"}


def tgt() -> Target:
    return Target(name="projects", kind="table", columns=list(FMT), primary_key=["id"], required=list(FMT),
                  column_formats=FMT, discovered_by="openapi", confidence="confirmed")


def body(actor: Role, new_owner: Role, rule: str) -> dict[str, object]:
    plan = WritePlan(op=Op.INSERT, actor=actor, rule=rule, reader=new_owner, new_owner=new_owner, text_column="name")
    rec = Recorder(lambda r: httpx.Response(201))
    run(lambda c: send_write(c, URL, ANON, tgt(), plan, None, "owner_id", SESS), rec, Profile.DEV)
    assert len(rec.requests) == 1
    return dict(json.loads(rec.requests[0].content))


def test_user_attacker_fills_own_id_owner_is_victim() -> None:
    b = body(Role.USER_B, Role.USER_A, "CROSS_TENANT_WRITE")
    assert b["owner_id"] == A and b["created_by"] == B


def test_anon_attacker_falls_back_to_new_owner_id() -> None:
    b = body(Role.ANON, Role.USER_A, "ANON_WRITE")
    assert b["owner_id"] == A and b["created_by"] == A
