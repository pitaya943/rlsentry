"""probe/verdict.py write verdict (SPEC §5 M3 writes; ADR-029). Contract: contracts/probe.py
(forbidden_write, write_outcome, write_cell). Pure, no I/O."""
import pytest

from rlsentry.contracts.models import Op, Outcome, Role
from rlsentry.contracts.policy import RowScope
from rlsentry.contracts.probe import (
    WRITE_NOT_FORBIDDEN_REASON,
    ReadBack,
    WriteAttempt,
    WriteObservation,
    WritePlan,
)
from rlsentry.probe.verdict import forbidden_write, write_cell, write_outcome

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest.mark.parametrize("scope,actor,owner,public,forbidden", [
    (RowScope.DENY, None, A, False, True),            # anon cannot write at all
    (RowScope.ALL, None, A, False, False),            # anon may (not forbidden)
    (RowScope.OWN_ROWS_ONLY, A, B, False, True),       # user_a writing a row owned by B
    (RowScope.OWN_ROWS_ONLY, A, A, False, False),      # user_a writing its own row
    (RowScope.PUBLIC_OR_OWN_ROWS, A, B, False, True),  # non-public, not own
    (RowScope.PUBLIC_ROWS_ONLY, A, B, True, False),    # public row is permitted
])
def test_forbidden_write_is_negation_of_permitted(scope: RowScope, actor: str | None,
                                                   owner: str, public: bool, forbidden: bool) -> None:
    assert forbidden_write(scope, actor, owner, public) is forbidden


@pytest.mark.parametrize("op,after,expected", [
    (Op.INSERT, True, True), (Op.INSERT, False, False), (Op.INSERT, None, None),
    (Op.UPDATE, True, True), (Op.UPDATE, False, False), (Op.UPDATE, None, None),
    (Op.DELETE, False, True), (Op.DELETE, True, False), (Op.DELETE, None, None),
])
def test_write_outcome_reads_only_the_after_state(op: Op, after: bool | None,
                                                  expected: bool | None) -> None:
    # DELETE took effect iff the row is now absent; INSERT/UPDATE iff the end state is present.
    assert write_outcome(op, after) is expected


def plan(op: Op = Op.UPDATE) -> WritePlan:
    return WritePlan(op=op, actor=Role.USER_A, rule="CROSS_TENANT_WRITE", reader=Role.USER_B,
                     work_owner=Role.USER_B, text_column="body")


def obs(op: Op = Op.UPDATE, *, has_plan: bool = True, attempt: WriteAttempt | None = None,
        after: ReadBack | None = None, note: str | None = None) -> WriteObservation:
    return WriteObservation(target="t", role=Role.USER_A, op=op, plan=plan(op) if has_plan else None,
                            attempt=attempt, after=after, note=note)


def at(status: int | None = 200) -> WriteAttempt:
    return WriteAttempt(status=status, curl=f"curl {status}", new_pk="np", new_value="rlsentry_canary_x")


def rb(present: bool | None, status: int | None = 200) -> ReadBack:
    return ReadBack(present=present, status=status, curl="curl head")


def test_no_plan_is_not_tested() -> None:
    c = write_cell(WriteObservation(target="t", role=Role.USER_A, op=Op.UPDATE, plan=None))
    assert c.outcome is Outcome.NOT_TESTED and c.known_rows_checked == 0
    assert c.reason == WRITE_NOT_FORBIDDEN_REASON and c.evidence_curl == ""


def test_no_plan_uses_note_when_present() -> None:
    c = write_cell(WriteObservation(target="t", role=Role.ANON, op=Op.INSERT, plan=None,
                                    note="no reader"))
    assert c.outcome is Outcome.NOT_TESTED and c.reason == "no reader"


def test_attempt_or_readback_missing_is_inconclusive() -> None:
    assert write_cell(obs(attempt=None, after=rb(True))).outcome is Outcome.INCONCLUSIVE
    assert write_cell(obs(attempt=at(), after=None)).outcome is Outcome.INCONCLUSIVE


def test_untrustworthy_readback_is_inconclusive_never_denied() -> None:
    c = write_cell(obs(attempt=at(201), after=rb(None, status=403)))
    assert c.outcome is Outcome.INCONCLUSIVE and c.known_rows_checked == 0
    assert c.http_status == 201


def test_effect_verified_is_allowed() -> None:
    c = write_cell(obs(Op.UPDATE, attempt=at(200), after=rb(True)))
    assert c.outcome is Outcome.ALLOWED and c.known_rows_checked == 1 and c.op is Op.UPDATE
    assert c.evidence_curl == "curl 200"


def test_two_xx_without_effect_is_denied_not_allowed() -> None:
    # SPEC §5 M3: USING filters an UPDATE/DELETE to 0 rows, PostgREST still answers 2xx.
    c = write_cell(obs(Op.UPDATE, attempt=at(200), after=rb(False)))
    assert c.outcome is Outcome.DENIED and c.known_rows_checked == 1


def test_delete_absent_after_is_allowed() -> None:
    c = write_cell(obs(Op.DELETE, attempt=at(200), after=rb(False)))
    assert c.outcome is Outcome.ALLOWED
    assert write_cell(obs(Op.DELETE, attempt=at(200), after=rb(True))).outcome is Outcome.DENIED
