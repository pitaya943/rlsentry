"""probe/metadata.py (L03 USER_METADATA_ESCALATION; ADR-029). Contract: contracts/probe.py
(escalate_user_metadata, restore_user_metadata). Writes only to the test user's own Auth record."""
import json

import httpx
import pytest

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.probe.metadata import escalate_user_metadata, restore_user_metadata
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

TOKEN = fake_jwt("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def ok(r: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "u"})


def test_escalate_puts_admin_role_on_own_user() -> None:
    rec = Recorder(ok)
    _status, changed = run(lambda c: escalate_user_metadata(c, URL, ANON, TOKEN), rec, Profile.DEV)
    (req,) = rec.requests
    assert req.method == "PUT" and req.url.path == "/auth/v1/user"
    assert req.headers["authorization"] == f"Bearer {TOKEN}" and req.headers["apikey"] == ANON
    assert json.loads(req.content) == {"data": {"role": "admin"}} and changed is True


def test_escalate_reports_not_changed_on_non_200() -> None:
    _status, changed = run(lambda c: escalate_user_metadata(c, URL, ANON, TOKEN),
                           Recorder(lambda r: httpx.Response(403)), Profile.DEV)
    assert changed is False


def test_restore_clears_the_role() -> None:
    rec = Recorder(ok)
    run(lambda c: restore_user_metadata(c, URL, ANON, TOKEN), rec, Profile.DEV)
    assert json.loads(rec.requests[0].content) == {"data": {"role": None}}


def test_audit_cannot_escalate() -> None:
    with pytest.raises(WriteRefused):
        run(lambda c: escalate_user_metadata(c, URL, ANON, TOKEN), Recorder(ok), Profile.AUDIT)
