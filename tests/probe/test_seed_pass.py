"""probe/seed_pass.py: dev/ci read seeding and its cleanup (SPEC §4 step 4; ADR-042).

Contract: rlsentry/contracts/probe.py seed_reads, cleanup_reads. Runs against the fake Supabase
of the pipeline tests through the real SafeClient (dev; localhost = writable, remote = refused).
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from rlsentry.contracts.models import Finding, Profile, Role, Target
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.probe import CANARY_PREFIX, SeededRow, Sessions
from rlsentry.probe.seed_pass import cleanup_reads, seed_reads
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.pipeline.fake_supabase import ANON_KEY, API, ENV, REMOTE, A, B, FakeSupabase, Table, notes_table
from tests.pipeline.helpers import OWNER_ONLY, USERS

POLICY = ExpectedPolicy(tables={"notes": OWNER_ONLY, "locked": OWNER_ONLY})


def tgt(name: str, kind: str = "table", pk: list[str] | None = None) -> Target:
    return Target(name=name, kind=kind, columns=["id", "owner_id", "title"], primary_key=pk or ["id"],
                  column_formats={"id": "uuid", "owner_id": "uuid", "title": "text"},
                  required=["id", "owner_id"], discovered_by="openapi", confidence="confirmed")


def go[T](fake: FakeSupabase, body: Callable[[SafeClient, Sessions], Awaitable[T]],
          base: str = API) -> T:
    async def run() -> T:
        async with SafeClient(profile=Profile.DEV, limiter=RateLimiter(rps=1e6, concurrency=8),
                              transport=fake.transport()) as c:
            sessions = await build_sessions(c, base, ANON_KEY, USERS, ENV)
            return await body(c, sessions)
    return asyncio.run(run())


def test_each_user_seeds_one_own_canary_per_table_and_cleanup_removes_them() -> None:
    notes = notes_table()
    fake = FakeSupabase(tables={"notes": notes})

    async def body(c: SafeClient, s: Sessions) -> tuple[list[SeededRow], list[str], list[Finding]]:
        rows, notes_ = await seed_reads(c, API, ANON_KEY, [tgt("notes")], POLICY, s)
        assert len(notes.rows) == 4                     # 2 original + 1 canary per user
        left = await cleanup_reads(c, API, ANON_KEY, [tgt("notes")], rows, s)
        return rows, notes_, left
    rows, notes_, left = go(fake, body)
    assert sorted(r.owner for r in rows) == [Role.USER_A, Role.USER_B] and notes_ == []
    assert all(r.target == "notes" and r.marker.startswith(CANARY_PREFIX) for r in rows)
    owners = {x["id"]: x["owner_id"] for x in notes.rows}
    assert left == [] and len(notes.rows) == 2 and set(owners.values()) == {A, B}


def test_refused_insert_is_a_note_never_a_row() -> None:
    fake = FakeSupabase(tables={"locked": Table(rows=[], insert_own=False)})
    rows, notes_ = go(fake, lambda c, s: seed_reads(c, API, ANON_KEY, [tgt("locked")], POLICY, s))
    assert rows == [] and notes_ == ["locked: user_a: seed HTTP 403", "locked: user_b: seed HTTP 403"]


def test_views_rpcs_and_composite_keys_are_never_seeded() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    targets = [tgt("notes", "view"), tgt("notes", "rpc"), tgt("notes", pk=["id", "owner_id"])]
    rows, _ = go(fake, lambda c, s: seed_reads(c, API, ANON_KEY, targets, POLICY, s))
    assert rows == [] and "POST" not in {r.method for r in fake.requests if r.url.path != "/auth/v1/token"}


@pytest.mark.safety
def test_remote_host_in_dev_is_refused_by_the_gate_and_stops_the_pass() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, api=REMOTE)
    rows, notes_ = go(fake, lambda c, s: seed_reads(c, REMOTE, ANON_KEY, [tgt("notes"), tgt("notes")],
                                                    POLICY, s), base=REMOTE)
    assert rows == [] and len(notes_) == 1
    assert notes_[0].startswith("read seeding refused by the safety gate: ")
    assert {r.method for r in fake.requests if r.url.path != "/auth/v1/token"} <= {"GET", "HEAD"}


def test_undeletable_canaries_become_cleanup_failed() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=[], delete_own=False)})

    async def body(c: SafeClient, s: Sessions) -> list[Finding]:
        rows, _ = await seed_reads(c, API, ANON_KEY, [tgt("notes")], POLICY, s)
        assert len(rows) == 2
        return await cleanup_reads(c, API, ANON_KEY, [tgt("notes")], rows, s)
    left = go(fake, body)
    assert {(f.rule, f.target) for f in left} == {("CLEANUP_FAILED", "notes")}


def test_rows_of_an_unknown_target_are_still_reported() -> None:
    fake = FakeSupabase(tables={})
    ghost = [SeededRow(target="ghost", pk="00000000-0000-4000-8000-000000000001", owner=Role.USER_A,
                       marker=CANARY_PREFIX + "x")]
    left = go(fake, lambda c, s: cleanup_reads(c, API, ANON_KEY, [], ghost, s))
    assert [(f.rule, f.target) for f in left] == [("CLEANUP_FAILED", "ghost")]
