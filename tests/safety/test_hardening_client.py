"""MS1 safety audit fixes for the client and limiter (T-084; ADR-020)."""
import asyncio
import math

import httpx
import pytest

from rlsentry.contracts.models import Profile
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter


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
