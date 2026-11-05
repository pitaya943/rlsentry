"""probe/diff.py write_findings, cleanup_findings (FR-10; ADR-029). Contract: contracts/probe.py."""
from rlsentry.contracts.models import Evidence, Op, Outcome, ProbeResult, Role, Severity, Target, finding_id
from rlsentry.contracts.probe import ReadBack, SeededRow, WriteAttempt, WriteObservation, WritePlan
from rlsentry.probe.diff import cleanup_findings, write_findings


def tgt() -> Target:
    return Target(name="customers", kind="table", columns=["id", "owner_id", "name"],
                  primary_key=["id"], discovered_by="openapi", confidence="confirmed")


def obs(rule: str, actor: Role, op: Op) -> WriteObservation:
    plan = WritePlan(op=op, actor=actor, rule=rule, reader=Role.USER_A)
    return WriteObservation(target="customers", role=actor, op=op, plan=plan,
                            attempt=WriteAttempt(status=201, curl="c"), after=ReadBack(present=True, status=200, curl="h"))


def cell(outcome: Outcome, actor: Role, op: Op) -> ProbeResult:
    known = 1 if outcome in (Outcome.ALLOWED, Outcome.DENIED) else 0
    return ProbeResult(target="customers", role=actor, op=op, outcome=outcome,
                       known_rows_checked=known, reason="r", evidence_curl="c")


def test_allowed_write_becomes_a_vulnerability_finding() -> None:
    (f,) = write_findings(tgt(), obs("ANON_WRITE", Role.ANON, Op.INSERT), cell(Outcome.ALLOWED, Role.ANON, Op.INSERT))
    assert f.rule == "ANON_WRITE" and f.evidence is Evidence.CONFIRMED and f.severity is Severity.CRITICAL
    assert f.role is Role.ANON and f.op is Op.INSERT and f.target == "customers"
    assert f.id == finding_id("customers", Role.ANON, Op.INSERT, "ANON_WRITE")


def test_cross_tenant_write_is_high() -> None:
    (f,) = write_findings(tgt(), obs("CROSS_TENANT_WRITE", Role.USER_A, Op.UPDATE),
                          cell(Outcome.ALLOWED, Role.USER_A, Op.UPDATE))
    assert f.rule == "CROSS_TENANT_WRITE" and f.severity is Severity.HIGH


def test_denied_inconclusive_not_tested_give_no_finding() -> None:
    for outcome in (Outcome.DENIED, Outcome.INCONCLUSIVE, Outcome.NOT_TESTED):
        assert write_findings(tgt(), obs("ANON_WRITE", Role.ANON, Op.INSERT),
                              cell(outcome, Role.ANON, Op.INSERT)) == []


def test_cleanup_findings_one_per_unremoved_row() -> None:
    rows = [SeededRow(target="customers", pk="p1", owner=Role.USER_A, marker="m"),
            SeededRow(target="customers", pk="p2", owner=Role.USER_B, marker="m")]
    fs = cleanup_findings(tgt(), rows)
    assert [f.rule for f in fs] == ["CLEANUP_FAILED", "CLEANUP_FAILED"]
    assert {f.role for f in fs} == {Role.USER_A, Role.USER_B}
    assert all(f.op is Op.DELETE and f.evidence is not Evidence.CONFIRMED for f in fs)
    assert cleanup_findings(tgt(), []) == []
