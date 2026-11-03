"""MS2 holdout, mutation variant (ADR-022 #3): different lab mutations than the visible
tests/lab/test_oracle_mutations.py, for the oracle AND for the scanner. Needs Docker."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator

import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS, row_pk
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Evidence, Op, Outcome, Profile, Role
from rlsentry.contracts.policy import TestUser
from rlsentry.discovery.discover import discover
from rlsentry.probe.run import probe
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.lab.oracle import Scenario, load_gt

pytestmark = pytest.mark.safety


@pytest.fixture(scope="module")
def lab_info() -> Iterator[LabInfo]:
    with labctl.lock():
        yield labctl.ensure_up()


def caught(info: LabInfo, sid: str, sql: str, check: Callable[[Scenario], None], reason: str) -> None:
    sc = Scenario.load(info, sid)
    try:
        check(sc)
        labctl.execute(sql)
        sc.tokens.clear()
        with pytest.raises(AssertionError) as exc:
            check(sc)
        assert reason in str(exc.value), str(exc.value)
    finally:
        labctl.apply(sid)


def test_oracle_l02_fixed_select(lab_info: LabInfo) -> None:
    caught(lab_info, "L02", "drop policy messages_select on public.messages; create policy messages_select on "
           "public.messages for select to authenticated using (owner_id = auth.uid());",
           lambda sc: sc.check_case("L02-V1"), "L02-V1")


def test_oracle_c02_everything_published(lab_info: LabInfo) -> None:
    caught(lab_info, "C02", "update public.articles set is_published = true;",
           lambda sc: sc.check_case("C02-S2"), "C02-S2")


def test_oracle_l06_invoker_view(lab_info: LabInfo) -> None:
    caught(lab_info, "L06", "alter view public.invoice_summary set (security_invoker = true);",
           lambda sc: sc.check_case("L06-V1"), "L06-V1")


def scan(info: LabInfo, sid: str) -> tuple[dict[tuple[str, Role, Op], Outcome], set[tuple[str | None, Role | None, str]]]:
    gt = load_gt(sid)
    users = [TestUser(name=r, email=u["email"], password_env=u["password_env"]) for r, u in LAB_USERS.items()]
    env = {u["password_env"]: labctl.lab_password(r) for r, u in LAB_USERS.items()}

    async def go() -> tuple[dict[tuple[str, Role, Op], Outcome], set[tuple[str | None, Role | None, str]]]:
        async with SafeClient(profile=Profile.AUDIT, limiter=RateLimiter(rps=200)) as c:
            d = await discover(c, info.api_url, info.anon_key, gt.policy, [])
            s = await build_sessions(c, info.api_url, info.anon_key, users, env)
            m, fs = await probe(c, info.api_url, info.anon_key, d.targets, s, gt.policy, Profile.AUDIT)
        return ({(x.target, x.role, x.op): x.outcome for x in m.cells},
                {(f.target, f.role, f.rule) for f in fs if f.evidence is Evidence.CONFIRMED})
    return asyncio.run(go())


def test_scanner_sees_c01_with_rls_disabled(lab_info: LabInfo) -> None:
    labctl.apply("C01")
    try:
        cells, confirmed = scan(lab_info, "C01")
        assert cells[("todos", Role.ANON, Op.SELECT)] is Outcome.DENIED and confirmed == set()
        labctl.execute("alter table public.todos disable row level security;")
        cells, confirmed = scan(lab_info, "C01")
        assert confirmed == {("todos", Role.ANON, "ANON_READ_OWNER_SCOPED"), ("todos", Role.USER_A, "CROSS_TENANT_READ"),
                             ("todos", Role.USER_B, "CROSS_TENANT_READ")}
    finally:
        labctl.apply("C01")


def test_scanner_c04_becomes_decidable_when_b_has_a_row(lab_info: LabInfo) -> None:
    labctl.apply("C04")
    try:
        assert scan(lab_info, "C04")[0][("subscriptions", Role.USER_A, Op.SELECT)] is Outcome.INCONCLUSIVE
        labctl.execute(f"insert into public.subscriptions (id, owner_id, plan) values ('{row_pk('C04', 9)}', "
                       f"'{LAB_USERS[Role.USER_B]['id']}', 'free');")
        cells, confirmed = scan(lab_info, "C04")
        assert cells[("subscriptions", Role.USER_A, Op.SELECT)] is Outcome.DENIED and confirmed == set()
    finally:
        labctl.apply("C04")
