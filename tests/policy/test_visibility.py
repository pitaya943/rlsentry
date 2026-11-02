"""row_permitted (T-022). SPEC §6 row scopes; contract: rlsentry/contracts/policy.py."""
import pytest
from rlsentry.policy.visibility import row_permitted

from rlsentry.contracts.policy import RowScope

A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest.mark.parametrize(("scope", "actor", "owner", "public", "want"), [
    (RowScope.DENY, A, A, True, False),
    (RowScope.ALL, None, B, False, True),
    (RowScope.OWN_ROWS_ONLY, A, A, False, True),
    (RowScope.OWN_ROWS_ONLY, A, B, True, False),
    (RowScope.PUBLIC_ROWS_ONLY, B, B, False, False),
    (RowScope.PUBLIC_ROWS_ONLY, None, A, True, True),
    (RowScope.PUBLIC_OR_OWN_ROWS, B, A, False, False),
    (RowScope.PUBLIC_OR_OWN_ROWS, B, A, True, True),
    (RowScope.PUBLIC_OR_OWN_ROWS, B, B, False, True),
])
def test_scope_table(scope: RowScope, actor: str | None, owner: str | None, public: bool, want: bool) -> None:
    assert row_permitted(scope, actor, owner, public) is want


def test_none_never_owns() -> None:
    # anon (actor None) does not own unowned rows (owner None): None == None is not ownership.
    assert row_permitted(RowScope.OWN_ROWS_ONLY, None, None, False) is False
    assert row_permitted(RowScope.PUBLIC_OR_OWN_ROWS, A, None, False) is False
