"""Bench runner: drives the lab through M2+M3 (+M4) and scores it (SPEC §8, §9; ADR-033)."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

import yaml

from lab._shared import labctl
from rlsentry.bench.score import aggregate, score_scenario
from rlsentry.contracts.bench import BENCH_RPS, RUNTIME_PROFILE, RUNTIME_RPS, RUNTIME_TABLES
from rlsentry.contracts.ground_truth import LAB_USERS, BenchReport, GroundTruth, ScenarioResult
from rlsentry.contracts.lab import POSTGREST_ROLES, LabInfo
from rlsentry.contracts.models import AccessMatrix, Finding, Profile
from rlsentry.contracts.policy import ExpectedPolicy, TestUser
from rlsentry.discovery.discover import discover
from rlsentry.probe.run import probe
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from rlsentry.whitebox.correlate import correlate
from rlsentry.whitebox.splinter import run_splinter

_USERS = [TestUser(name=role, email=u["email"], password_env=u["password_env"])
          for role, u in LAB_USERS.items()]


async def _pipeline(profile: Profile, info: LabInfo, policy: ExpectedPolicy, sources: list[str],
                    rps: float) -> tuple[AccessMatrix, list[Finding]]:
    """M2 + M3 exactly as the scan pipeline runs them, through one SafeClient."""
    env = {u["password_env"]: labctl.lab_password(role) for role, u in LAB_USERS.items()}
    async with SafeClient(profile=profile, limiter=RateLimiter(rps=rps, concurrency=4)) as client:
        found = await discover(client, info.api_url, info.anon_key, policy, sources)
        sessions = await build_sessions(client, info.api_url, info.anon_key, _USERS, env)
        return await probe(client, info.api_url, info.anon_key, found.targets, sessions,
                           policy, profile)


def run_scenario(sid: str, profile: Profile, info: LabInfo, *,
                 rps: float = BENCH_RPS, with_whitebox: bool = True) -> ScenarioResult:
    """Apply one scenario, scan it and score against its expected.yaml (writes only in dev)."""
    with labctl.lock():
        labctl.apply(sid)
        sdir = labctl.scenario_dir(sid)
        gt = GroundTruth.model_validate(
            yaml.safe_load((sdir / "expected.yaml").read_text("utf-8")))
        sources = [p.read_text("utf-8", errors="replace")
                   for p in sorted((sdir / "frontend").rglob("*.js"))]
        marker = labctl.db_log_marker()
        start = time.monotonic()
        matrix, findings = asyncio.run(_pipeline(profile, info, gt.policy, sources, rps))
        runtime_s = time.monotonic() - start
        db_writes = sum(1 for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES)
        lints = run_splinter(info.db_url) if with_whitebox else None
        if lints is not None:
            findings = correlate(findings, lints)
        return score_scenario(gt, profile, matrix, findings, runtime_s,
                              lints=lints, db_writes=db_writes)


def run_runtime(info: LabInfo, tables: Sequence[int] = RUNTIME_TABLES) -> dict[str, float]:
    """Time M2+M3 in AUDIT over n synthetic tables at the default rate limit."""
    out: dict[str, float] = {}
    for n in tables:
        with labctl.lock():
            policy = labctl.apply_synthetic(n)
            start = time.monotonic()
            asyncio.run(_pipeline(RUNTIME_PROFILE, info, policy, [], RUNTIME_RPS))
            out[str(n)] = round(time.monotonic() - start, 1)
    return out


def run_bench(scenarios: Sequence[str], *, runtime: bool = True) -> BenchReport:
    """Run every scenario in DEV and AUDIT, optionally the runtime sweep, and aggregate."""
    info = labctl.ensure_up()
    try:
        results: list[ScenarioResult] = []
        for sid in scenarios:
            results.append(run_scenario(sid, Profile.DEV, info))
            results.append(run_scenario(sid, Profile.AUDIT, info))
        runtime_dict = run_runtime(info) if runtime else {}
        return aggregate(results, runtime_dict)
    finally:
        if scenarios:
            labctl.apply(scenarios[-1])
