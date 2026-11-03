"""MS1 safety audit fixes (T-083, T-084; ADR-020). Contract: rlsentry/contracts/safety.py."""
import asyncio
import math

import httpx
import pytest
from pydantic import ValidationError

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ScanConfig
from rlsentry.safety.http import SafeClient
from rlsentry.safety.mode import require_write_allowed
from rlsentry.safety.ratelimit import RateLimiter

LOCAL = "http://localhost:54321/rest/v1/notes"


@pytest.mark.safety
@pytest.mark.parametrize("profile", ["AUDIT", "audit", "dev", None, 0])
@pytest.mark.parametrize("method", ["POST", "GET"])
def test_unknown_profile_fails_closed(profile: object, method: str) -> None:
    with pytest.raises(WriteRefused):
        require_write_allowed(profile, method, LOCAL)  # deliberately not a Profile


@pytest.mark.safety
@pytest.mark.parametrize("path", ["/rest/v1/%72pc/f", "/rest/v1/%2572pc/f", "/REST/V1/RPC/f",
                                  "/rest/v1//rpc/f", "//rest/v1/rpc/f", "/rest/v1/rpc%2Ff"])
@pytest.mark.parametrize("profile", [Profile.DEV, Profile.CI])
def test_rpc_ban_survives_path_tricks(path: str, profile: Profile) -> None:
    with pytest.raises(WriteRefused):
        require_write_allowed(profile, "POST", f"http://localhost:54321{path}")


def test_non_rpc_paths_still_writable_in_dev() -> None:
    require_write_allowed(Profile.DEV, "POST", "http://localhost:54321/rest/v1/rpcs_log")
    require_write_allowed(Profile.DEV, "PATCH", "http://localhost:54321/rest/v1/notes?id=eq.1")


@pytest.mark.safety
@pytest.mark.parametrize("entry", ["preview.example.test:443", "preview.example.test:80"])
def test_write_hosts_default_port_rejected(entry: str) -> None:
    with pytest.raises(ValidationError, match="default port"):
        ScanConfig.model_validate({"target": "https://x.test", "write_hosts": [entry]})


@pytest.mark.parametrize("rps", [math.nan, math.inf, -math.inf])
def test_rate_must_be_finite(rps: float) -> None:
    with pytest.raises(ValueError):
        RateLimiter(rps, 1)


@pytest.mark.safety
def test_client_drops_cookies_with_proxy_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, headers={"set-cookie": "sid=abc; Path=/"}, json=[])

    async def run() -> None:
        async with SafeClient(profile=Profile.AUDIT, limiter=RateLimiter(1000.0, 1),
                              transport=httpx.MockTransport(handler)) as c:
            await c.request("GET", "http://127.0.0.1:54321/rest/v1/a")
            await c.request("GET", "http://127.0.0.1:54321/rest/v1/b")

    asyncio.run(run())
    assert len(seen) == 2
    assert "cookie" not in seen[1].headers
