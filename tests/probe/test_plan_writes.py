"""probe/write.py plan_writes (SPEC §5 M3 writes; ADR-029 + 補記). Contract: contracts/probe.py.
Pure enumeration of the forbidden writes worth attempting, from the EXPECTED policy. The row a
destructive write needs is seeded at probe time (work_owner), so planning has no seeded rows."""
from collections.abc import Mapping

from rlsentry.contracts.models import Op, Role
from rlsentry.contracts.policy import ExpectedAccess, RowScope
from rlsentry.contracts.probe import USER_ROLES, WRITE_OPS, WritePlan
from rlsentry.probe.write import plan_writes

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
IDS = {Role.USER_A: A, Role.USER_B: B}
TOKENS = {Role.ANON: "anonkey", Role.USER_A: "ta", Role.USER_B: "tb"}


def scopes(user: RowScope, anon: RowScope = RowScope.DENY,
           review: bool = False) -> dict[tuple[Op, Role], ExpectedAccess]:
    out: dict[tuple[Op, Role], ExpectedAccess] = {}
    for op in WRITE_OPS:
        for role in (Role.ANON, *USER_ROLES):
            sc = anon if role is Role.ANON else user
            out[(op, role)] = ExpectedAccess(target="t", op=op, role=role, scope=sc,
                                             owner_column="owner_id",
                                             review_reason="no owner" if review else None)
    return out


def tup(p: WritePlan) -> tuple:
    return (p.op, p.actor, p.rule, p.reader, p.work_owner, p.new_owner, p.transfer, p.text_column)


def run(exp: Mapping[tuple[Op, Role], ExpectedAccess], tokens: dict[Role, str] = TOKENS,
        has_text: bool = True) -> set[tuple]:
    return {tup(p) for p in plan_writes(exp, IDS, tokens, has_text)}


def test_all_denied_policy_plans_every_forbidden_write() -> None:
    assert run(scopes(RowScope.OWN_ROWS_ONLY)) == {
        # INSERT: anon→user_a, user_a→user_b, user_b→user_a (work_owner None; new_owner is reader)
        (Op.INSERT, Role.ANON, "ANON_WRITE", Role.USER_A, None, Role.USER_A, False, None),
        (Op.INSERT, Role.USER_A, "CROSS_TENANT_WRITE", Role.USER_B, None, Role.USER_B, False, None),
        (Op.INSERT, Role.USER_B, "CROSS_TENANT_WRITE", Role.USER_A, None, Role.USER_A, False, None),
        # UPDATE value-change cross-tenant: a fresh row owned by the other user (work_owner)
        (Op.UPDATE, Role.ANON, "ANON_WRITE", Role.USER_A, Role.USER_A, None, False, "body"),
        (Op.UPDATE, Role.USER_A, "CROSS_TENANT_WRITE", Role.USER_B, Role.USER_B, None, False, "body"),
        (Op.UPDATE, Role.USER_B, "CROSS_TENANT_WRITE", Role.USER_A, Role.USER_A, None, False, "body"),
        # UPDATE transfer: actor's own fresh row moved to the other user
        (Op.UPDATE, Role.USER_A, "CROSS_TENANT_WRITE", Role.USER_B, Role.USER_A, Role.USER_B, True, None),
        (Op.UPDATE, Role.USER_B, "CROSS_TENANT_WRITE", Role.USER_A, Role.USER_B, Role.USER_A, True, None),
        # DELETE cross-tenant
        (Op.DELETE, Role.ANON, "ANON_WRITE", Role.USER_A, Role.USER_A, None, False, None),
        (Op.DELETE, Role.USER_A, "CROSS_TENANT_WRITE", Role.USER_B, Role.USER_B, None, False, None),
        (Op.DELETE, Role.USER_B, "CROSS_TENANT_WRITE", Role.USER_A, Role.USER_A, None, False, None),
    }


def test_policy_that_permits_writes_plans_nothing() -> None:
    assert run(scopes(RowScope.ALL, anon=RowScope.ALL)) == set()


def test_review_scope_plans_nothing() -> None:
    assert run(scopes(RowScope.OWN_ROWS_ONLY, review=True)) == set()


def test_ordered_by_op_then_actor() -> None:
    plans = plan_writes(scopes(RowScope.OWN_ROWS_ONLY), IDS, TOKENS, True)
    ops = [p.op for p in plans]
    assert ops == sorted(ops, key=WRITE_OPS.index)


def test_update_value_skipped_without_text_column_transfer_and_delete_remain() -> None:
    got = run(scopes(RowScope.OWN_ROWS_ONLY), has_text=False)
    assert [t for t in got if t[0] is Op.UPDATE and not t[6]] == []   # no value-change plans
    assert any(t[0] is Op.UPDATE and t[6] for t in got)               # transfer remains
    assert any(t[0] is Op.DELETE for t in got)


def test_no_reader_token_means_no_plan() -> None:
    # Without user_b's token nothing whose reader or work_owner is user_b can be set up/verified.
    got = run(scopes(RowScope.OWN_ROWS_ONLY), tokens={Role.ANON: "k", Role.USER_A: "ta"})
    assert all(reader is not Role.USER_B and work is not Role.USER_B
               for (_, _, _, reader, work, *_rest) in got)
