"""RateLimiter: asyncio semaphore + token bucket (NFR-04; SPEC §5 Safety)."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from rlsentry.contracts.safety import Sleep


class RateLimiter:
    """Bound request rate and concurrency so a scan can never hammer a target.

    Capacity is one token (no bursts, even after a long idle), refilled at `rps` per second,
    starting full. Time comes only from the injected `clock` and `sleep`, so tests are exact.
    """

    def __init__(self, rps: float = 5.0, concurrency: int = 4, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Sleep = asyncio.sleep) -> None:
        if rps <= 0 or concurrency < 1:
            raise ValueError("rps must be > 0 and concurrency >= 1")
        self._rps = rps
        self._clock = clock
        self._sleep = sleep
        self._sem = asyncio.Semaphore(concurrency)
        self._token_lock = asyncio.Lock()
        self._tokens = 1.0
        self._last = clock()

    async def _take_token(self) -> None:
        async with self._token_lock:
            now = self._clock()
            self._tokens = min(1.0, self._tokens + (now - self._last) * self._rps)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens = 0.0
                return
            await self._sleep((1.0 - self._tokens) / self._rps)
            self._tokens = 0.0
            self._last = self._clock()

    async def __aenter__(self) -> None:
        await self._sem.acquire()
        try:
            await self._take_token()
        except BaseException:
            self._sem.release()
            raise

    async def __aexit__(self, *exc: object) -> None:
        self._sem.release()
