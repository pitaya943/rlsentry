"""MS6 audit (ADR-047): seeding, cleanup and escalation survive network errors without losing
track of what they wrote, and a failed restore is reported instead of silently leaving admin."""
from __future__ import annotations

import asyncio
import json

import httpx

from rlsentry.contracts.models import Finding, Profile
from rlsentry.contracts.probe import SeededRow, Sessions
from rlsentry.probe.metadata import restore_user_metadata
from rlsentry.probe.seed_pass import cleanup_reads, seed_reads
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.pipeline.fake_supabase import ANON_KEY, API, ENV, USERS, A, FakeSupabase, Table, notes_table
from tests.probe.test_escalation import esc, puts
from tests.probe.test_seed_pass import POLICY, go, tgt


def put_role(r: httpx.Request) -> object:
    return r.method == "PUT" and b'"admin"' in r.content


def test_seeding_error_on_one_target_keeps_the_rows_of_the_others() -> None:
    fake = FakeSupabase(tables={"notes": notes_table(), "locked": Table(rows=[])},
                        fail_when=lambda r: r.method == "POST" and r.url.path.endswith("/locked"))
    rows, notes = go(fake, lambda c, s: seed_reads(c, API, ANON_KEY, [tgt("notes"), tgt("locked")], POLICY, s))
    assert len(rows) == 2 and {r.target for r in rows} == {"notes"}
    assert "locked: seeding failed (ReadTimeout)" in notes


def test_cleanup_error_on_one_target_is_reported_and_the_rest_is_cleaned() -> None:
    notes = notes_table()
    fake = FakeSupabase(tables={"notes": notes, "other": Table(rows=[])})

    async def body(c: SafeClient, s: Sessions) -> tuple[list[SeededRow], list[Finding]]:
        rows, _ = await seed_reads(c, API, ANON_KEY, [tgt("other"), tgt("notes")], POLICY, s)
        fake.fail_when = lambda r: r.method == "DELETE" and r.url.path.endswith("/other")
        return rows, await cleanup_reads(c, API, ANON_KEY, [tgt("other"), tgt("notes")], rows, s)
    rows, left = go(fake, body)
    assert len(rows) == 4
    assert {(f.rule, f.target) for f in left} == {("CLEANUP_FAILED", "other")}
    assert len(notes.rows) == 2                                   # notes canaries were still deleted


def test_escalation_timeout_still_restores_and_is_noted() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)}, fail_when=put_role)
    findings, notes = esc(fake)
    assert findings == []
    assert any(n.startswith("user_a: escalation request failed (ReadTimeout)") for n in notes)
    restores = [r for r in fake.requests if r.method == "PUT" and json.loads(r.content)["data"]["role"] is None]
    assert len(restores) == 2                                     # one restore per user despite the timeout


def test_failed_restore_is_reported_never_silent() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)}, restore_status=500)
    findings, notes = esc(fake)
    assert len(findings) == 2                                     # the escalation itself was confirmed
    assert any("user_a: user_metadata restore failed" in n and "by hand" in n for n in notes)
    assert fake.metadata_role.get(A) == "admin" and len(puts(fake)) == 4


def test_restore_returns_whether_it_worked() -> None:
    async def run(fake: FakeSupabase) -> bool:
        async with SafeClient(profile=Profile.DEV, limiter=RateLimiter(rps=1e6, concurrency=8),
                              transport=fake.transport()) as c:
            s = await build_sessions(c, API, ANON_KEY, USERS, ENV)
            return await restore_user_metadata(c, API, ANON_KEY, s.tokens[next(iter(s.user_ids))])
    assert asyncio.run(run(FakeSupabase())) is True
    assert asyncio.run(run(FakeSupabase(restore_status=500))) is False
    assert asyncio.run(run(FakeSupabase(fail_when=lambda r: r.method == "PUT"))) is False
