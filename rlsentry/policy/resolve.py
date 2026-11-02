"""Resolve the expected access for one cell (SPEC §6, FR-10)."""
from __future__ import annotations

from rlsentry.contracts.models import Op, Role
from rlsentry.contracts.policy import (
    NEEDS_OWNER,
    NEEDS_PUBLIC,
    OWNER_COLUMN_CANDIDATES,
    PUBLIC_COLUMN_CANDIDATES,
    ExpectedAccess,
    ExpectedPolicy,
    RowScope,
)


def _first(candidates: tuple[str, ...], columns: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if c in columns), None)


def resolve_expected(policy: ExpectedPolicy, target: str, op: Op, role: Role,
                     columns: tuple[str, ...] = ()) -> ExpectedAccess:
    """Why: M3 diffs reality against this single normalized answer; a missing column
    must become a Review hint rather than a false vulnerability (SPEC §6)."""
    key = "anon" if role is Role.ANON else "user"
    default: RowScope = getattr(policy.defaults, key)
    table = policy.tables.get(target)
    if table is not None:
        scopes = getattr(table, op.value, None)
        scope = (getattr(scopes, key, None) if scopes is not None else None) or default
        owner, public = table.owner_column, table.public_column
    else:
        scope = default
        owner = _first(OWNER_COLUMN_CANDIDATES, columns)
        public = _first(PUBLIC_COLUMN_CANDIDATES, columns)
    if role is Role.ANON:
        if scope is RowScope.OWN_ROWS_ONLY:
            scope = RowScope.DENY
        elif scope is RowScope.PUBLIC_OR_OWN_ROWS:
            scope = RowScope.PUBLIC_ROWS_ONLY
    reason = None
    if scope in NEEDS_OWNER and owner is None:
        reason = f"{target}: scope {scope.value} needs an owner column but none is known"
    elif scope in NEEDS_PUBLIC and public is None:
        reason = f"{target}: scope {scope.value} needs a public column but none is known"
    return ExpectedAccess(target=target, op=op, role=role, scope=scope, owner_column=owner,
                          public_column=public, review_reason=reason)
