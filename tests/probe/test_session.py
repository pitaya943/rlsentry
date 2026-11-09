"""probe/session.py (FR-07). Contract: rlsentry/contracts/probe.py (login, build_sessions)."""
import json

import httpx
import pytest

from rlsentry.contracts.models import Profile, Role
from rlsentry.contracts.policy import TestUser
from rlsentry.contracts.probe import LoginFailed, Sessions
from rlsentry.probe.session import build_sessions, login
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

PW = "hunter2-very-secret-password"
UID_A, UID_B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
USERS = [TestUser(name=Role.USER_A, email="a@test.dev", password_env="RLS_A_PW"),
         TestUser(name=Role.USER_B, email="b@test.dev", password_env="RLS_B_PW")]


def gotrue(r: httpx.Request) -> httpx.Response:
    body = json.loads(r.content)
    sub = {"a@test.dev": UID_A, "b@test.dev": UID_B}.get(body["email"])
    if sub is None or body["password"] != PW:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": f"bad {PW}"})
    return httpx.Response(200, json={"access_token": fake_jwt(sub), "token_type": "bearer"})


@pytest.mark.parametrize("profile", list(Profile))
def test_login_request_shape_and_result(profile: Profile) -> None:
    rec = Recorder(gotrue)
    token, sub = run(lambda c: login(c, URL + "/", ANON, "a@test.dev", PW), rec, profile)
    assert sub == UID_A and token == fake_jwt(UID_A)
    (req,) = rec.requests
    assert req.method == "POST" and str(req.url) == URL + "/auth/v1/token?grant_type=password"
    assert req.headers["apikey"] == ANON
    assert json.loads(req.content) == {"email": "a@test.dev", "password": PW}


@pytest.mark.safety
def test_rejected_login_message_leaks_nothing() -> None:
    with pytest.raises(LoginFailed) as e:
        run(lambda c: login(c, URL, ANON, "a@test.dev", "wrong-password-xyz"), Recorder(gotrue))
    msg = str(e.value)
    assert "400" in msg and "wrong-password-xyz" not in msg and PW not in msg and "invalid_grant" not in msg


@pytest.mark.parametrize("payload", [{"access_token": "not-a-jwt"}, {"token_type": "bearer"},
                                     {"access_token": "eyJh.eyJub3N1YiI6MX0.sig"}, {"access_token": 5}])
def test_unusable_token_is_login_failed(payload: object) -> None:
    with pytest.raises(LoginFailed):
        run(lambda c: login(c, URL, ANON, "a@test.dev", PW), Recorder(lambda r: httpx.Response(200, json=payload)))


@pytest.mark.safety
def test_transport_error_names_class_only() -> None:
    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused {PW}", request=r)
    with pytest.raises(LoginFailed) as e:
        run(lambda c: login(c, URL, ANON, "a@test.dev", PW), Recorder(boom))
    assert "ConnectError" in str(e.value) and PW not in str(e.value)


def test_build_sessions_all_ok() -> None:
    rec = Recorder(gotrue)
    s = run(lambda c: build_sessions(c, URL, ANON, USERS, {"RLS_A_PW": PW, "RLS_B_PW": PW}), rec)
    assert s.tokens == {Role.ANON: ANON, Role.USER_A: fake_jwt(UID_A), Role.USER_B: fake_jwt(UID_B)}
    assert s.user_ids == {Role.USER_A: UID_A, Role.USER_B: UID_B} and s.missing == {}


def test_missing_env_sends_nothing_and_failure_does_not_stop_other_user() -> None:
    rec = Recorder(gotrue)
    s = run(lambda c: build_sessions(c, URL, ANON, USERS, {"RLS_A_PW": "", "RLS_B_PW": PW}), rec)
    assert len(rec.requests) == 1 and s.missing == {Role.USER_A: "RLS_A_PW is not set"}
    s2 = run(lambda c: build_sessions(c, URL, ANON, USERS, {"RLS_A_PW": "nope", "RLS_B_PW": PW}), Recorder(gotrue))
    assert set(s2.tokens) == {Role.ANON, Role.USER_B} and "400" in s2.missing[Role.USER_A]


def test_unconfigured_user_role() -> None:
    s = run(lambda c: build_sessions(c, URL, ANON, USERS[:1], {"RLS_A_PW": PW}), Recorder(gotrue))
    assert s.missing == {Role.USER_B: "no test account configured"} and Role.USER_A in s.user_ids


@pytest.mark.safety
def test_sessions_never_show_tokens() -> None:
    s = Sessions(tokens={Role.ANON: ANON, Role.USER_A: fake_jwt(UID_A)}, user_ids={Role.USER_A: UID_A})
    for text in (repr(s), str(s), s.model_dump_json(), json.dumps(s.model_dump(mode="json"))):
        assert "eyJ" not in text
