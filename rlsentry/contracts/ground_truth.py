"""Ground-truth format for lab scenarios (lab/<id>/expected.yaml) and the benchmark output.

Owned by the architect. SPEC §8 gives the core (`vulnerable_cases`, `safe_cases`,
`inconclusive_cases`, `splinter_expected`); ADR-009 adds what the lab and the benchmark need to
be reproducible: `schema` and `rows` (what lab-dev must build and seed, with fixed primary
keys), `policy` (the intended access policy fed to the scanner), `warning_cases` and
`discovery_cases`.

Scoring (ADR-011), per scenario and summed over all P0 scenarios:
- a *cell* is (kind, target, op, role); a vulnerable case matches a Finding when evidence is
  confirmed and target, op, role and rule are all equal (key cases: rule only);
- TP = vulnerable cases with ≥1 matching finding; FN = the rest;
- FP = confirmed findings with `RULES[rule].vulnerability` that match no vulnerable case
  (this includes every confirmed finding on a safe cell, and findings the ground truth does
  not foresee — those are reported for human review, never silently dropped);
- TN = safe cases whose cell has no confirmed finding; FPR = (#safe cases hit)/(#safe cases);
- inconclusive cases pass iff the reported cell outcome is inconclusive and the cell has no
  confirmed finding (an inconclusive cell reported as denied is a violation, SPEC §8 C03/C04);
- cases are scored only in the profiles they list; bench runs `dev` for scoring and `audit`
  for the read-only and inconclusive checks.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rlsentry.contracts.models import Evidence, Op, Outcome, Profile, Role, Severity
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.rules import RULES

SCENARIO_IDS: tuple[str, ...] = tuple(
    [f"L{i:02d}" for i in range(1, 13)] + [f"C{i:02d}" for i in range(1, 5)]
)
"""The 16 scenarios of SPEC §8. Directory names are lab/<id>_<slug>/."""

LAB_USERS: dict[Role, dict[str, str]] = {
    Role.USER_A: {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "email": "a@test.dev",
                  "password_env": "RLS_A_PW"},
    Role.USER_B: {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "email": "b@test.dev",
                  "password_env": "RLS_B_PW"},
}
"""Fixed test accounts seeded in every scenario (auth.users ids), same emails as SPEC §6."""

KEY_TARGET_RE = re.compile(r"^(jwt:[a-z_]+|sb_secret|sb_publishable|unverified)$")
"""`target` of key cases and of M1 findings: the JWT `role` claim (jwt:anon, jwt:service_role)
or the key format. M1 sets Finding.target to this label so a misclassified anon key can never
be credited as the detected secret key (ADR-011)."""

ROW_PK_RE = re.compile(r"^5ce0[1c]0\d{2}-0000-4000-8000-\d{12}$")
"""Seed row primary keys: 5ce0<S><NNN>-0000-4000-8000-<row:012d>, S = 1 (L) or c (C), e.g.
L04 row 1 → 5ce01004-0000-4000-8000-000000000001. Readable in DB logs and unique per scenario."""


def row_pk(scenario: str, n: int) -> str:
    """Primary key of seed row `n` of `scenario` (format ROW_PK_RE)."""
    s = "1" if scenario.startswith("L") else "c"
    return f"5ce0{s}0{scenario[1:]}-0000-4000-8000-{n:012d}"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseKind(str, Enum):
    ACCESS = "access"        # table / view / rpc cell probed through PostgREST
    KEY = "key"              # key found in the frontend bundle (M1)
    STORAGE = "storage"      # Storage bucket object (P2)


class SchemaEntry(_Strict):
    """What lab-dev must create. `base` is the table a view or RPC exposes rows of."""

    kind: Literal["table", "view", "rpc", "bucket"]
    columns: list[str] = []
    primary_key: list[str] = []
    rls: Literal["enabled", "disabled", "n/a"] = "enabled"
    base: str | None = None
    security_definer: bool = False
    in_openapi: bool = True      # L12: False when OpenAPI is restricted
    in_bundle: bool = True       # referenced by the frontend via .from()/.rpc()


class SeedRow(_Strict):
    """One seeded row. Owner is a role, mapped to LAB_USERS ids; None = no owner."""

    target: str                  # table (or bucket) that stores the row
    pk: str                      # ROW_PK_RE for tables; object path for buckets
    owner: Role | None = None
    public: bool = False


class Case(_Strict):
    """One ground-truth case.

    `expect` states whether the listed `rows` are reachable by `role` with `op` in the planted
    lab (MS1 verifies this against the running lab). For write ops `rows` names rows *like*
    the ones written (the scanner may seed its own equivalents, SPEC §5 M3); `new_owner` is
    the owner the write sets (insert payload, or the changed owner column of an update).
    Inconclusive cases instead require the scanner's cell outcome to be inconclusive: no row
    that the policy forbids for that role is knowable (none exists, or nobody can see it).
    A `denied` safe case therefore only lists rows some test user can see or seed.
    """

    id: str                                  # <scenario>-V/S/I/W<n>, unique in the file
    kind: CaseKind = CaseKind.ACCESS
    target: str | None = None
    op: Op | None = None
    role: Role | None = None
    rows: list[str] = []
    new_owner: Role | None = None
    expect: Outcome | None = None
    rule: str | None = None
    evidence: Evidence = Evidence.CONFIRMED
    severity: Severity | None = None
    key_kind: Literal["publishable", "secret", "unverified"] | None = None
    precondition: str | None = None          # e.g. "user_metadata.role=admin" (L03)
    profiles: list[Profile] = [Profile.DEV, Profile.CI, Profile.AUDIT]

    @property
    def cell(self) -> tuple[str, str | None, str | None, str | None]:
        return (self.kind.value, self.target, self.op.value if self.op else None,
                self.role.value if self.role else None)

    @model_validator(mode="after")
    def _shape(self) -> Case:
        if self.kind is CaseKind.KEY:
            if self.key_kind is None or not KEY_TARGET_RE.match(self.target or "") \
                    or self.op or self.role or self.rows:
                raise ValueError(f"{self.id}: key case needs key_kind and a KEY_TARGET_RE target only")
        else:
            if not (self.target and self.op and self.role and self.expect):
                raise ValueError(f"{self.id}: access/storage case needs target, op, role, expect")
            if self.op in (Op.INSERT, Op.UPDATE, Op.DELETE) and Profile.AUDIT in self.profiles:
                raise ValueError(f"{self.id}: write cases cannot run in audit (NFR-01)")
            if self.op is Op.INSERT and self.rows:
                raise ValueError(f"{self.id}: insert cases describe the new row via new_owner")
        if self.rule is not None and self.rule not in RULES:
            raise ValueError(f"{self.id}: unknown rule {self.rule}")
        return self


class Discovery(_Strict):
    """Expected M2 result for one target (FR-04/FR-05)."""

    target: str
    discovered_by: Literal["openapi", "bundle", "policy"]
    confidence: Literal["confirmed", "inferred", "unknown"]


class GroundTruth(_Strict):
    scenario: str
    title: str
    priority: Literal["P0", "P1", "P2"] = "P0"   # P2 scenarios are reported but not scored
    plant: str                                   # how the bug (or its absence) is built
    openapi: bool = True                         # False: anon OpenAPI access is disabled (L12)
    schema_: dict[str, SchemaEntry] = Field(alias="schema")
    rows: dict[str, SeedRow] = {}
    policy: ExpectedPolicy
    vulnerable_cases: list[Case] = []
    safe_cases: list[Case] = []
    inconclusive_cases: list[Case] = []
    warning_cases: list[Case] = []
    discovery_cases: list[Discovery] = []
    splinter_expected: Literal["measure", "reported", "not_reported"] = "measure"

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _consistent(self) -> GroundTruth:
        """Structural integrity only; agreement with `policy` is checked in tests (T-024)."""
        errs: list[str] = []
        if self.scenario not in SCENARIO_IDS:
            errs.append(f"unknown scenario {self.scenario}")
        all_cases = (self.vulnerable_cases + self.safe_cases + self.inconclusive_cases
                     + self.warning_cases)
        ids = [c.id for c in all_cases]
        if len(ids) != len(set(ids)):
            errs.append("case ids must be unique")
        for c in all_cases:
            if not c.id.startswith(self.scenario + "-"):
                errs.append(f"{c.id}: id must start with {self.scenario}-")
            if c.kind is not CaseKind.KEY and c.target not in self.schema_:
                errs.append(f"{c.id}: target {c.target} not in schema")
            errs += [f"{c.id}: unknown row {r}" for r in c.rows if r not in self.rows]
            for r in c.rows:
                row = self.rows.get(r)
                ent = self.schema_.get(c.target or "")
                if row and ent and row.target not in (c.target, ent.base):
                    errs.append(f"{c.id}: row {r} is not stored in {c.target} or its base")
        for c in self.vulnerable_cases:
            if c.expect not in (None, Outcome.ALLOWED) or not c.rule or not c.severity:
                errs.append(f"{c.id}: vulnerable case needs expect allowed, rule, severity")
            if c.rule and not RULES[c.rule].vulnerability:
                errs.append(f"{c.id}: rule {c.rule} is not a vulnerability rule")
        for c in self.safe_cases:
            if c.expect not in (None, Outcome.ALLOWED, Outcome.DENIED) or c.rule:
                errs.append(f"{c.id}: safe case expects allowed/denied and has no rule")
        for c in self.inconclusive_cases:
            if c.expect is not Outcome.INCONCLUSIVE:
                errs.append(f"{c.id}: inconclusive case must expect inconclusive")
        for c in self.warning_cases:
            if c.evidence is Evidence.CONFIRMED or not c.rule or not c.severity:
                errs.append(f"{c.id}: warning case needs a non-confirmed evidence, rule, severity")
        vuln_cells = {c.cell for c in self.vulnerable_cases}
        scored = self.safe_cases + self.inconclusive_cases
        clash = [c.id for c in scored if c.cell in vuln_cells]
        if clash:
            errs.append(f"cells both vulnerable and safe/inconclusive: {clash}")
        cells = [c.cell for c in scored]
        if len(cells) != len(set(cells)):
            errs.append("each safe/inconclusive cell may appear once")
        for name, row in self.rows.items():
            if self.schema_.get(row.target, None) is None:
                errs.append(f"row {name}: target {row.target} not in schema")
            elif self.schema_[row.target].kind == "table" and not ROW_PK_RE.match(row.pk):
                errs.append(f"row {name}: pk {row.pk} does not match ROW_PK_RE")
        if errs:
            raise ValueError("; ".join(errs))
        return self


# --- benchmark output (logs/bench.json, SPEC §9) -----------------------------------------

class CaseResult(_Strict):
    case_id: str
    verdict: Literal["tp", "fn", "tn", "fp", "inconclusive_ok", "inconclusive_violation",
                     "warning_seen", "warning_missing"]
    detail: str = ""


class ScenarioResult(_Strict):
    scenario: str
    profile: Profile
    scored: bool                       # False for P2 scenarios
    cases: list[CaseResult] = []
    unmatched_findings: list[str] = []  # Finding.id of confirmed findings matching no case
    runtime_s: float


class BenchReport(_Strict):
    """Exactly the keys SPEC §9 requires, plus the raw counts behind each ratio."""

    tp: int
    fp: int
    fn: int
    tn: int
    recall: float
    precision: float
    fpr: float
    coverage: float                    # tested cells / cells that should be tested
    inconclusive_ratio: float
    runtime: dict[str, float]          # "5", "20", "50" tables → seconds
    scenarios: list[ScenarioResult]
