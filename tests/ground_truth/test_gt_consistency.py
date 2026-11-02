"""Ground truth agrees with its own intended policy (T-024).

Catches the architect's own mistakes: a case labelled "vulnerable" must be forbidden by the
scenario's `policy`, a "safe" case must agree with it, and a `denied` verdict may only rest on
rows some test user can actually see (SPEC §5 M3: count = 0 is not denied).
"""
from pathlib import Path

import pytest
import yaml

from rlsentry.contracts.ground_truth import LAB_USERS, Case, CaseKind, GroundTruth, SeedRow
from rlsentry.contracts.models import Op, Outcome, Role
from rlsentry.contracts.rules import RULES, SENSITIVE_COLUMN_PATTERNS
from rlsentry.policy.resolve import resolve_expected
from rlsentry.policy.visibility import row_permitted

LAB = Path(__file__).resolve().parents[2] / "lab"
GTS = [GroundTruth.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
       for p in sorted(LAB.glob("*/expected.yaml"))]


def _uid(role: Role | None) -> str | None:
    return LAB_USERS[role]["id"] if role in LAB_USERS else None


def _permitted(gt: GroundTruth, c: Case) -> list[bool]:
    """Per touched row (incl. the row a write creates), is it permitted by the policy?"""
    assert c.target and c.op and c.role
    cols = tuple(gt.schema_[c.target].columns)
    e = resolve_expected(gt.policy, c.target, c.op, c.role, cols)
    assert not e.is_review, f"{c.id}: ground truth must be judgeable ({e.review_reason})"
    rows = [gt.rows[r] for r in c.rows]
    if c.op is Op.INSERT or c.new_owner is not None:
        public = rows[0].public if rows else False
        rows.append(SeedRow(target=c.target, pk="new", owner=c.new_owner, public=public))
    return [row_permitted(e.scope, _uid(c.role), _uid(r.owner), r.public) for r in rows]


def _access(cases: list[Case]) -> list[Case]:
    return [c for c in cases if c.kind is CaseKind.ACCESS]


def _ids(kind: str) -> list[tuple[GroundTruth, Case]]:
    return [(g, c) for g in GTS for c in _access(getattr(g, kind))]


@pytest.mark.parametrize(("gt", "case"), _ids("vulnerable_cases"),
                         ids=[c.id for _, c in _ids("vulnerable_cases")])
def test_vulnerable_cases_are_forbidden_by_policy(gt: GroundTruth, case: Case) -> None:
    assert not all(_permitted(gt, case)), f"{case.id}: policy already allows it"


@pytest.mark.parametrize(("gt", "case"), _ids("safe_cases"), ids=[c.id for _, c in _ids("safe_cases")])
def test_safe_cases_agree_with_policy(gt: GroundTruth, case: Case) -> None:
    perm = _permitted(gt, case)
    if case.expect is Outcome.ALLOWED:
        assert all(perm), f"{case.id}: expected allowed but policy forbids a row"
    else:
        assert not all(perm), f"{case.id}: expected denied but policy permits it"
        if case.op is Op.SELECT:
            assert not any(perm), f"{case.id}: a denied read lists a permitted row"


def _knowable(gt: GroundTruth, row: SeedRow) -> bool:
    """Some test user may see this row under the policy (so its PK can be learned in audit)."""
    for role in (Role.USER_A, Role.USER_B):
        for name, ent in gt.schema_.items():
            if name == row.target or ent.base == row.target:
                e = resolve_expected(gt.policy, name, Op.SELECT, role, tuple(ent.columns))
                if not e.is_review and row_permitted(e.scope, _uid(role), _uid(row.owner), row.public):
                    return True
    return False


@pytest.mark.parametrize(("gt", "case"), _ids("safe_cases"), ids=[c.id for _, c in _ids("safe_cases")])
def test_denied_reads_rest_on_knowable_rows(gt: GroundTruth, case: Case) -> None:
    if case.op is Op.SELECT and case.expect is Outcome.DENIED:
        for r in case.rows:
            assert _knowable(gt, gt.rows[r]), f"{case.id}: nobody can see {r}; use inconclusive"


@pytest.mark.parametrize(("gt", "case"), _ids("inconclusive_cases"),
                         ids=[c.id for _, c in _ids("inconclusive_cases")])
def test_inconclusive_cases_have_no_knowable_forbidden_row(gt: GroundTruth, case: Case) -> None:
    assert case.target and case.role
    ent = gt.schema_[case.target]
    e = resolve_expected(gt.policy, case.target, Op.SELECT, case.role, tuple(ent.columns))
    for name, row in gt.rows.items():
        if row.target in (case.target, ent.base):
            forbidden = not row_permitted(e.scope, _uid(case.role), _uid(row.owner), row.public)
            assert not (forbidden and _knowable(gt, row)), f"{case.id}: {name} makes it decidable"


@pytest.mark.parametrize(("gt", "case"), _ids("vulnerable_cases"),
                         ids=[c.id for _, c in _ids("vulnerable_cases")])
def test_rule_role_and_severity_are_coherent(gt: GroundTruth, case: Case) -> None:
    assert case.rule and case.severity
    spec = RULES[case.rule]
    if case.rule.startswith("ANON_"):
        assert case.role is Role.ANON
    if case.rule.startswith("CROSS_TENANT_"):
        assert case.role in (Role.USER_A, Role.USER_B)
    if case.rule == "CROSS_TENANT_READ" or case.rule == "ANON_READ_OWNER_SCOPED":
        assert case.op is Op.SELECT
    sensitive = any(p in col.lower() for col in gt.schema_[case.target or ""].columns
                    for p in SENSITIVE_COLUMN_PATTERNS)
    want = spec.escalates_to if (spec.escalates_to and sensitive) else spec.severity
    assert case.severity is want, f"{case.id}: severity {case.severity} != {want}"
