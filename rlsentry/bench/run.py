"""Bench runner: drives the lab through the product path, run_scan, and scores it (SPEC §8, §9).

Why run_scan: the bench measures what a user gets, so the only SafeClient is pipeline.py's
(ADR-042, ADR-020 #6)."""
from __future__ import annotations

import asyncio
from collections.abc import Sequence

import yaml

from lab._shared import labctl
from rlsentry import pipeline
from rlsentry.bench.score import aggregate, score_scenario
from rlsentry.contracts.bench import (
    BENCH_ANON_KEY_ENV,
    BENCH_DB_URL_ENV,
    BENCH_RPS,
    RUNTIME_PROFILE,
    RUNTIME_RPS,
    RUNTIME_TABLES,
)
from rlsentry.contracts.ground_truth import LAB_USERS, BenchReport, GroundTruth, ScenarioResult
from rlsentry.contracts.lab import POSTGREST_ROLES, LabInfo
from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ExpectedPolicy, ScanConfig, TestUser
from rlsentry.whitebox.splinter import run_splinter


def bench_config(target_url: str, info: LabInfo, policy: ExpectedPolicy, profile: Profile,
                 rps: float, with_db: bool) -> tuple[ScanConfig, dict[str, str]]:
    """The ScanConfig a lab user would write, plus the in-memory env run_scan reads (ADR-042)."""
    config = ScanConfig(
        target=target_url, authorized=True, profile=profile, rate_limit_rps=rps,
        test_users=[TestUser(name=role, email=u["email"], password_env=u["password_env"])
                    for role, u in LAB_USERS.items()],
        supabase_url=info.api_url, anon_key_env=BENCH_ANON_KEY_ENV,
        db_url_env=BENCH_DB_URL_ENV if with_db else None,
        tables=policy.tables, defaults=policy.defaults)
    env = {u["password_env"]: labctl.lab_password(role) for role, u in LAB_USERS.items()}
    env[BENCH_ANON_KEY_ENV] = info.anon_key
    if with_db:
        env[BENCH_DB_URL_ENV] = info.db_url
    return config, env


def run_scenario(sid: str, profile: Profile, info: LabInfo, *,
                 rps: float = BENCH_RPS, with_whitebox: bool = True) -> ScenarioResult:
    """Apply one scenario, scan it via run_scan and score it against expected.yaml.

    Why: runtime counts M2+M3 only (ADR-033 #6); the extra splinter run only feeds
    splinter_status, since run_scan already correlated."""
    with labctl.lock():
        labctl.apply(sid)
        gt = GroundTruth.model_validate(
            yaml.safe_load((labctl.scenario_dir(sid) / "expected.yaml").read_text("utf-8")))
        marker = labctl.db_log_marker()
        with labctl.serve_frontend(sid) as url:
            config, env = bench_config(url, info, gt.policy, profile, rps, with_whitebox)
            report = asyncio.run(pipeline.run_scan(config, confirmed_by="rlsentry-bench", env=env))
        runtime_s = report.timings.get("M2", 0) + report.timings.get("M3", 0)
        db_writes = sum(1 for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES)
        lints = run_splinter(info.db_url, config.db_schemas) if with_whitebox else None
        return score_scenario(gt, profile, report.matrix, report.findings, runtime_s,
                              lints=lints, db_writes=db_writes, db_schemas=config.db_schemas)


def run_runtime(info: LabInfo, tables: Sequence[int] = RUNTIME_TABLES) -> dict[str, float]:
    """Time M2+M3 in AUDIT over n synthetic tables at the default rate limit."""
    out: dict[str, float] = {}
    for n in tables:
        with labctl.lock():
            policy = labctl.apply_synthetic(n)
            config, env = bench_config(info.api_url, info, policy, RUNTIME_PROFILE, RUNTIME_RPS,
                                       with_db=False)
            report = asyncio.run(pipeline.run_scan(config, confirmed_by="rlsentry-bench", env=env))
            out[str(n)] = round(report.timings["M2"] + report.timings["M3"], 1)
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
