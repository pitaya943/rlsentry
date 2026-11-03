"""Expected access policy and `rlsentry.yaml` (SPEC §6 設定檔). Owned by the architect.

The expected policy states what *should* be possible: table × op × role → row scope. M3
compares it with what is actually possible (FR-10). The same format is the `policy:` section
of every lab ground truth file (ADR-009), so the benchmark feeds the scanner exactly what a
user would write.

Implementations of the functions declared at the bottom live in rlsentry/policy/.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rlsentry.contracts.models import Evidence, Op, Profile, Role, Severity


class RowScope(str, Enum):
    """Which rows a role may touch (SPEC §6 comment above `tables:`)."""

    DENY = "deny"
    ALL = "all"
    OWN_ROWS_ONLY = "own_rows_only"
    PUBLIC_ROWS_ONLY = "public_rows_only"
    PUBLIC_OR_OWN_ROWS = "public_or_own_rows"


NEEDS_OWNER: frozenset[RowScope] = frozenset({RowScope.OWN_ROWS_ONLY, RowScope.PUBLIC_OR_OWN_ROWS})
NEEDS_PUBLIC: frozenset[RowScope] = frozenset({RowScope.PUBLIC_ROWS_ONLY, RowScope.PUBLIC_OR_OWN_ROWS})

OWNER_COLUMN_CANDIDATES: tuple[str, ...] = ("user_id", "owner_id", "author_id", "created_by")
"""Column names treated as the owner column of tables not listed in the policy (SPEC §6
`rlsentry init`). Checked in this order; exact, case-sensitive match."""

PUBLIC_COLUMN_CANDIDATES: tuple[str, ...] = ("is_public", "is_published")
"""Boolean column names treated as the public flag of unlisted tables (SPEC §6)."""


class _Strict(BaseModel):
    # extra="forbid": a typo such as `selct:` must be an error, never a silently ignored rule.
    model_config = ConfigDict(extra="forbid")


class RoleScopes(_Strict):
    """Scopes for one operation. A missing role falls back to `defaults` (SPEC §6)."""

    anon: RowScope | None = None
    user: RowScope | None = None     # applies to both user_a and user_b


class TablePolicy(_Strict):
    """One table, view or RPC (ADR-007). `primary_key` is an addition (ADR-014): it tells the
    scanner which column identifies rows when OpenAPI is unavailable (L12) or does not describe
    the target (RPC results). Without it and without OpenAPI, cells are inconclusive; the
    scanner never guesses a column name."""

    primary_key: list[str] | None = None
    owner_column: str | None = None
    public_column: str | None = None
    select: RoleScopes | None = None
    insert: RoleScopes | None = None
    update: RoleScopes | None = None
    delete: RoleScopes | None = None


class DefaultScopes(_Strict):
    """Fallback for unlisted tables and operations. SPEC default: anon deny, user own_rows_only."""

    anon: RowScope = RowScope.DENY
    user: RowScope = RowScope.OWN_ROWS_ONLY


class ExpectedPolicy(_Strict):
    """The `tables:` + `defaults:` part of rlsentry.yaml; also `policy:` in expected.yaml."""

    tables: dict[str, TablePolicy] = {}
    defaults: DefaultScopes = DefaultScopes()


class TestUser(_Strict):
    """A test account. Passwords are referenced by env var name only, never stored (SPEC §6)."""

    __test__ = False   # not a pytest test class despite the name

    name: Role
    email: str
    password_env: str = Field(pattern=r"^[A-Z_][A-Z0-9_]*$")

    @field_validator("name")
    @classmethod
    def _not_anon(cls, v: Role) -> Role:
        if v is Role.ANON:
            raise ValueError("test users are user_a / user_b; anon needs no account")
        return v


class FailOn(_Strict):
    """CI exit-code threshold (FR-13). Default: Confirmed and severity >= high (SPEC §5 M5)."""

    evidence: Evidence = Evidence.CONFIRMED
    severity: Severity = Severity.HIGH


class ScanConfig(ExpectedPolicy):
    """Whole rlsentry.yaml. Defaults are the safe choice: not authorized, audit (read-only)."""

    target: str = Field(pattern=r"^https?://")
    authorized: bool = False                 # NFR-02; the CLI flag can also confirm
    profile: Profile = Profile.AUDIT         # ADR-010: read-only unless the user opts in
    rate_limit_rps: float = Field(default=5.0, gt=0)   # NFR-04
    test_users: list[TestUser] = []
    db_url_env: str | None = None            # enables M4 when set
    fail_on: FailOn = FailOn()
    write_hosts: list[str] = []              # ADR-017: remote hosts ci may write to (exact)

    @field_validator("write_hosts")
    @classmethod
    def _exact_hosts(cls, v: list[str]) -> list[str]:
        # Imported here: safety.py imports this module, so a top-level import would be circular.
        from rlsentry.contracts.safety import WRITE_HOST_RE
        out: list[str] = []
        for i, raw in enumerate(v):
            host = raw.lower()
            if not WRITE_HOST_RE.match(host):
                raise ValueError(f"write_hosts[{i}] must be a bare host or host:port, "
                                 "without scheme, path or wildcard (ADR-017)")
            if host not in out:
                out.append(host)
        return out

    @model_validator(mode="after")
    def _unique_users(self) -> ScanConfig:
        names = [u.name for u in self.test_users]
        if len(names) != len(set(names)):
            raise ValueError("test_users names must be unique")
        return self

    @property
    def policy(self) -> ExpectedPolicy:
        return ExpectedPolicy(tables=self.tables, defaults=self.defaults)


class ConfigError(ValueError):
    """Raised by load_config. The message names the offending key path, or for YAML syntax
    errors the line and column and the kind of error; it never quotes file content, because
    a user may have pasted a secret into the file by mistake (NFR-03, auditor F5)."""


class ExpectedAccess(_Strict):
    """Result of resolve_expected for one cell (target × op × role).

    `scope` is the effective scope after applying defaults and the anon simplification
    (for anon, own_rows_only ≡ deny and public_or_own_rows ≡ public_rows_only, because anon
    owns no rows). `review_reason` is set when the scope needs an owner or public column that
    is unknown: such a cell must yield a Review hint, never a vulnerability (SPEC §6).
    """

    target: str
    op: Op
    role: Role
    scope: RowScope
    owner_column: str | None = None
    public_column: str | None = None
    review_reason: str | None = None

    @property
    def is_review(self) -> bool:
        return self.review_reason is not None


# --- function contracts (implemented in rlsentry/policy/, tickets T-021..T-023) -----------

def resolve_expected(policy: ExpectedPolicy, target: str, op: Op, role: Role,
                     columns: tuple[str, ...] = ()) -> ExpectedAccess:
    """Contract only; implemented by rlsentry.policy.resolve.resolve_expected.

    Rules, in order:
    1. Role key: anon → `anon`; user_a, user_b → `user`.
    2. Listed table: scope = tables[target].<op>.<role key>; when the op or the role key is
       missing, use defaults.<role key>. owner/public columns come from the table entry only.
    3. Unlisted table: scope = defaults.<role key>; owner column = first of
       OWNER_COLUMN_CANDIDATES present in `columns`; public column likewise from
       PUBLIC_COLUMN_CANDIDATES.
    4. Anon simplification (see ExpectedAccess).
    5. review_reason is set iff the effective scope is in NEEDS_OWNER without an owner column,
       or in NEEDS_PUBLIC without a public column.
    """
    raise NotImplementedError


def row_permitted(scope: RowScope, actor_id: str | None, owner_id: str | None,
                  is_public: bool) -> bool:
    """Contract only; implemented by rlsentry.policy.visibility.row_permitted.

    Whether a role may touch one row under `scope`. actor_id is None for anon; owner_id is
    None for rows without an owner. "Own" means both ids are non-None and equal.
    deny → False; all → True; own_rows_only → own; public_rows_only → is_public;
    public_or_own_rows → is_public or own.
    """
    raise NotImplementedError


def load_config(text: str) -> ScanConfig:
    """Contract only; implemented by rlsentry.policy.load.load_config.

    Parse rlsentry.yaml text with yaml.safe_load and validate it as ScanConfig. Every failure
    (YAML syntax, not a mapping, validation) raises ConfigError whose message names the
    offending key path (e.g. "tables.posts.select.anon") or, for YAML syntax errors, the
    line/column ("line 3, column 5") and the problem kind; never a snippet of the input.
    Environment variables are NOT read.
    """
    raise NotImplementedError
