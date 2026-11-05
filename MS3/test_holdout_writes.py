"""MS3 holdout: write verdict / planning with DIFFERENT inputs than the visible tests.
Pure, no Docker. Catches a scanner that weakens the three-state write judgement or plans the
wrong forbidden writes. Contract: rlsentry/contracts/probe.py (ADR-029 + 補記)."""
from collections.abc import Mapping

from rlsentry.contracts.models import Op, Outcome, Role
from rlsentry.contracts.policy import ExpectedAccess, RowScope
from rlsentry.contracts.probe import ReadBack, WriteAttempt, WriteObservation, WritePlan
from rlsentry.probe.verdict import forbidden_write, write_cell, write_outcome
from rlsentry.probe.write import plan_writes
from rlsentry.rules.severity import write_rule

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
IDS = {Role.USER_A: A, Role.USER_B: B}
TOK = {Role.ANON: "k", Role.USER_A: "ta", Role.USER_B: "tb"}


def test_write_outcome_delete_is_absence() -> None:
    assert write_outcome(Op.DELETE, False) is True       # gone == took effect
    assert write_outcome(Op.DELETE, True) is False        # still there == denied
    assert write_outcome(Op.INSERT, True) is True
    assert write_outcome(Op.UPDATE, False) is False
    for op in (Op.INSERT, Op.UPDATE, Op.DELETE):
        assert write_outcome(op, None) is None


def _obs(op: Op, after: bool | None, status: int) -> WriteObservation:
    plan = WritePlan(op=op, actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A,
                     work_owner=None if op is Op.INSERT else Role.USER_A)
    return WriteObservation(target="x", role=Role.ANON, op=op,
                            plan=plan, attempt=WriteAttempt(status=status, curl="c"),
                            after=ReadBack(present=after, status=200 if after is not None else 409, curl="h"))


def test_two_xx_without_effect_is_denied() -> None:
    assert write_cell(_obs(Op.UPDATE, False, 200)).outcome is Outcome.DENIED
    assert write_cell(_obs(Op.DELETE, True, 200)).outcome is Outcome.DENIED
    assert write_cell(_obs(Op.INSERT, True, 201)).outcome is Outcome.ALLOWED
    assert write_cell(_obs(Op.UPDATE, None, 200)).outcome is Outcome.INCONCLUSIVE


def test_forbidden_write_public_and_own() -> None:
    assert forbidden_write(RowScope.PUBLIC_ROWS_ONLY, A, B, True) is False   # public row ok
    assert forbidden_write(RowScope.PUBLIC_ROWS_ONLY, A, B, False) is True
    assert forbidden_write(RowScope.ALL, None, A, False) is False
    assert forbidden_write(RowScope.DENY, A, A, True) is True


def test_write_rule_mapping() -> None:
    assert write_rule(Role.ANON, Op.DELETE) == "ANON_WRITE"
    assert write_rule(Role.USER_B, Op.INSERT) == "CROSS_TENANT_WRITE"


def _scopes(ins: RowScope, upd: RowScope, dele: RowScope) -> dict[tuple[Op, Role], ExpectedAccess]:
    by = {Op.INSERT: ins, Op.UPDATE: upd, Op.DELETE: dele}
    out: dict[tuple[Op, Role], ExpectedAccess] = {}
    for op in (Op.INSERT, Op.UPDATE, Op.DELETE):
        for role in (Role.ANON, Role.USER_A, Role.USER_B):
            # anon denied, users all-allowed except INSERT which stays own_rows_only
            sc = RowScope.DENY if role is Role.ANON else by[op]
            out[(op, role)] = ExpectedAccess(target="t", op=op, role=role, scope=sc, owner_column="owner_id")
    return out


def test_plan_writes_only_forbidden_ops() -> None:
    # users may UPDATE/DELETE anything (all) but only own INSERTs; anon denied everywhere.
    exp: Mapping[tuple[Op, Role], ExpectedAccess] = _scopes(RowScope.OWN_ROWS_ONLY, RowScope.ALL, RowScope.ALL)
    plans = plan_writes(exp, IDS, TOK, "body")
    kinds = {(p.op, p.actor) for p in plans}
    # anon forbidden for every op → 3 anon plans; users only forbidden on cross-tenant INSERT.
    assert (Op.INSERT, Role.ANON) in kinds
    assert (Op.INSERT, Role.USER_A) in kinds and (Op.INSERT, Role.USER_B) in kinds
    # users' UPDATE/DELETE are permitted (scope ALL) → not planned
    assert (Op.UPDATE, Role.USER_A) not in kinds and (Op.DELETE, Role.USER_B) not in kinds
    assert all(p.rule == ("ANON_WRITE" if p.actor is Role.ANON else "CROSS_TENANT_WRITE") for p in plans)
