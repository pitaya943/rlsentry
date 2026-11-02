"""resolve_expected (T-021). SPEC §6 expected policy + defaults; contract: rlsentry/contracts/policy.py."""
import pytest
import yaml
from rlsentry.policy.resolve import resolve_expected

from rlsentry.contracts.models import Op, Role
from rlsentry.contracts.policy import ExpectedPolicy, RowScope

POLICY = ExpectedPolicy.model_validate(yaml.safe_load("""
tables:
  profiles:
    owner_column: id
    select: {anon: deny, user: own_rows_only}
    delete: {anon: deny, user: deny}
  posts:
    owner_column: author_id
    public_column: is_published
    select: {anon: public_rows_only, user: public_or_own_rows}
    insert: {user: own_rows_only}
  catalog:
    select: {anon: all, user: all}
  shared:
    select: {user: own_rows_only}
defaults: {anon: deny, user: own_rows_only}
"""))


def test_listed_table_uses_its_own_scope_and_columns() -> None:
    e = resolve_expected(POLICY, "posts", Op.SELECT, Role.USER_B)
    assert (e.scope, e.owner_column, e.public_column) == (RowScope.PUBLIC_OR_OWN_ROWS, "author_id", "is_published")
    assert not e.is_review
    assert (e.target, e.op, e.role) == ("posts", Op.SELECT, Role.USER_B)


def test_user_a_and_user_b_share_the_user_key() -> None:
    a = resolve_expected(POLICY, "profiles", Op.DELETE, Role.USER_A)
    b = resolve_expected(POLICY, "profiles", Op.DELETE, Role.USER_B)
    assert a.scope is b.scope is RowScope.DENY


def test_missing_op_or_role_falls_back_to_defaults() -> None:
    assert resolve_expected(POLICY, "profiles", Op.UPDATE, Role.USER_A).scope is RowScope.OWN_ROWS_ONLY
    assert resolve_expected(POLICY, "posts", Op.INSERT, Role.ANON).scope is RowScope.DENY


def test_unlisted_table_infers_owner_column_from_candidates() -> None:
    e = resolve_expected(POLICY, "orders", Op.SELECT, Role.USER_A, ("id", "owner_id", "user_id"))
    assert e.scope is RowScope.OWN_ROWS_ONLY
    assert e.owner_column == "user_id"           # candidate order wins, not column order
    assert not e.is_review


def test_owner_scope_without_owner_column_is_review_not_vulnerability() -> None:
    # SPEC §6 defaults comment: 找不到 owner_column 時改為 Review
    e = resolve_expected(POLICY, "logs", Op.SELECT, Role.USER_B, ("id", "message"))
    assert e.is_review and e.owner_column is None
    listed = resolve_expected(POLICY, "shared", Op.SELECT, Role.USER_A, ("id", "user_id"))
    assert listed.is_review                      # listed tables never infer columns


def test_anon_owns_nothing() -> None:
    # own_rows_only for anon is deny: no review needed even without an owner column.
    e = resolve_expected(ExpectedPolicy(defaults={"anon": "own_rows_only"}), "logs", Op.SELECT,
                         Role.ANON, ("id",))
    assert e.scope is RowScope.DENY and not e.is_review


@pytest.mark.parametrize(("role", "review"), [(Role.ANON, True), (Role.USER_A, True)])
def test_public_scope_without_public_column_is_review(role: Role, review: bool) -> None:
    p = ExpectedPolicy.model_validate(
        {"tables": {"t": {"owner_column": "user_id", "select": {"anon": "public_or_own_rows",
                                                                  "user": "public_rows_only"}}}})
    e = resolve_expected(p, "t", Op.SELECT, role)
    assert e.is_review is review
    if role is Role.ANON:
        assert e.scope is RowScope.PUBLIC_ROWS_ONLY


def test_all_and_deny_never_need_columns() -> None:
    assert not resolve_expected(POLICY, "catalog", Op.SELECT, Role.ANON).is_review
    assert not resolve_expected(POLICY, "anything", Op.DELETE, Role.ANON, ()).is_review
