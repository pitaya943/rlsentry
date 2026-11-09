"""probe/fill.py (ADR-034): values for required columns the caller does not set.

Contract: rlsentry/contracts/probe.py fill_required."""
import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import (
    CANARY_PREFIX,
    FILL_INT_FORMATS,
    FILL_NUM_FORMATS,
    FILL_TEXT_FORMATS,
    FILL_TIME_FORMATS,
)


def _value(fmt: str, owner_id: str) -> tuple[bool, Any]:
    """(fillable, value) for one OpenAPI format."""
    if fmt == "uuid":
        return True, owner_id
    if fmt in FILL_TEXT_FORMATS:
        return True, CANARY_PREFIX + uuid.uuid4().hex
    if fmt in FILL_INT_FORMATS or fmt in FILL_NUM_FORMATS:
        return True, 0
    if fmt == "boolean":
        return True, False
    if fmt in FILL_TIME_FORMATS:
        return True, datetime.now(UTC).isoformat()
    if fmt == "date":
        return True, datetime.now(UTC).date().isoformat()
    if fmt in ("json", "jsonb"):
        return True, {}
    return False, None


def fill_required(target: Target, owner_id: str, preset: Collection[str]) -> dict[str, Any] | None:
    """Why: NOT NULL columns without defaults make a seed/INSERT fail for reasons unrelated to
    RLS; fill them honestly, or return None so the caller sends nothing rather than a false verdict."""
    out: dict[str, Any] = {}
    for column in target.required:
        if column in preset:
            continue
        fmt = target.column_formats.get(column)
        ok, value = _value(fmt, owner_id) if fmt is not None else (False, None)
        if not ok:
            return None
        out[column] = value
    return out
