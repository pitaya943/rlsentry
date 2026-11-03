"""MS1 holdout: same behaviour as the visible safety tests, different inputs."""
import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from rlsentry.contracts.interfaces import AuthorizationRefused, WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ScanConfig
from rlsentry.contracts.safety import MASK_FILL, USER_AGENT
from rlsentry.safety.gate import authorize
from rlsentry.safety.http import SafeClient
from rlsentry.safety.mask import mask, mask_text
from rlsentry.safety.mode import require_write_allowed
from rlsentry.safety.ratelimit import RateLimiter


def cfg(**kw: object) -> ScanConfig:
    return ScanConfig.model_validate({"target": "https://app.sample.test", **kw})


def test_gate_refuses_unconfirmed_ci() -> None:
    with pytest.raises(AuthorizationRefused):
        authorize(cfg(profile="ci"), cli_confirmed=False, confirmed_by="ops-bot",
                  now=datetime(2027, 1, 1, tzinfo=UTC))


def test_gate_records_ci_hosts_from_cli_profile() -> None:
    c = cfg(authorized=True, profile="audit", write_hosts=["staging.sample.test:5432"])
    rec = authorize(c, cli_confirmed=False, confirmed_by="ops-bot", profile=Profile.CI,
                    now=datetime(2027, 1, 1, tzinfo=UTC))
    assert rec.write_hosts == ["staging.sample.test:5432"] and rec.method == "config"


@pytest.mark.parametrize(("profile", "method", "url", "hosts", "allowed"), [
    (Profile.AUDIT, "DELETE", "http://localhost:3000/rest/v1/t", (), False),
    (Profile.DEV, "DELETE", "http://localhost:3000/rest/v1/t", (), True),
    (Profile.DEV, "PUT", "https://staging.sample.test/auth/v1/user", ("staging.sample.test",), False),
    (Profile.CI, "PUT", "https://staging.sample.test/auth/v1/user", ("staging.sample.test",), True),
    (Profile.CI, "PUT", "https://staging.sample.test/auth/v1/user", ("sample.test",), False),
    (Profile.CI, "PATCH", "https://STAGING.sample.test:6543/x", ("staging.sample.test:6543",), True),
    (Profile.CI, "PATCH", "https://staging.sample.test/x", ("staging.sample.test:6543",), False),
    (Profile.CI, "POST", "http://127.0.0.1/rest/v1/rpc/do_it", (), False),
    (Profile.AUDIT, "POST", "http://127.0.0.1/auth/v1/token?grant_type=password", (), True),
    (Profile.AUDIT, "POST", "http://127.0.0.1/auth/v1/token?grant_type=PASSWORD", (), False),
    (Profile.DEV, "POST", "http://127.0.0.1@attacker.test/rest/v1/t", (), False),
    (Profile.AUDIT, "HEAD", "https://anywhere.sample.test/rest/v1/t", (), True),
])
def test_mode_matrix(profile: Profile, method: str, url: str, hosts: tuple[str, ...], allowed: bool) -> None:
    if allowed:
        require_write_allowed(profile, method, url, hosts)
    else:
        with pytest.raises(WriteRefused):
            require_write_allowed(profile, method, url, hosts)


def test_mask_values() -> None:
    s = "0123456789ABCDEFGHIJKLMNOP"
    assert mask(s) == "012345" + MASK_FILL + "MNOP"
    assert mask("short-key") == MASK_FILL
    jwt = "eyJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjMifQ.abcDEF123_-xyz"
    out = mask_text(f"Bearer {jwt}\nsb_publishable_ZZZZZZZZZZZZZZZZ end")
    assert jwt not in out and "sb_publishable_ZZZZZZZZZZZZZZZZ" not in out and out.endswith(" end")


def test_ratelimit_one_rps() -> None:
    now = [0.0]

    async def sleep(d: float) -> None:
        now[0] += d
        await asyncio.sleep(0)

    rl = RateLimiter(1.0, 3, clock=lambda: now[0], sleep=sleep)
    seen: list[float] = []

    async def run() -> None:
        for _ in range(4):
            async with rl:
                seen.append(now[0])

    asyncio.run(run())
    assert seen == pytest.approx([0.0, 1.0, 2.0, 3.0])


def test_http_refuses_and_overrides_agent() -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(204)

    async def run() -> None:
        rl = RateLimiter(100.0, 1)
        async with SafeClient(profile=Profile.DEV, limiter=rl, transport=httpx.MockTransport(handler)) as c:
            await c.request("DELETE", "http://localhost:54321/rest/v1/t", headers={"user-agent": "x"},
                            params={"id": "eq.1"})
            with pytest.raises(WriteRefused):
                await c.request("DELETE", "https://remote.sample.test/rest/v1/t")

    asyncio.run(run())
    assert len(calls) == 1 and calls[0].headers["user-agent"] == USER_AGENT
