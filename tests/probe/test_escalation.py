"""probe/escalation.py: L03 user_metadata escalation (ADR-029 #9, ADR-042; MS3 approval note 1).

Contract: rlsentry/contracts/probe.py escalation_pass. The pass writes only the test user's own
Auth record, only when a verified DENIED read could reveal the change, and always restores it.
"""
from __future__ import annotations

import asyncio

import pytest

from rlsentry.contracts.models import (
    AccessMatrix,
    Evidence,
    Finding,
    Op,
    Outcome,
    ProbeResult,
    Profile,
    Role,
    Severity,
)
from rlsentry.contracts.policy import ExpectedPolicy, TestUser
from rlsentry.contracts.probe import ESCALATION_REASON
from rlsentry.probe.escalation import escalation_pass
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.pipeline.fake_supabase import (
    ANON_KEY,
    API,
    ENV,
    OWNER_ONLY,
    REMOTE,
    USERS,
    A,
    B,
    FakeSupabase,
    Table,
    notes_table,
)
from tests.probe.test_seed_pass import tgt

POLICY = ExpectedPolicy(tables={"notes": OWNER_ONLY})


def cell(role: Role, outcome: Outcome) -> ProbeResult:
    return ProbeResult(target="notes", role=role, op=Op.SELECT, outcome=outcome,
                       known_rows_checked=0 if outcome is Outcome.INCONCLUSIVE else 1,
                       reason="", evidence_curl="")


DENIED = AccessMatrix(cells=[cell(Role.USER_A, Outcome.DENIED), cell(Role.USER_B, Outcome.DENIED)])


def esc(fake: FakeSupabase, matrix: AccessMatrix = DENIED, env: dict[str, str] | None = None,
        users: list[TestUser] = USERS, base: str = API, profile: Profile = Profile.DEV
        ) -> tuple[list[Finding], list[str]]:
    async def run() -> tuple[list[Finding], list[str]]:
        async with SafeClient(profile=profile, limiter=RateLimiter(rps=1e6, concurrency=8),
                              transport=fake.transport()) as c:
            s = await build_sessions(c, base, ANON_KEY, USERS, ENV)
            return await escalation_pass(c, base, ANON_KEY, [tgt("notes")], POLICY, s, users,
                                         ENV if env is None else env, matrix)
    return asyncio.run(run())


def puts(fake: FakeSupabase) -> list[str]:
    return [r.headers["authorization"][-4:] for r in fake.requests if r.method == "PUT"]


def test_l03_pattern_is_confirmed_for_both_users_and_both_are_restored() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)})
    findings, notes = esc(fake)
    assert notes == []
    assert [(f.role, f.rule, f.evidence, f.severity, f.op) for f in findings] == [
        (Role.USER_A, "USER_METADATA_ESCALATION", Evidence.CONFIRMED, Severity.HIGH, Op.SELECT),
        (Role.USER_B, "USER_METADATA_ESCALATION", Evidence.CONFIRMED, Severity.HIGH, Op.SELECT)]
    p = findings[0].probes[0]
    assert p.outcome is Outcome.ALLOWED and p.known_rows_checked == 1
    assert p.reason.startswith(ESCALATION_REASON) and "1/1" in p.reason
    assert p.evidence_curl.startswith("curl ") and "****" in p.evidence_curl
    assert fake.metadata_role == {A: None, B: None}            # restored
    assert len(puts(fake)) == 4                                  # escalate + restore, per user


def test_policy_that_ignores_metadata_gives_no_finding_and_is_restored() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    findings, _ = esc(fake)
    assert findings == [] and fake.metadata_role == {A: None, B: None}


def test_nothing_is_written_without_a_verified_denied_cell() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)})
    m = AccessMatrix(cells=[cell(Role.USER_A, Outcome.INCONCLUSIVE), cell(Role.USER_B, Outcome.ALLOWED)])
    findings, _ = esc(fake, matrix=m)
    assert findings == [] and puts(fake) == []


def test_missing_password_skips_the_user_silently() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)})
    findings, notes = esc(fake, env={**ENV, "RLS_B_PW": ""})
    assert [f.role for f in findings] == [Role.USER_A] and notes == [] and len(puts(fake)) == 2


def test_metadata_not_changed_is_a_note() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)},
                        put_metadata_status=403)
    findings, notes = esc(fake)
    assert findings == [] and notes[0].startswith("user_a: user_metadata not changed")
    logins = [r for r in fake.requests if r.url.path == "/auth/v1/token"]
    assert len(logins) == 2                                       # only build_sessions' logins


@pytest.mark.safety
def test_remote_host_in_dev_is_refused_and_nothing_changes() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)}, api=REMOTE)
    findings, notes = esc(fake, base=REMOTE)
    assert findings == [] and puts(fake) == [] and fake.metadata_role == {}
    assert notes == [n for n in notes if n.startswith("user_metadata escalation refused by the safety gate: ")]
    assert len(notes) == 1


B2 = "33333333-0000-4000-8000-00000000000b"


def test_rows_already_visible_before_escalation_never_count() -> None:
    # ADR-042 補記 (L05 in the reference benchmark): a write probe can make one of B's rows
    # visible to A after the matrix was built. The fresh baseline excludes it; only the row
    # that escalation really reveals counts.
    rows = [*notes_table().rows, {"id": B2, "owner_id": B, "title": "b2"}]
    fake = FakeSupabase(tables={"notes": Table(rows=rows, admin_metadata=True,
                                               shared=frozenset({"22222222-0000-4000-8000-00000000000b"}))})
    findings, _ = esc(fake, matrix=AccessMatrix(cells=[cell(Role.USER_A, Outcome.DENIED)]))
    [f] = findings
    assert f.role is Role.USER_A and f.probes[0].known_rows_checked == 1 and "1/1" in f.probes[0].reason


def test_everything_already_visible_means_nothing_is_written() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True, rls="all")})
    findings, _ = esc(fake)                       # stale DENIED cells, but A and B now see all rows
    assert findings == [] and puts(fake) == []
