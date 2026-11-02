"""Data models exchanged between modules (SPEC §6). Owned by the architect.

Every model here is also part of the JSON report format, so any field change needs an ADR
(SPEC §6). Fields marked "ADR-006" are additions to the SPEC §6 listing; see docs/DECISIONS.md.

Why one file: modules (M1–M5, safety) only talk to each other through these types, which is
what lets different implementers work in parallel and lets the human review one file to see
every hand-off.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Role(str, Enum):
    """Identity used for a probe. user_a / user_b are the two test accounts (SPEC §5 M3)."""

    ANON = "anon"
    USER_A = "user_a"
    USER_B = "user_b"


class Op(str, Enum):
    """Operation probed. Calling an RPC is modelled as SELECT ("obtains data"), see ADR-007."""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class Outcome(str, Enum):
    """Three-state result plus not_tested (SPEC §5 M3: count = 0 is NOT denied)."""

    ALLOWED = "allowed"
    DENIED = "denied"
    INCONCLUSIVE = "inconclusive"
    NOT_TESTED = "not_tested"


class Evidence(str, Enum):
    """Evidence level, independent of severity (SPEC §5 M5)."""

    CONFIRMED = "confirmed"
    SUSPECTED = "suspected"
    CONFIG_WARNING = "config_warning"


class Severity(str, Enum):
    """Severity (SPEC §5 M5). Ordering for `fail_on` comparisons is given by SEVERITY_RANK."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW = "review"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1, Severity.REVIEW: 0,
}
"""Higher is worse. REVIEW ranks lowest: it means "cannot judge", never "safe" or "severe"."""


class Profile(str, Enum):
    """Usage profile (SPEC §2). audit is forced read-only and cannot be overridden (NFR-01)."""

    DEV = "dev"
    CI = "ci"
    AUDIT = "audit"


class _Strict(BaseModel):
    # forbid unknown fields: a typo in a report or config must fail loudly, not vanish.
    model_config = ConfigDict(extra="forbid")


class KeyFinding(_Strict):
    """M1: one key-like string found in the bundle. The raw value is never stored (NFR-03)."""

    kind: str = Field(pattern=r"^(publishable|secret|unverified)$")
    masked: str                       # first 6 + last 4 characters kept, see safety/mask
    source_file: str
    jwt_claims: dict[str, str | int | None] | None = None   # role, ref, exp only


class Target(_Strict):
    """M2: one attack-surface entry (table, view or RPC)."""

    name: str
    kind: str = Field(pattern=r"^(table|view|rpc)$")
    columns: list[str] = []
    primary_key: list[str] = []
    discovered_by: str = Field(pattern=r"^(openapi|bundle|policy)$")
    confidence: str = Field(pattern=r"^(confirmed|inferred|unknown)$")


class ProbeResult(_Strict):
    """M3: one cell of the access matrix (target × role × op)."""

    target: str
    role: Role
    op: Op
    outcome: Outcome
    known_rows_checked: int = Field(ge=0)  # known PKs used for the verdict
    reason: str                             # always explain inconclusive / not_tested
    http_status: int | None = None
    evidence_curl: str                      # reproduction command with keys masked

    @model_validator(mode="after")
    def _no_rows_means_no_verdict(self) -> ProbeResult:
        # SPEC §6: known_rows_checked == 0 ⇒ inconclusive. Encoded in the type so that no
        # module can ever report "denied" (i.e. "safe") without a known row to judge by.
        # not_tested is also allowed: the cell was never probed (e.g. writes in audit).
        # For writes the known row is the seeded row or the inserted canary that was read back;
        # an RPC that is callable but returns no known row is inconclusive, not allowed.
        if self.known_rows_checked == 0 and self.outcome in (Outcome.ALLOWED, Outcome.DENIED):
            raise ValueError("a verdict needs at least one known row; use inconclusive")
        return self


class Finding(_Strict):
    """M1/M3/M4 → M5: one reported issue.

    `role` and `op` are additions (ADR-006): the benchmark matches findings to ground-truth
    cases by (target, op, role, rule), and key findings have no probes to derive them from.
    `id` = finding_id(target, role, op, rule), see that function's docstring.
    """

    id: str
    rule: str                         # a key of rlsentry.contracts.rules.RULES
    evidence: Evidence
    severity: Severity
    target: str | None = None
    role: Role | None = None          # ADR-006
    op: Op | None = None              # ADR-006
    probes: list[ProbeResult] = []
    lint: str | None = None
    correlation: str | None = Field(default=None, pattern=r"^(confirmed|lint_only|probe_only)$")
    fix_sql: str | None = None


def finding_id(target: str | None, role: Role | None, op: Op | None, rule: str) -> str:
    """Stable content hash so CI can tell a new issue from an old unfixed one (SPEC §6).

    Format (frozen): first 16 hex chars of sha256 over "<target>|<role>|<op>|<rule>", with
    None rendered as the empty string and enums by their value. Defined here, not in an
    implementation module, because the id is part of the report format.
    """
    import hashlib

    parts = [target or "", role.value if role else "", op.value if op else "", rule]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


# --- stage outputs (ADR-006: not listed in SPEC §6, needed for the hand-offs in §4) ---------

class ReconResult(_Strict):
    """M1 output (SPEC §5 M1): URL, keys and the scan scope the report must list."""

    supabase_url: str | None
    keys: list[KeyFinding] = []
    chunks_scanned: list[str] = []


class DiscoveryResult(_Strict):
    """M2 output. `openapi_available` drives the "not found ≠ safe" coverage note (FR-05)."""

    targets: list[Target] = []
    openapi_available: bool


class AccessMatrix(_Strict):
    """M3 output: every probed cell, including inconclusive and not_tested ones."""

    cells: list[ProbeResult] = []


class AuthorizationRecord(_Strict):
    """NFR-02: who confirmed ownership of the target, how, and when (recorded in the report)."""

    confirmed_by: str
    method: str = Field(pattern=r"^(cli_flag|config)$")
    confirmed_at: datetime


class ScanReport(_Strict):
    """The JSON report (FR-12). M5 renders HTML/SARIF from this object only."""

    tool_version: str
    target: str
    profile: Profile
    authorization: AuthorizationRecord
    started_at: datetime
    finished_at: datetime
    recon: ReconResult | None = None
    discovery: DiscoveryResult | None = None
    matrix: AccessMatrix = AccessMatrix()
    findings: list[Finding] = []
