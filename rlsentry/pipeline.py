"""Scan pipeline: authorize, M1, S4, M2, M3, M4, M5 over ONE SafeClient (ADR-020 #6, ADR-042).

Why one module: the CLI, the Python API and the GitHub Action must share exactly one code path,
and the only place a SafeClient is built is here, after authorize() and the S4 endpoint checks.
"""
from __future__ import annotations

import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import psycopg

from rlsentry.contracts.models import Finding, PolicyRow, Profile, ScanReport
from rlsentry.contracts.pipeline import (
    CONFIRMER_ENV,
    M1_SKIPPED_NOTE,
    M4_SKIPPED_NOTE,
    MODULES_BY_PROFILE,
    PROFILE_STRICTNESS,
    WRITES_AUDIT_NOTE,
    EndpointRefused,
    ScanSetupError,
)
from rlsentry.contracts.policy import ScanConfig
from rlsentry.contracts.safety import TOOL_VERSION
from rlsentry.discovery.discover import discover
from rlsentry.policy.init import draft_policy
from rlsentry.probe.escalation import escalation_pass
from rlsentry.probe.run import WRITE_REFUSED_REASON, probe
from rlsentry.probe.seed_pass import cleanup_reads, seed_reads
from rlsentry.probe.session import build_sessions
from rlsentry.recon.links import report_url
from rlsentry.recon.run import recon
from rlsentry.report.enrich import enrich
from rlsentry.safety.endpoint import normalize_api_url, resolve_endpoint
from rlsentry.safety.gate import authorize
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from rlsentry.whitebox.correlate import correlate
from rlsentry.whitebox.policies import read_policies
from rlsentry.whitebox.splinter import run_splinter


def stricter_profile(config_profile: Profile, cli_profile: Profile | None) -> Profile:
    """The stricter of the config and CLI profiles, so a flag can only tighten a scan (ADR-014 #4)."""
    if cli_profile is None:
        return config_profile
    if PROFILE_STRICTNESS[cli_profile] > PROFILE_STRICTNESS[config_profile]:
        return cli_profile
    return config_profile


def modules_for(profile: Profile, db_url: str | None) -> list[str]:
    """Modules a profile runs; M4 only when a database URL exists (ADR-042 #2)."""
    return [m for m in MODULES_BY_PROFILE[profile] if m != "M4" or db_url]


def _confirmer(confirmed_by: str | None, env: Mapping[str, str]) -> str:
    if confirmed_by:
        return confirmed_by
    for name in CONFIRMER_ENV:
        if env.get(name):
            return env[name]
    return "unknown"


def _new_client(profile: Profile, config: ScanConfig, write_hosts: list[str],
                transport: Any) -> SafeClient:
    return SafeClient(profile=profile,
                      limiter=RateLimiter(rps=config.rate_limit_rps, concurrency=4),
                      write_hosts=write_hosts, transport=transport)


def _bundle_url_differs(recon_url: str, url: str) -> bool:
    try:
        return normalize_api_url(recon_url) != url
    except EndpointRefused:
        return True


