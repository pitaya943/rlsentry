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
    # ADR-036: jwt:<role> | sb_secret | sb_publishable | unverified (= contracts.recon.KEY_LABEL_RE);
    # also the Finding.target of a key finding, so the benchmark matches by label (ADR-011 #9).
    label: str = Field(pattern=r"^(jwt:[a-z_]+|sb_secret|sb_publishable|unverified)$")
    masked: str                       # first 6 + last 4 characters kept, see safety/mask
    source_file: str                  # recon.report_url form: no query string, keys masked
    jwt_claims: dict[str, str | int | None] | None = None   # role, ref, exp only

    @model_validator(mode="after")
    def _consistent(self) -> KeyFinding:
        # MS5 audit S6: the report must never say "publishable" for a service_role key (or the
        # reverse), and `masked` must really be masked (contains MASK_FILL "****").
        # MS5 approval note 4 (ADR-038): every role in recon.SECRET_JWT_ROLES (roles that are
        # superuser or BYPASSRLS in a stock Supabase project, measured) is a secret key.
        from rlsentry.contracts.recon import SECRET_JWT_ROLES  # local: recon imports this module
        fixed = {"jwt:anon": "publishable", "sb_publishable": "publishable", "sb_secret": "secret"}
        fixed.update({f"jwt:{r}": "secret" for r in SECRET_JWT_ROLES})
        expected = fixed.get(self.label, "unverified")
        if self.kind != expected:
            raise ValueError(f"label {self.label} requires kind {expected}")
        if "****" not in self.masked:
            raise ValueError("masked must contain the mask fill")
        return self


class Target(_Strict):
    """M2: one attack-surface entry (table, view or RPC)."""

    name: str
    kind: str = Field(pattern=r"^(table|view|rpc)$")
    columns: list[str] = []
    primary_key: list[str] = []
    required: list[str] = []          # ADR-034: NOT NULL columns without default (OpenAPI)
    column_formats: dict[str, str] = {}  # ADR-034: column → OpenAPI `format` (uuid, text, …)
    discovered_by: str = Field(pattern=r"^(openapi|bundle|policy)$")
    confidence: str = Field(pattern=r"^(confirmed|inferred|unknown)$")


class ProbeResult(_Strict):
    """M3: one cell of the access matrix (target × role × op).

    known_rows_checked counts the known rows the verdict rests on (ADR-006, ADR-014):
    for reads, known primary keys queried; for UPDATE/DELETE, seeded rows whose final state
    was read back; for INSERT, the canary whose presence (allowed) or absence (denied) was
    verified by a reader that could see it (owner identity, or the lab DB).
    """

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
    # ADR-044 (M5, FR-12): filled by report.enrich; None/[] until then.
    title: str | None = None          # RULES[rule].description
    repro: str | None = None          # curl reproduction command, keys masked (NFR-03)
    references: list[str] = []        # documentation links (report.REFERENCES)

    @model_validator(mode="after")
    def _known_rule(self) -> Finding:
        # Rule ids are part of the report format (ADR-008); an unknown id is a bug, not data.
        from rlsentry.contracts.rules import RULES  # local import: rules imports this module
        if self.rule not in RULES:
            raise ValueError(f"unknown rule {self.rule!r}")
        return self


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
    chunks_skipped: list[str] = []   # ADR-036: "<url> (<reason>)"; the scope is never claimed complete


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
    write_hosts: list[str] = []      # ADR-017: remote hosts this run may write to (ci only)
    # ADR-043 (MS5 audit S4): the Supabase API URL every API request of this run went to, and
    # who named it: the config file (`supabase_url`) or the CLI flag `--supabase-url`. Never
    # a URL taken from the target's bundle alone. None until the pipeline resolves it.
    supabase_url: str | None = None
    supabase_url_method: str | None = Field(default=None, pattern=r"^(config|cli_flag)$")


class PolicyRow(_Strict):
    """M4: one pg_policies entry (SPEC §5 M4 第 2 點; ADR-032). Policy DDL text, never row data."""

    schema_: str = Field(alias="schema")
    table: str
    name: str
    command: str                      # ALL | SELECT | INSERT | UPDATE | DELETE
    roles: list[str]
    permissive: bool
    using: str | None = None          # pg_policies.qual
    with_check: str | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
    policies: list[PolicyRow] = []    # M4 (SPEC §5 M4 第 2 點; ADR-032): pg_policies conditions
    # ADR-042: modules that ran ("M1".."M5"), why some did not / what was skipped (no secrets,
    # URLs via report_url), and seconds spent per module ("M1".."M4").
    modules: list[str] = []
    notes: list[str] = []
    timings: dict[str, float] = {}
