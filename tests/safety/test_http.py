"""SafeClient (T-054). SPEC §5 Safety; contract: rlsentry/contracts/safety.py (SafeClientContract).
All traffic goes to httpx.MockTransport: no network."""
import asyncio

import httpx
import pytest

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.contracts.safety import USER_AGENT
from rlsentry.safety.http import SafeClient


class SpyLimiter:
    def __init__(self) -> None:
        self.entered = 0

    async def __aenter__(self) -> None:
        self.entered += 1

    async def __aexit__(self, *exc: object) -> None:
        return None


class Recorder:
    def __init__(self, response: httpx.Response | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.response = response or httpx.Response(200, json=[])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response


def call(profile: Profile, method: str, url: str, rec: Recorder, lim: SpyLimiter,
         hosts: tuple[str, ...] = (), **kw: object) -> httpx.Response:
    async def run() -> httpx.Response:
        async with SafeClient(profile=profile, limiter=lim, write_hosts=hosts,
                              transport=httpx.MockTransport(rec)) as c:
            return await c.request(method, url, **kw)
    return asyncio.run(run())


def test_get_sent_with_user_agent_through_limiter() -> None:
    rec, lim = Recorder(), SpyLimiter()
    r = call(Profile.AUDIT, "GET", "http://127.0.0.1:54321/rest/v1/notes", rec, lim,
             headers={"User-Agent": "curl/8", "apikey": "k"}, params={"select": "id"})
    assert r.status_code == 200 and lim.entered == 1 and len(rec.requests) == 1
    req = rec.requests[0]
    assert req.headers["user-agent"] == USER_AGENT
    assert req.headers["apikey"] == "k"
    assert req.url.params["select"] == "id"


@pytest.mark.safety
def test_refused_write_sends_nothing_and_skips_limiter() -> None:
    rec, lim = Recorder(), SpyLimiter()
    with pytest.raises(WriteRefused):
        call(Profile.AUDIT, "POST", "http://127.0.0.1:54321/rest/v1/notes", rec, lim, json={"a": 1})
    assert rec.requests == [] and lim.entered == 0


@pytest.mark.safety
def test_gate_sees_params_in_final_url() -> None:
    rec, lim = Recorder(), SpyLimiter()
    call(Profile.AUDIT, "POST", "https://t.example.test/auth/v1/token", rec, lim,
         params={"grant_type": "password"}, json={})
    assert len(rec.requests) == 1
    with pytest.raises(WriteRefused):
        call(Profile.AUDIT, "POST", "https://t.example.test/auth/v1/token?grant_type=password", rec, lim,
             params={"extra": "1"}, json={})
    assert len(rec.requests) == 1


@pytest.mark.safety
def test_write_hosts_forwarded_to_gate() -> None:
    rec, lim = Recorder(), SpyLimiter()
    url = "https://preview.example.test/rest/v1/notes"
    with pytest.raises(WriteRefused):
        call(Profile.CI, "POST", url, rec, lim, json={})
    call(Profile.CI, "POST", url, rec, lim, ("preview.example.test",), json={})
    assert [r.method for r in rec.requests] == ["POST"]


@pytest.mark.safety
def test_redirects_not_followed() -> None:
    rec = Recorder(httpx.Response(302, headers={"location": "https://evil.test/steal"}))
    r = call(Profile.AUDIT, "GET", "http://127.0.0.1:54321/rest/v1/notes", rec, SpyLimiter())
    assert r.status_code == 302 and len(rec.requests) == 1
