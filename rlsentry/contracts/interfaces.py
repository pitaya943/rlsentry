"""Stage interfaces (SPEC §4 執行流程, §5). Owned by the architect.

Each Protocol is the call signature one module offers to the pipeline. Implementations live
in the module packages listed in SPEC §10; they are planned in docs/PLAN.md and may refine
these signatures only through an ADR. Everything that crosses a module boundary is a model
from rlsentry.contracts.models.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from rlsentry.contracts.models import (
    AccessMatrix,
    AuthorizationRecord,
    DiscoveryResult,
    Finding,
    Profile,
    ScanReport,
    Target,
)
from rlsentry.contracts.policy import ExpectedPolicy, ScanConfig
from rlsentry.contracts.probe import Sessions
from rlsentry.contracts.recon import ReconOutput
from rlsentry.contracts.safety import SafeClientContract


class AuthorizationRefused(PermissionError):
    """NFR-02: raised before any request is sent when ownership is not confirmed."""


class WriteRefused(PermissionError):
    """NFR-01: raised by the write gate for any non-HEAD/GET request outside dev/ci."""


class Authorize(Protocol):
    """safety/gate.py. Returns the record stored in the report; raises AuthorizationRefused.
    Full rules: rlsentry.contracts.safety.authorize."""

    def __call__(self, config: ScanConfig, *, cli_confirmed: bool, confirmed_by: str,
                 profile: Profile | None = None,
                 now: datetime | None = None) -> AuthorizationRecord: ...


class RequireWriteAllowed(Protocol):
    """safety/mode.py. Every non-HEAD/GET request goes through this (SPEC §5 Safety).

    ADR-014: (1) the only non-GET request allowed in every profile is the test-user login
    `POST /auth/v1/token?grant_type=password` (FR-07), matched exactly; (2) audit refuses
    everything else; (3) dev writes only to localhost; ci to localhost or to hosts listed
    exactly in `write_hosts` (ADR-017, human decision on MS0); (4) RPCs are never POSTed:
    they are called with GET/HEAD only, in every profile.
    Full rules: rlsentry.contracts.safety.require_write_allowed."""

    def __call__(self, profile: Profile, method: str, url: str,
                 write_hosts: Iterable[str] = ()) -> None: ...


class Mask(Protocol):
    """safety/mask.py. Keeps the first 6 and last 4 characters of a key or JWT (NFR-03)."""

    def __call__(self, secret: str) -> str: ...


class Recon(Protocol):
    """recon/ (M1). ADR-023/ADR-036: SafeClient first (GET only, same origin as target_url).
    Returns the report part (ReconResult, key findings) and, in memory only, the bundle texts
    for M2 and the raw anon key. Full rules: rlsentry.contracts.recon.recon."""

    async def __call__(self, client: SafeClientContract, target_url: str) -> ReconOutput: ...


class Discover(Protocol):
    """discovery/ (M2). `bundle_sources` are the JS texts M1 scanned (for FR-05 inference).
    ADR-023: every stage that sends requests receives the run's SafeClient as first argument,
    so the write gate, rate limit and User-Agent apply to it. Full rules:
    rlsentry.contracts.discovery.discover."""

    async def __call__(self, client: SafeClientContract, supabase_url: str, anon_key: str,
                       policy: ExpectedPolicy, bundle_sources: list[str]) -> DiscoveryResult: ...


class Probe(Protocol):
    """probe/ (M3). ADR-023: SafeClient first; `sessions` carries each role's bearer token
    (anon key for anon), the test users' ids and why a role has no session.
    Full rules: rlsentry.contracts.probe.probe."""

    async def __call__(self, client: SafeClientContract, supabase_url: str, anon_key: str,
                       targets: list[Target], sessions: Sessions, policy: ExpectedPolicy,
                       profile: Profile) -> tuple[AccessMatrix, list[Finding]]: ...


class Whitebox(Protocol):
    """whitebox/ (M4). Adds lint-only findings and sets `correlation` on probe findings."""

    def __call__(self, db_url: str, findings: list[Finding]) -> list[Finding]: ...


class RunScan(Protocol):
    """pipeline.run_scan (FR-16): the single entry point shared by CLI, API and Action."""

    async def __call__(self, config: ScanConfig, *, cli_confirmed: bool = False,
                       cli_profile: Profile | None = None) -> ScanReport: ...
    # ADR-014: effective profile = the stricter of config.profile and cli_profile
    # (audit > ci > dev); audit can never be relaxed by either source.
