"""Shared test helpers for M2/M3 unit tests: a real SafeClient over httpx.MockTransport.

Using the real SafeClient (not a stub) means every unit test also exercises the write gate:
a module that sent a forbidden request would raise WriteRefused here. No network is used.
"""
from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Awaitable, Callable

import httpx

from rlsentry.contracts.models import Profile
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter

URL = "http://127.0.0.1:54321"
ANON = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.anonsignatureanonsignature"

Handler = Callable[[httpx.Request], httpx.Response]


def fake_jwt(sub: str, extra: str = "") -> str:
    """A JWT-shaped token whose payload carries `sub` (signature is junk: never verified)."""
    body = base64.urlsafe_b64encode(json.dumps({"sub": sub, "role": "authenticated"}).encode())
    return "eyJhbGciOiJIUzI1NiJ9." + body.decode().rstrip("=") + ".sig" + extra + "nature0123"


class Recorder:
    """Records every request that reached the transport, then delegates to `handler`."""

    def __init__(self, handler: Handler | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = handler or (lambda r: httpx.Response(200, json=[]))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def methods(self) -> set[str]:
        return {r.method for r in self.requests}


def run[T](make: Callable[[SafeClient], Awaitable[T]], rec: Recorder,
        profile: Profile = Profile.AUDIT) -> T:
    """Run `make(client)` with a SafeClient whose transport is `rec` (rate limit effectively off)."""
    async def go() -> T:
        async with SafeClient(profile=profile, limiter=RateLimiter(rps=1e6, concurrency=8),
                              transport=httpx.MockTransport(rec)) as client:
            return await make(client)
    return asyncio.run(go())
