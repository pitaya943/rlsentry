"""Stage interfaces (SPEC §4 執行流程, §5). Owned by the architect.

Each Protocol is the call signature one module offers to the pipeline. Implementations live
in the module packages listed in SPEC §10; they are planned in docs/PLAN.md and may refine
these signatures only through an ADR. Everything that crosses a module boundary is a model
from rlsentry.contracts.models.
"""
from __future__ import annotations

from typing import Protocol

from rlsentry.contracts.models import (
    AccessMatrix,
    AuthorizationRecord,
    DiscoveryResult,
    Finding,
    Profile,
    ReconResult,
    Role,
    ScanReport,
    Target,
)
from rlsentry.contracts.policy import ExpectedPolicy, ScanConfig


class AuthorizationRefused(PermissionError):
    """NFR-02: raised before any request is sent when ownership is not confirmed."""


class WriteRefused(PermissionError):
    """NFR-01: raised by the write gate for any non-HEAD/GET request outside dev/ci."""


class Authorize(Protocol):
    """safety/gate.py. Returns the record stored in the report; raises AuthorizationRefused."""

    def __call__(self, config: ScanConfig, *, cli_confirmed: bool,
                 confirmed_by: str) -> AuthorizationRecord: ...


class RequireWriteAllowed(Protocol):
    """safety/mode.py. Every non-HEAD/GET request goes through this (SPEC §5 Safety).

    ADR-014: (1) the only non-GET request allowed in every profile is the test-user login
    `POST /auth/v1/token?grant_type=password` (FR-07), matched exactly; (2) audit refuses
    everything else; (3) dev/ci writes are allowed only to localhost until the human decides
    otherwise (SPEC §2 ci preview DB is an open question); (4) RPCs are never POSTed: they are
    called with GET/HEAD only, in every profile."""

    def __call__(self, profile: Profile, method: str, url: str) -> None: ...


class Mask(Protocol):
    """safety/mask.py. Keeps the first 6 and last 4 characters of a key or JWT (NFR-03)."""

    def __call__(self, secret: str) -> str: ...


class Recon(Protocol):
    """recon/ (M1)."""

    async def __call__(self, target_url: str) -> ReconResult: ...


class Discover(Protocol):
    """discovery/ (M2). `bundle_sources` are the JS texts M1 scanned (for FR-05 inference)."""

    async def __call__(self, supabase_url: str, anon_key: str, policy: ExpectedPolicy,
                       bundle_sources: list[str]) -> DiscoveryResult: ...


class Probe(Protocol):
    """probe/ (M3). `sessions` maps each role to its bearer token (anon key for anon)."""

    async def __call__(self, supabase_url: str, anon_key: str, targets: list[Target],
                       sessions: dict[Role, str], policy: ExpectedPolicy,
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
