"""Scanner write-path mutation tests (ADR-022 #3, ADR-026 必做變異; common-mode risk).

Each test takes a SAFE scenario, confirms the scanner reports no write vulnerability, then
plants a real write hole with labctl.execute and asserts the scanner now raises a CONFIRMED
finding with the expected rule. This catches a scanner whose write verdict is hardwired to
"denied" or that trusts a 2xx without reading the row back. The scenario is re-applied after.
Needs Docker.
"""
from __future__ import annotations

import asyncio

import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS, GroundTruth
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Evidence, Finding, Op, Profile
from rlsentry.contracts.policy import TestUser
from rlsentry.discovery.discover import discover
from rlsentry.probe.run import probe
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.lab.oracle import load_gt, scenario_path

pytestmark = pytest.mark.safety


def scan(info: LabInfo, sid: str, gt: GroundTruth) -> list[Finding]:
    users = [TestUser(name=r, email=u["email"], password_env=u["password_env"]) for r, u in LAB_USERS.items()]
    env = {u["password_env"]: labctl.lab_password(r) for r, u in LAB_USERS.items()}
    d = scenario_path(sid) / "frontend"
    sources = [p.read_text("utf-8") for p in sorted(d.rglob("*.js"))] if d.is_dir() else []

    async def go() -> list[Finding]:
        async with SafeClient(profile=Profile.DEV, limiter=RateLimiter(rps=200, concurrency=4)) as client:
            disc = await discover(client, info.api_url, info.anon_key, gt.policy, sources)
            sessions = await build_sessions(client, info.api_url, info.anon_key, users, env)
            _matrix, findings = await probe(client, info.api_url, info.anon_key, disc.targets,
                                            sessions, gt.policy, Profile.DEV)
            return findings
    return asyncio.run(go())


def confirmed(findings: list[Finding], target: str, op: Op, rule: str) -> list[Finding]:
    return [f for f in findings if f.evidence is Evidence.CONFIRMED and f.target == target
            and f.op is op and f.rule == rule]


def caught(info: LabInfo, sid: str, target: str, op: Op, rule: str, sql: str) -> None:
    """The unmutated safe scenario has no such finding; the mutation makes the scanner report it."""
    labctl.apply(sid)
    try:
        before = confirmed(scan(info, sid, load_gt(sid)), target, op, rule)
        assert not before, f"{sid}: {rule} on {target} present BEFORE the mutation: {before}"
        labctl.execute(sql)
        after = confirmed(scan(info, sid, load_gt(sid)), target, op, rule)
        assert after, f"{sid}: scanner did not catch planted {rule} on {target}.{op.value}"
    finally:
        labctl.apply(sid)


def test_scanner_catches_planted_cross_tenant_update(lab_info: LabInfo) -> None:
    # C01 todos is owner-scoped and safe. A permissive UPDATE policy opens cross-tenant writes;
    # the scanner must flip from denied to a confirmed CROSS_TENANT_WRITE (read-back verified).
    caught(lab_info, "C01", "todos", Op.UPDATE, "CROSS_TENANT_WRITE",
           "create policy pwn_upd on public.todos for update to authenticated "
           "using (true) with check (true)")


def test_scanner_catches_planted_anon_delete(lab_info: LabInfo) -> None:
    # A permissive DELETE policy for anon opens anonymous deletes → ANON_WRITE.
    caught(lab_info, "C01", "todos", Op.DELETE, "ANON_WRITE",
           "create policy pwn_del on public.todos for delete to anon using (true)")
