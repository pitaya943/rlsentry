"""RateLimiter (T-053). NFR-04; contract: rlsentry/contracts/safety.py (RateLimiterContract).
A fake clock makes timing exact: sleep() advances the clock by the requested amount."""
import asyncio

import pytest

from rlsentry.safety.ratelimit import RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    async def sleep(self, d: float) -> None:
        self.sleeps.append(d)
        self.t += d
        await asyncio.sleep(0)


def limiter(ft: FakeTime, rps: float = 5.0, concurrency: int = 4) -> RateLimiter:
    return RateLimiter(rps, concurrency, clock=ft.clock, sleep=ft.sleep)


@pytest.mark.parametrize(("rps", "conc"), [(0, 1), (-1, 1), (5, 0), (5, -2)])
def test_invalid_arguments(rps: float, conc: int) -> None:
    with pytest.raises(ValueError):
        RateLimiter(rps, conc)


@pytest.mark.safety
def test_sequential_entries_are_spaced_by_one_over_rps() -> None:
    ft = FakeTime()
    rl = limiter(ft, rps=5.0)
    times: list[float] = []

    async def run() -> None:
        for _ in range(6):
            async with rl:
                times.append(ft.t)

    asyncio.run(run())
    assert times[0] == 1000.0
    for k, t in enumerate(times):
        assert t == pytest.approx(1000.0 + k / 5.0)
    assert ft.sleeps[0] == pytest.approx(0.2)


def test_bucket_capacity_is_one_after_idle() -> None:
    ft = FakeTime()
    rl = limiter(ft, rps=2.0)
    times: list[float] = []

    async def run() -> None:
        async with rl:
            times.append(ft.t)
        ft.t += 60.0                       # long idle must not bank more than one token
        for _ in range(2):
            async with rl:
                times.append(ft.t)

    asyncio.run(run())
    assert times[1] == pytest.approx(1060.0)
    assert times[2] == pytest.approx(1060.5)


@pytest.mark.safety
def test_concurrency_bounded() -> None:
    ft = FakeTime()
    rl = limiter(ft, rps=1000.0, concurrency=2)
    active = 0
    peak = 0

    async def body() -> None:
        nonlocal active, peak
        async with rl:
            active += 1
            peak = max(peak, active)
            for _ in range(5):
                await asyncio.sleep(0)
            active -= 1

    async def run() -> None:
        await asyncio.gather(*(body() for _ in range(7)))

    asyncio.run(run())
    assert peak == 2


def test_slot_released_when_body_raises() -> None:
    ft = FakeTime()
    rl = limiter(ft, rps=1000.0, concurrency=1)

    async def run() -> int:
        with pytest.raises(RuntimeError):
            async with rl:
                raise RuntimeError("boom")
        async with rl:
            return 1

    assert asyncio.run(asyncio.wait_for(run(), timeout=5)) == 1
