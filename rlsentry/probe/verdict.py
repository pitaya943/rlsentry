"""probe/verdict.py: three-state read verdict (SPEC §5 M3 三態結果; ADR-023 #3).
Contract: rlsentry/contracts/probe.py (split_known, read_cell)."""
from __future__ import annotations

from collections.abc import Mapping

from rlsentry.contracts.models import Op, Outcome, ProbeResult, Role
from rlsentry.contracts.policy import ExpectedAccess, RowScope
from rlsentry.contracts.probe import (
    WRITE_NOT_FORBIDDEN_REASON,
    KnownRow,
    ReadObservation,
    WriteObservation,
)
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


def forbidden_write(scope: RowScope, actor_id: str | None, owner_id: str | None,
                    is_public: bool) -> bool:
    """True iff the expected scope does not permit the end state of the write.

    Why: only forbidden writes are attempted, so a confirmed effect is a vulnerability.
    """
    return not row_permitted(scope, actor_id, owner_id, is_public)


def write_outcome(op: Op, after_present: bool | None) -> bool | None:
    """Did the forbidden write take effect, judged only by the read-back of the end state?

    Why: a 2xx is not a write; None (untrustworthy read-back) stays None, never False.
    """
    if after_present is None:
        return None
    return (not after_present) if op is Op.DELETE else after_present


def write_cell(obs: WriteObservation) -> ProbeResult:
    """Decide allowed / denied / inconclusive / not_tested for one write cell.

    Why: only a trustworthy read-back of the end state can say allowed or denied; a 2xx
    with no verified effect is denied (USING filters to 0 rows yet PostgREST answers 2xx).
    """
    curl = obs.attempt.curl if obs.attempt is not None else ""
    status = obs.attempt.status if obs.attempt is not None else None

    def make(outcome: Outcome, checked: int, reason: str) -> ProbeResult:
        return ProbeResult(target=obs.target, role=obs.role, op=obs.op, outcome=outcome,
                           known_rows_checked=checked, reason=reason, http_status=status,
                           evidence_curl=curl)

    if obs.plan is None:
        return make(Outcome.NOT_TESTED, 0, obs.note or WRITE_NOT_FORBIDDEN_REASON)
    if obs.attempt is None or obs.after is None:
        return make(Outcome.INCONCLUSIVE, 0, obs.note or "write not sent")
    took = write_outcome(obs.op, obs.after.present)
    if took is None:
        return make(Outcome.INCONCLUSIVE, 0,
                    f"the end state could not be read back (HTTP {obs.after.status})")
    if took:
        return make(Outcome.ALLOWED, 1, "the forbidden write took effect (verified by read-back)")
    return make(Outcome.DENIED, 1, "the forbidden write did not take effect (verified by read-back)")
