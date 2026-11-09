"""SafeClient: the only HTTP client in rlsentry (SPEC §5 Safety; NFR-01, NFR-04)."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from http.cookiejar import Cookie, DefaultCookiePolicy
from typing import Any, Self

import httpx

from rlsentry.contracts.models import Profile
from rlsentry.contracts.safety import USER_AGENT
from rlsentry.safety.mode import require_write_allowed
from rlsentry.safety.ratelimit import RateLimiter


class _NoCookies(DefaultCookiePolicy):
    """Refuse to store or return any cookie, so no state crosses requests or identities."""

    def set_ok(self, cookie: Cookie, request: object) -> bool:
        return False

    def return_ok(self, cookie: Cookie, request: object) -> bool:
        return False

    def domain_return_ok(self, domain: str, request: object) -> bool:
        return False

    def path_return_ok(self, path: str, request: object) -> bool:
        return False


class SafeClient:
    """Funnel every request through the write gate, the rate limiter and a fixed User-Agent.

    The gate runs on the final URL (params included) before the limiter, so a refused write
    costs no token and sends nothing. Redirects are never followed, so a write or token
    cannot be bounced to another host.
    """

    def __init__(self, *, profile: Profile, limiter: RateLimiter,
                 write_hosts: Iterable[str] = (),
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 10.0) -> None:
        self._profile = profile
        self._limiter = limiter
        self._write_hosts = tuple(write_hosts)
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout,
                                         follow_redirects=False, trust_env=False)
        self._client.cookies.jar.set_policy(_NoCookies())

    async def request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None,
                      params: Mapping[str, str] | None = None, json: Any = None) -> httpx.Response:
        """Send one request after the write gate passes; WriteRefused propagates unsent."""
        final_url = str(self._client.build_request(method, url, params=params).url)
        require_write_allowed(self._profile, method, final_url, self._write_hosts)
        merged = {k: v for k, v in (headers or {}).items() if k.lower() != "user-agent"}
        merged["User-Agent"] = USER_AGENT
        async with self._limiter:
            return await self._client.request(method, url, headers=merged, params=params,
                                              json=json)

    async def aclose(self) -> None:
        """Close the underlying transport."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
