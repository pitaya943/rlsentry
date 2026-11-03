"""probe/diff.py: finding = actual − expected (FR-10; ADR-023 #3, #4).
Contract: rlsentry/contracts/probe.py (read_findings, target_findings)."""
from rlsentry.contracts.models import (
    Evidence,
    Finding,
    Op,
    Outcome,
    ProbeResult,
    Role,
    Severity,
    Target,
    finding_id,
)
from rlsentry.contracts.policy import ExpectedAccess, RowScope
from rlsentry.contracts.probe import CountResult, ReadObservation
from rlsentry.probe.diff import read_findings, target_findings


def tgt(kind: str = "table", cols: list[str] | None = None, conf: str = "confirmed") -> Target:
    return Target(name="t", kind=kind, columns=cols if cols is not None else ["id", "owner_id", "email"],
                  primary_key=["id"], discovered_by="openapi" if conf == "confirmed" else "bundle", confidence=conf)


def cell(role: Role, outcome: Outcome) -> ProbeResult:
    known = 0 if outcome in (Outcome.INCONCLUSIVE, Outcome.NOT_TESTED) else 2
    return ProbeResult(target="t", role=role, op=Op.SELECT, outcome=outcome, known_rows_checked=known,
                       reason="r", evidence_curl="curl")


def obs(role: Role, permitted: CountResult | None = None, review: str | None = None) -> ReadObservation:
    e = ExpectedAccess(target="t", op=Op.SELECT, role=role, scope=RowScope.PUBLIC_ROWS_ONLY, review_reason=review)
    return ReadObservation(target="t", role=role, expected=e, permitted=permitted)


def rules(fs: list[Finding]) -> list[tuple[str, str, str]]:
    return [(f.rule, f.evidence.value, f.severity.value) for f in fs]


def test_anon_leak_with_sensitive_column_is_critical() -> None:
    c = cell(Role.ANON, Outcome.ALLOWED)
    (f,) = read_findings(tgt(), obs(Role.ANON), c)
    assert (f.rule, f.evidence, f.severity) == ("ANON_READ_OWNER_SCOPED", Evidence.CONFIRMED, Severity.CRITICAL)
    assert (f.target, f.role, f.op, f.probes) == ("t", Role.ANON, Op.SELECT, [c])
    assert f.id == finding_id("t", Role.ANON, Op.SELECT, "ANON_READ_OWNER_SCOPED")


def test_user_and_rpc_leaks() -> None:
    assert rules(read_findings(tgt(), obs(Role.USER_A), cell(Role.USER_A, Outcome.ALLOWED))) == [
        ("CROSS_TENANT_READ", "confirmed", "medium")]
    assert rules(read_findings(tgt("rpc", []), obs(Role.ANON), cell(Role.ANON, Outcome.ALLOWED))) == [
        ("SECURITY_DEFINER_RPC_DATA", "confirmed", "medium")]


def test_denied_and_not_tested_give_nothing() -> None:
    assert read_findings(tgt(), obs(Role.ANON), cell(Role.ANON, Outcome.DENIED)) == []
    assert read_findings(tgt(), obs(Role.USER_B), cell(Role.USER_B, Outcome.NOT_TESTED)) == []


def test_inconclusive_is_reported_never_silent() -> None:
    assert rules(read_findings(tgt(), obs(Role.ANON), cell(Role.ANON, Outcome.INCONCLUSIVE))) == [
        ("INCONCLUSIVE_CELL", "suspected", "review")]
    assert rules(read_findings(tgt(), obs(Role.USER_A, review="no owner"), cell(Role.USER_A, Outcome.INCONCLUSIVE))) == [
        ("NO_OWNER_COLUMN", "suspected", "review")]


def test_permitted_rows_hints() -> None:
    hidden = CountResult(queried=2, status=200, total=1, curl="c")
    assert rules(read_findings(tgt(cols=["id"]), obs(Role.USER_A, hidden), cell(Role.USER_A, Outcome.DENIED))) == [
        ("EXPECTED_ACCESS_DENIED", "config_warning", "review")]
    shown = CountResult(queried=1, status=200, total=1, curl="c")
    assert rules(read_findings(tgt(), obs(Role.ANON, shown), cell(Role.ANON, Outcome.DENIED))) == [
        ("SENSITIVE_COLUMN_PUBLIC", "config_warning", "review")]
    assert read_findings(tgt(), obs(Role.USER_A, shown), cell(Role.USER_A, Outcome.DENIED)) == []
    assert read_findings(tgt(cols=["id", "title"]), obs(Role.ANON, shown), cell(Role.ANON, Outcome.DENIED)) == []
    bad = CountResult(queried=1, status=404, total=None, curl="c")
    assert read_findings(tgt(), obs(Role.ANON, bad), cell(Role.ANON, Outcome.DENIED)) == []


def test_target_findings() -> None:
    (f,) = target_findings(tgt(conf="inferred"))
    assert (f.rule, f.target, f.role, f.op, f.probes) == ("INFERRED_TARGET", "t", None, None, [])
    assert f.id == finding_id("t", None, None, "INFERRED_TARGET")
    assert target_findings(tgt()) == []
    assert target_findings(Target(name="t", kind="table", discovered_by="policy", confidence="unknown")) == []
