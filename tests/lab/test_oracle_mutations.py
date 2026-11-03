"""Oracle mutation tests (ADR-022 #3; ADR-005 補記 common-mode risk).

Each test loads a scenario, breaks it on purpose with labctl.execute, and asserts that the lab
oracle fails FOR THE EXPECTED REASON: the AssertionError message must name the given case id
(or "positive control"). An oracle that fails for any other reason (a crash, a different case)
does not count as catching the defect (human Q3 on MS1). Since the oracle also names the case
in "broken, not caught" messages (e.g. "rpc not callable"), the message must also contain the
phrase of the expected failure (MS2 audit F3). Every test re-applies the scenario.
Needs Docker.
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import row_pk
from rlsentry.contracts.lab import LabInfo
from tests.lab.oracle import Scenario

B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


NONE = "expected none"            # _select: a denied row became visible
ALL = "expected all"              # _select: an allowed row became invisible
CONTROL = "positive control"      # check_rows: a permitted row is invisible
KNOWABLE = "is visible to"        # _inconclusive: a forbidden row became knowable


def caught(info: LabInfo, sid: str, sql: str, check: Callable[[Scenario], None], *reason: str) -> None:
    sc = Scenario.load(info, sid)
    try:
        check(sc)  # the unbroken scenario passes: the failure below is caused by the mutation
        labctl.execute(sql)
        sc.tokens.clear()
        with pytest.raises(AssertionError) as exc:
            check(sc)
        assert all(r in str(exc.value) for r in reason), f"oracle failed for another reason: {exc.value}"
    finally:
        labctl.apply(sid)


@pytest.mark.safety
def test_rls_disabled_breaks_owner_isolation(lab_info: LabInfo) -> None:
    caught(lab_info, "C01", "alter table public.todos disable row level security;",
           lambda sc: sc.check_case("C01-S2"), "C01-S2", NONE)


@pytest.mark.safety
def test_fixed_policy_removes_planted_cross_tenant_read(lab_info: LabInfo) -> None:
    caught(lab_info, "L04", "drop policy notes_select on public.notes; create policy notes_select on "
           "public.notes for select to authenticated using (owner_id = auth.uid());",
           lambda sc: sc.check_case("L04-V1"), "L04-V1", ALL)


@pytest.mark.safety
def test_deny_all_policy_fails_positive_control(lab_info: LabInfo) -> None:
    caught(lab_info, "C04", "drop policy subscriptions_select_own on public.subscriptions; create policy "
           "deny_all on public.subscriptions for select using (false);",
           lambda sc: sc.check_rows(), CONTROL)


@pytest.mark.safety
def test_knowable_forbidden_row_breaks_inconclusive_case(lab_info: LabInfo) -> None:
    caught(lab_info, "C03", f"insert into public.announcements (id, owner_id) values ('{row_pk('C03', 9)}', '{B}');",
           lambda sc: sc.check_case("C03-I2"), "C03-I2", KNOWABLE)


@pytest.mark.safety
def test_invoker_rpc_removes_planted_definer_leak(lab_info: LabInfo) -> None:
    caught(lab_info, "L07", "alter function public.get_all_accounts() security invoker;",
           lambda sc: sc.check_case("L07-V1"), "L07-V1", ALL)
