"""probe/verdict.py: three-state read verdict (SPEC §5 M3 三態結果; ADR-023 #3).
Contract: rlsentry/contracts/probe.py (split_known, read_cell)."""
from __future__ import annotations

from collections.abc import Mapping

from rlsentry.contracts.models import Op, Outcome, ProbeResult, Role
from rlsentry.contracts.policy import ExpectedAccess
from rlsentry.contracts.probe import KnownRow, ReadObservation
from rlsentry.policy.visibility import row_permitted


def split_known(expected: ExpectedAccess, rows: list[KnownRow],
                user_ids: Mapping[Role, str]) -> tuple[list[str], list[str]]:
    """Split known rows into (forbidden, permitted) pks for the probed role.

    Why: only rows the policy forbids can prove a leak; a missing user id means the actor
    owns nothing, so ownership is never granted by accident.
    """
    actor_id = None if expected.role is Role.ANON else user_ids.get(expected.role)
    forbidden: list[str] = []
    permitted: list[str] = []
    for row in rows:
        ok = row_permitted(expected.scope, actor_id, user_ids.get(row.owner), row.public)
        (permitted if ok else forbidden).append(row.pk)
    return forbidden, permitted


def read_cell(obs: ReadObservation) -> ProbeResult:
    """Decide allowed / denied / inconclusive for one read cell.

    Why: count 0 or an HTTP error is not proof of denial; only a trustworthy exact count of
    known forbidden rows can say allowed or denied.
    """
    fb, pm = obs.forbidden, obs.permitted
    curl = fb.curl if fb is not None else (pm.curl if pm is not None else "")

    def make(outcome: Outcome, checked: int, reason: str, status: int | None = None) -> ProbeResult:
        return ProbeResult(target=obs.target, role=obs.role, op=Op.SELECT, outcome=outcome,
                           known_rows_checked=checked, reason=reason, http_status=status,
                           evidence_curl=curl)

    if obs.expected.is_review:
        return make(Outcome.INCONCLUSIVE, 0, obs.expected.review_reason or "needs review")
    if fb is None:
        return make(Outcome.INCONCLUSIVE, 0, obs.note or "no known row outside the expected scope")
    if fb.status in (200, 206) and fb.total is not None and fb.total <= fb.queried:
        outcome = Outcome.ALLOWED if fb.total > 0 else Outcome.DENIED
        return make(outcome, fb.queried,
                    f"{fb.total}/{fb.queried} known rows outside the expected scope are visible",
                    fb.status)
    seen = f"HTTP {fb.status}" if fb.status is not None else "no response"
    return make(Outcome.INCONCLUSIVE, 0, f"{seen}: no trustworthy row count was obtained", fb.status)