async def run_scan(config: ScanConfig, *, cli_confirmed: bool = False,
                   cli_profile: Profile | None = None, cli_supabase_url: str | None = None,
                   confirmed_by: str | None = None, env: Mapping[str, str] | None = None,
                   transport: Any = None, now: datetime | None = None) -> ScanReport:
    """Run the whole scan and return the enriched report (FR-16).

    Why this order: nothing is sent before authorization and the S4 endpoint checks, and the
    Supabase URL is never taken from the bundle alone (ADR-043).
    """
    env = os.environ if env is None else env
    started = datetime.now(UTC)
    profile = stricter_profile(config.profile, cli_profile)
    record = authorize(config, cli_confirmed=cli_confirmed,
                       confirmed_by=_confirmer(confirmed_by, env), profile=profile, now=now)
    db_url = (env.get(config.db_url_env) if config.db_url_env else None) or None
    modules = modules_for(profile, db_url)
    use_m1 = "M1" in modules
    notes: list[str] = []
    url = ""
    method = ""
    if not use_m1:
        url, method = resolve_endpoint(config, cli_supabase_url, None)
        notes.append(M1_SKIPPED_NOTE)
    anon_key: str | None = None
    if config.anon_key_env:
        anon_key = env.get(config.anon_key_env) or None
        if anon_key is None:
            raise ScanSetupError(f"anon key variable {config.anon_key_env} is not set")
    elif not use_m1:
        raise ScanSetupError("ci needs anon_key_env: the anon key is not taken from a bundle in ci")
    timings: dict[str, float] = {}
    rec = None
    policies: list[PolicyRow] = []
    async with _new_client(profile, config, record.write_hosts, transport) as client:
        sources: list[str] = []
        if use_m1:
            t = time.monotonic()
            rec = await recon(client, config.target)
            timings["M1"] = time.monotonic() - t
            url, method = resolve_endpoint(config, cli_supabase_url, rec.result.supabase_url)
            if rec.result.supabase_url is not None and _bundle_url_differs(
                    rec.result.supabase_url, url):
                notes.append("the frontend bundle points at "
                             f"{report_url(rec.result.supabase_url)}, not the confirmed "
                             "Supabase URL")
            if anon_key is None:
                anon_key = rec.anon_key
            sources = rec.sources
        record = record.model_copy(update={"supabase_url": url, "supabase_url_method": method})
        if anon_key is None:
            raise ScanSetupError("no anon key: set anon_key_env or make sure the bundle "
                                 "contains the anon key")

        t = time.monotonic()
        found = await discover(client, url, anon_key, config.policy, sources)
        timings["M2"] = time.monotonic() - t

        t = time.monotonic()
        sessions = await build_sessions(client, url, anon_key, config.test_users, env)
        writes = profile is not Profile.AUDIT
        seeded: list[Any] = []
        if writes:
            seeded, seed_notes = await seed_reads(client, url, anon_key, found.targets,
                                                  config.policy, sessions)
            notes.extend(seed_notes)
        try:
            matrix, m3 = await probe(client, url, anon_key, found.targets, sessions,
                                     config.policy, profile)
            if writes:
                esc, esc_notes = await escalation_pass(client, url, anon_key, found.targets,
                                                       config.policy, sessions,
                                                       config.test_users, env, matrix)
                m3 = m3 + esc
                notes.extend(esc_notes)
            else:
                notes.append(WRITES_AUDIT_NOTE)
        finally:
            # ADR-047: canaries are deleted even when probe or escalation crashes.
            cleanup = (await cleanup_reads(client, url, anon_key, found.targets, seeded,
                                           sessions) if writes else [])
        m3 = m3 + cleanup
        refused = sum(1 for c in matrix.cells if c.reason.startswith(WRITE_REFUSED_REASON))
        if refused:
            notes.append(f"{refused} write cells inconclusive: writes to "
                         f"{urlsplit(url).netloc} refused by the safety gate (ADR-041)")
        timings["M3"] = time.monotonic() - t

    if "M4" in modules and db_url:
        t = time.monotonic()
        try:
            lints = run_splinter(db_url, config.db_schemas)
            m3 = correlate(m3, lints, config.db_schemas)
            policies = read_policies(db_url, config.db_schemas)
            timings["M4"] = time.monotonic() - t
        except (psycopg.Error, OSError, ValueError, RuntimeError) as exc:  # M4 is optional; no message (DB URL)
            notes.append(f"M4 failed: {type(exc).__name__}")
            modules = [m for m in modules if m != "M4"]
            policies = []
    if "M4" not in modules:
        notes.append(M4_SKIPPED_NOTE)

    findings: list[Finding] = m3 + (rec.findings if rec is not None else [])
    report = ScanReport(
        tool_version=TOOL_VERSION, target=config.target, profile=profile, authorization=record,
        started_at=started, finished_at=datetime.now(UTC),
        recon=rec.result if rec is not None else None, discovery=found, matrix=matrix,
        findings=findings, policies=policies, modules=modules, notes=notes, timings=timings)
    return enrich(report, config)


async def run_init(config: ScanConfig, *, cli_confirmed: bool = False,
                   cli_supabase_url: str | None = None, confirmed_by: str | None = None,
                   env: Mapping[str, str] | None = None, transport: Any = None) -> str:
    """Draft a policy from discovery (FR-15); GET-only, so it runs with the audit profile."""
    env = os.environ if env is None else env
    record = authorize(config, cli_confirmed=cli_confirmed,
                       confirmed_by=_confirmer(confirmed_by, env), profile=Profile.AUDIT)
    url, _ = resolve_endpoint(config, cli_supabase_url, None)
    anon_key = env.get(config.anon_key_env) if config.anon_key_env else None
    if not anon_key:
        raise ScanSetupError("anon_key_env is not set or empty: init needs the anon key")
    async with _new_client(Profile.AUDIT, config, record.write_hosts, transport) as client:
        found = await discover(client, url, anon_key, config.policy, [])
    return f"target: {config.target}\n" + draft_policy(found.targets)
