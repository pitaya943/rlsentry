"""MS7, ADR-051 #3: the L03 escalation puts back the test account's ORIGINAL user_metadata.role.

MS6 cleared the role to null (ADR-047 known limit). Now the pass reads the role first
(GET /auth/v1/user), restores exactly that value, and writes nothing when it cannot read it or
when the role is already "admin". The original value never appears in a note or finding.
Contract: rlsentry/contracts/probe.py (read_user_metadata_role, restore_user_metadata,
escalation_pass step 2b).
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from rlsentry.contracts.models import Profile, Role
from rlsentry.probe.metadata import read_user_metadata_role, restore_user_metadata
from tests.fakes import ANON, URL, Recorder, fake_jwt, run
from tests.pipeline.fake_supabase import A, B, FakeSupabase, Table, notes_table
from tests.probe.test_escalation import esc

TOKEN = fake_jwt("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def l03(**kw: Any) -> FakeSupabase:
    return FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)}, **kw)


def role_puts(fake: FakeSupabase) -> list[object]:
    return [json.loads(r.content)["data"]["role"] for r in fake.requests if r.method == "PUT"]


def test_original_role_is_put_back_after_the_finding() -> None:
    fake = l03(metadata_role={A: "editor", B: {"team": 7}})
    findings, notes = esc(fake)
    assert [f.role for f in findings] == [Role.USER_A, Role.USER_B] and notes == []
    assert role_puts(fake) == ["admin", "editor", "admin", {"team": 7}]
    assert fake.metadata_role == {A: "editor", B: {"team": 7}}


def test_absent_role_is_restored_as_null() -> None:
    fake = l03()
    esc(fake)
    assert role_puts(fake) == ["admin", None, "admin", None]


def test_role_already_admin_is_never_touched() -> None:
    # a policy that ignores metadata, so the rows stay hidden and both users are candidates
    fake = FakeSupabase(tables={"notes": notes_table()}, metadata_role={A: "admin", B: "admin"})
    findings, notes = esc(fake)
    assert findings == [] and role_puts(fake) == [] and fake.metadata_role == {A: "admin", B: "admin"}
    assert notes == [f"{r}: user_metadata.role is already admin; escalation skipped (nothing written)"
                     for r in ("user_a", "user_b")]


@pytest.mark.parametrize("kw", [{"get_user_status": 500}, {"get_user_body": ["not", "an", "object"]},
                                {"get_user_body": {"user_metadata": "x"}},
                                {"fail_when": lambda r: r.method == "GET" and r.url.path == "/auth/v1/user"}])
def test_unreadable_metadata_means_nothing_is_written(kw: dict[str, Any]) -> None:
    fake = l03(**kw)
    findings, notes = esc(fake)
    assert findings == [] and role_puts(fake) == []
    assert notes == [f"{r}: user_metadata could not be read; escalation skipped (nothing written)"
                     for r in ("user_a", "user_b")]


def test_the_original_value_never_reaches_notes_or_findings() -> None:
    fake = l03(metadata_role={A: "tenant-secret-42"})
    findings, notes = esc(fake)
    text = " ".join(notes) + " ".join(f.model_dump_json() for f in findings)
    assert "tenant-secret-42" not in text


@pytest.mark.parametrize("body, want", [
    ({"id": "u", "user_metadata": {"role": "editor"}}, (True, "editor")),
    ({"id": "u", "user_metadata": {"role": 3}}, (True, 3)),
    ({"id": "u", "user_metadata": {}}, (True, None)),
    ({"id": "u", "user_metadata": None}, (True, None)),
    ({"id": "u"}, (True, None)),
    ({"id": "u", "user_metadata": ["role"]}, (False, None)),
    ("text", (False, None)),
])
def test_read_user_metadata_role(body: object, want: tuple[bool, object]) -> None:
    rec = Recorder(lambda r: httpx.Response(200, json=body))
    assert run(lambda c: read_user_metadata_role(c, URL, ANON, TOKEN), rec, Profile.DEV) == want
    (req,) = rec.requests
    assert req.method == "GET" and req.url.path == "/auth/v1/user"
    assert req.headers["authorization"] == f"Bearer {TOKEN}" and req.headers["apikey"] == ANON


def test_read_failures_return_false_and_never_raise() -> None:
    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=r)
    for handler in (boom, lambda r: httpx.Response(401), lambda r: httpx.Response(200, content=b"{not json")):
        assert run(lambda c: read_user_metadata_role(c, URL, ANON, TOKEN), Recorder(handler), Profile.DEV) == (False, None)


def test_restore_sends_the_given_original() -> None:
    rec = Recorder(lambda r: httpx.Response(200, json={"id": "u"}))
    assert run(lambda c: restore_user_metadata(c, URL, ANON, TOKEN, "editor"), rec, Profile.DEV) is True
    assert json.loads(rec.requests[0].content) == {"data": {"role": "editor"}}
