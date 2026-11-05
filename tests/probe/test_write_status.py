"""write_cell HTTP-status classification (SPEC §5 M3; ADR-029 補記 2). Contract: contracts/probe.py.
Pure. A non-2xx write may be a policy denial (401/403) OR the scanner's own invalid request
(400/409/5xx) — only the former is 'denied', so a failed canary INSERT is never a false 'safe'."""
import pytest

from rlsentry.contracts.models import Op, Outcome, Role
from rlsentry.contracts.probe import ReadBack, WriteAttempt, WriteObservation, WritePlan
from rlsentry.probe.verdict import write_cell


def obs(op: Op, status: int | None, after: bool | None) -> WriteObservation:
    plan = WritePlan(op=op, actor=Role.ANON, rule="ANON_WRITE", reader=Role.USER_A,
                     work_owner=None if op is Op.INSERT else Role.USER_A)
    rb_status = status if status in (200, 201, 204, 206) else 400
    return WriteObservation(target="t", role=Role.ANON, op=op, plan=plan,
                            attempt=WriteAttempt(status=status, curl="c"),
                            after=ReadBack(present=after, status=rb_status, curl="h"))


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_denied_regardless_of_readback(status: int) -> None:
    c = write_cell(obs(Op.INSERT, status, after=False))
    assert c.outcome is Outcome.DENIED and c.known_rows_checked == 1 and c.http_status == status


@pytest.mark.parametrize("status", [400, 409, 422, 500, None])
def test_non_auth_failure_is_inconclusive_never_denied(status: int | None) -> None:
    c = write_cell(obs(Op.INSERT, status, after=None))
    assert c.outcome is Outcome.INCONCLUSIVE and c.known_rows_checked == 0 and c.http_status == status


@pytest.mark.parametrize("op,after,expected", [
    (Op.INSERT, True, Outcome.ALLOWED), (Op.INSERT, False, Outcome.DENIED),
    (Op.UPDATE, True, Outcome.ALLOWED), (Op.UPDATE, False, Outcome.DENIED),
    (Op.DELETE, False, Outcome.ALLOWED), (Op.DELETE, True, Outcome.DENIED),
    (Op.UPDATE, None, Outcome.INCONCLUSIVE),
])
def test_2xx_uses_read_back(op: Op, after: bool | None, expected: Outcome) -> None:
    assert write_cell(obs(op, 200, after)).outcome is expected
