"""ADR-041 (MS3 approval note 1): a write the SafeClient gate refuses becomes INCONCLUSIVE.

dev never writes to a remote host and ci only to listed hosts (ADR-017); the refusal happens
before anything is sent, so the cells are "not judged", never denied, and the scan goes on.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from rlsentry.contracts.models import AccessMatrix, Finding, Op, Outcome, ProbeResult, Profile, Role
from rlsentry.contracts.probe import WRITE_REFUSED_REASON
from rlsentry.probe.run import probe
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.fakes import ANON, Recorder
from tests.probe.test_run import POLICY, SESS, TWO, FakeRest, Rel, todos

REMOTE = "https://preview.example.test"


def remote_scan(profile: Profile, write_hosts: tuple[str, ...] = ()) -> tuple[dict[tuple[str, Role, Op], ProbeResult], Recorder]:
    rec = Recorder(FakeRest({"todos": Rel(TWO)}))

    async def go() -> tuple[AccessMatrix, list[Finding]]:
        async with SafeClient(profile=profile, limiter=RateLimiter(rps=1e6, concurrency=8),
                              write_hosts=write_hosts, transport=httpx.MockTransport(rec)) as c:
            return await probe(c, REMOTE, ANON, [todos(), todos("other")], SESS, POLICY, profile)
    matrix, _ = asyncio.run(go())
    return {(c.target, c.role, c.op): c for c in matrix.cells}, rec


@pytest.mark.safety
@pytest.mark.parametrize("profile", [Profile.DEV, Profile.CI])
def test_refused_writes_are_inconclusive_and_nothing_is_written(profile: Profile) -> None:
    cells, rec = remote_scan(profile)
    assert rec.methods() <= {"GET", "HEAD"}
    for t in ("todos", "other"):
        writes = [c for k, c in cells.items() if k[0] == t and k[2] is not Op.SELECT]
        assert len(writes) == 9
        for c in writes:
            assert c.outcome is Outcome.INCONCLUSIVE and c.known_rows_checked == 0
            assert c.reason.startswith(WRITE_REFUSED_REASON + ": ") and c.evidence_curl == ""
            assert "preview.example.test" in c.reason
        assert cells[(t, Role.USER_A, Op.SELECT)].outcome is Outcome.DENIED     # reads unaffected
