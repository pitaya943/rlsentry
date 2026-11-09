"""probe/verdict.py: three-state read verdict (SPEC §5 M3 三態結果; ADR-023 #3).
Contract: rlsentry/contracts/probe.py (split_known, read_cell)."""
import pytest

from rlsentry.contracts.models import Op, Outcome, Role
from rlsentry.contracts.policy import ExpectedAccess, RowScope
from rlsentry.contracts.probe import CountResult, KnownRow, ReadObservation
from rlsentry.probe.verdict import read_cell, split_known

A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
IDS = {Role.USER_A: A, Role.USER_B: B}
ROWS = [KnownRow(pk="a1", owner=Role.USER_A), KnownRow(pk="a2", owner=Role.USER_A, public=True),
        KnownRow(pk="b1", owner=Role.USER_B)]


def exp(role: Role, scope: RowScope, review: str | None = None) -> ExpectedAccess:
    return ExpectedAccess(target="t", op=Op.SELECT, role=role, scope=scope, owner_column="owner_id",
                          review_reason=review)


@pytest.mark.parametrize("role,scope,forbidden,permitted", [
    (Role.ANON, RowScope.DENY, ["a1", "a2", "b1"], []),
    (Role.ANON, RowScope.PUBLIC_ROWS_ONLY, ["a1", "b1"], ["a2"]),
    (Role.USER_A, RowScope.OWN_ROWS_ONLY, ["b1"], ["a1", "a2"]),
    (Role.USER_B, RowScope.PUBLIC_OR_OWN_ROWS, ["a1"], ["a2", "b1"]),
    (Role.USER_B, RowScope.ALL, [], ["a1", "a2", "b1"]),
])
def test_split_known(role: Role, scope: RowScope, forbidden: list[str], permitted: list[str]) -> None:
    assert split_known(exp(role, scope), ROWS, IDS) == (forbidden, permitted)


def test_split_without_user_id_owns_nothing() -> None:
    assert split_known(exp(Role.USER_A, RowScope.OWN_ROWS_ONLY), ROWS, {Role.USER_B: B}) == (["a1", "a2", "b1"], [])


def cr(status: int | None, total: int | None, queried: int = 2) -> CountResult:
    return CountResult(queried=queried, status=status, total=total, curl=f"curl {status}")


def obs(forbidden: CountResult | None, permitted: CountResult | None = None, review: str | None = None,
        note: str | None = None) -> ReadObservation:
    return ReadObservation(target="t", role=Role.USER_B, expected=exp(Role.USER_B, RowScope.OWN_ROWS_ONLY, review),
                           forbidden=forbidden, permitted=permitted, note=note)


def test_visible_forbidden_rows_are_allowed() -> None:
    c = read_cell(obs(cr(200, 1)))
    assert (c.outcome, c.known_rows_checked, c.http_status, c.op, c.role) == (Outcome.ALLOWED, 2, 200, Op.SELECT, Role.USER_B)
    assert "1/2" in c.reason and c.evidence_curl == "curl 200"


def test_no_visible_forbidden_rows_is_denied_206_too() -> None:
    assert read_cell(obs(cr(200, 0))).outcome is Outcome.DENIED
    assert read_cell(obs(cr(206, 2))).outcome is Outcome.ALLOWED


@pytest.mark.parametrize("status,total", [(401, None), (403, None), (404, None), (400, None), (500, None),
                                          (None, None), (200, None), (200, 3), (401, 0)])
def test_no_trustworthy_count_is_inconclusive_never_denied(status: int | None, total: int | None) -> None:
    c = read_cell(obs(cr(status, total)))
    assert c.outcome is Outcome.INCONCLUSIVE and c.known_rows_checked == 0 and c.http_status == status


def test_no_forbidden_row_is_inconclusive_even_if_permitted_visible() -> None:
    # C04-I1: the other user has no data, so nothing can show a violation.
    c = read_cell(obs(None, cr(200, 2), note="no known row outside the expected scope of user_b"))
    assert c.outcome is Outcome.INCONCLUSIVE and c.reason == "no known row outside the expected scope of user_b"
    assert c.evidence_curl == "curl 200"
    assert read_cell(obs(None)).reason == "no known row outside the expected scope"


def test_review_comes_first() -> None:
    c = read_cell(obs(cr(200, 1), review="owner column unknown"))
    assert c.outcome is Outcome.INCONCLUSIVE and c.reason == "owner column unknown" and c.known_rows_checked == 0
