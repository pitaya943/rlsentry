"""Row-level visibility under an expected scope (SPEC §6, FR-10). Pure, no I/O."""
from __future__ import annotations

from rlsentry.contracts.policy import RowScope


def row_permitted(scope: RowScope, actor_id: str | None, owner_id: str | None,
                  is_public: bool) -> bool:
    """Whether a role may touch one row under `scope`.

    Why: the probe diff needs one definition of "own" so that None (anon / unowned row)
    never counts as ownership.
    """
    own = actor_id is not None and owner_id is not None and actor_id == owner_id
    if scope is RowScope.ALL:
        return True
    if scope is RowScope.OWN_ROWS_ONLY:
        return own
    if scope is RowScope.PUBLIC_ROWS_ONLY:
        return is_public
    if scope is RowScope.PUBLIC_OR_OWN_ROWS:
        return is_public or own
    return False
