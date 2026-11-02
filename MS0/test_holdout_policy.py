"""MS0 holdout: same behaviour as tests/policy, different inputs."""
import pytest

from rlsentry.contracts.models import Op, Profile, Role
from rlsentry.contracts.policy import ConfigError, ExpectedPolicy, RowScope
from rlsentry.policy.load import load_config
from rlsentry.policy.resolve import resolve_expected
from rlsentry.policy.visibility import row_permitted

P = ExpectedPolicy.model_validate({
    "tables": {
        "comments": {"owner_column": "created_by", "public_column": "is_public",
                     "update": {"user": "public_or_own_rows"}, "select": {"anon": "all"}},
        "teams": {"insert": {"anon": "deny"}},
    },
    "defaults": {"anon": "public_rows_only", "user": "own_rows_only"},
})


def test_listed_partial_ops_and_roles() -> None:
    assert resolve_expected(P, "comments", Op.SELECT, Role.ANON).scope is RowScope.ALL
    u = resolve_expected(P, "comments", Op.SELECT, Role.USER_A)
    assert u.scope is RowScope.OWN_ROWS_ONLY and u.owner_column == "created_by" and not u.is_review
    upd = resolve_expected(P, "comments", Op.UPDATE, Role.USER_B)
    assert upd.scope is RowScope.PUBLIC_OR_OWN_ROWS and not upd.is_review
    a = resolve_expected(P, "comments", Op.DELETE, Role.ANON)       # defaults anon public_rows_only
    assert a.scope is RowScope.PUBLIC_ROWS_ONLY and a.public_column == "is_public" and not a.is_review


def test_unlisted_and_listed_without_columns() -> None:
    e = resolve_expected(P, "tasks", Op.SELECT, Role.ANON, ("id", "is_published", "owner_id"))
    assert e.scope is RowScope.PUBLIC_ROWS_ONLY and e.public_column == "is_published" and not e.is_review
    n = resolve_expected(P, "tasks", Op.SELECT, Role.ANON, ("id", "author_id"))
    assert n.is_review                                          # needs a public column
    t = resolve_expected(P, "teams", Op.INSERT, Role.USER_A, ("id", "user_id"))
    assert t.scope is RowScope.OWN_ROWS_ONLY and t.is_review    # listed: no inference
    c = resolve_expected(P, "docs", Op.UPDATE, Role.USER_B, ("created_by", "author_id"))
    assert c.owner_column == "author_id"                       # candidate order


def test_anon_simplification_other_way() -> None:
    p = ExpectedPolicy.model_validate({"tables": {"x": {"select": {"anon": "public_or_own_rows"}}}})
    e = resolve_expected(p, "x", Op.SELECT, Role.ANON)
    assert e.scope is RowScope.PUBLIC_ROWS_ONLY and e.is_review
    q = ExpectedPolicy.model_validate({"tables": {"x": {"delete": {"anon": "own_rows_only"}}}})
    assert resolve_expected(q, "x", Op.DELETE, Role.ANON).scope is RowScope.DENY


@pytest.mark.parametrize(("scope", "actor", "owner", "pub", "want"), [
    (RowScope.ALL, None, None, False, True),
    (RowScope.DENY, None, None, True, False),
    (RowScope.OWN_ROWS_ONLY, "u1", "u1", True, True),
    (RowScope.OWN_ROWS_ONLY, None, "u1", True, False),
    (RowScope.PUBLIC_ROWS_ONLY, "u1", "u1", False, False),
    (RowScope.PUBLIC_OR_OWN_ROWS, None, None, True, True),
    (RowScope.PUBLIC_OR_OWN_ROWS, None, None, False, False),
    (RowScope.PUBLIC_OR_OWN_ROWS, "u2", "u1", False, False),
])
def test_row_permitted_other_inputs(scope: RowScope, actor: str | None, owner: str | None,
                                    pub: bool, want: bool) -> None:
    assert row_permitted(scope, actor, owner, pub) is want


def test_load_config_other_inputs() -> None:
    c = load_config("target: https://lab.local\nprofile: ci\nrate_limit_rps: 2.5\n")
    assert c.profile is Profile.CI and c.rate_limit_rps == 2.5 and not c.authorized
    with pytest.raises(ConfigError) as ei:
        load_config("target: https://lab.local\ndefaults: {anon: sometimes}\n")
    assert "defaults.anon" in str(ei.value)
    with pytest.raises(ConfigError) as ei:
        load_config("target: https://lab.local\ntest_users: [{name: user_b, email: b@x, pasword_env: X}]\n")
    assert "test_users.0" in str(ei.value)
    with pytest.raises(ConfigError):
        load_config("target: https://lab.local\n  bad: indent: here\n")
    with pytest.raises(ConfigError):
        load_config("null")
