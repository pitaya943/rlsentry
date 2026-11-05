"""M3 probe + M4 whitebox on the real lab (SPEC §5 M4 第 3 點與解讀; ADR-032). Needs Docker.

The MS4 focus, end to end: (1) a SECURITY DEFINER RPC is a vulnerability only because the probe
really obtained other users' rows (L07 get_all_accounts → confirmed, correlation confirmed);
the executable-but-dataless one is only a Configuration warning (L07 ping_definer);
(2) probe-only cases are real: splinter is silent on L02/L04 yet the probe proves access."""
from __future__ import annotations

import asyncio

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Evidence, Finding, Profile, Role
from rlsentry.contracts.policy import TestUser
from rlsentry.contracts.rules import RULES
from rlsentry.discovery.discover import discover
from rlsentry.probe.run import probe
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from rlsentry.whitebox.run import whitebox
from tests.lab.oracle import load_gt


def scan_and_correlate(info: LabInfo, sid: str) -> list[Finding]:
    labctl.apply(sid)
    gt = load_gt(sid)
    users = [TestUser(name=r, email=u["email"], password_env=u["password_env"]) for r, u in LAB_USERS.items()]
    env = {u["password_env"]: labctl.lab_password(r) for r, u in LAB_USERS.items()}

    async def go() -> list[Finding]:
        async with SafeClient(profile=Profile.AUDIT, limiter=RateLimiter(rps=200, concurrency=4)) as c:
            disc = await discover(c, info.api_url, info.anon_key, gt.policy, [])
            sessions = await build_sessions(c, info.api_url, info.anon_key, users, env)
            _, findings = await probe(c, info.api_url, info.anon_key, disc.targets, sessions,
                                      gt.policy, Profile.AUDIT)
            return findings
    return whitebox(info.db_url, asyncio.run(go()))


def proven(fs: list[Finding]) -> list[Finding]:
    return [f for f in fs if f.evidence is Evidence.CONFIRMED and RULES[f.rule].vulnerability]


def test_l07_definer_with_data_confirmed_without_data_warning_only(lab_info: LabInfo) -> None:
    fs = scan_and_correlate(lab_info, "L07")
    rpc = [f for f in proven(fs) if f.target == "get_all_accounts"]
    assert {f.role for f in rpc} == {Role.ANON, Role.USER_A, Role.USER_B}
    assert all(f.rule == "SECURITY_DEFINER_RPC_DATA" and f.correlation == "confirmed" for f in rpc)
    assert all("anon_security_definer_function_executable" in (f.lint or "") for f in rpc)
    assert not [f for f in fs if f.target == "get_all_accounts" and f.rule == "SECURITY_DEFINER_EXECUTABLE"]
    ping = [f for f in fs if f.target == "ping_definer"]
    assert proven(ping) == []                                     # never confirmed
    warn = [f for f in ping if f.rule == "SECURITY_DEFINER_EXECUTABLE" and f.role is Role.ANON]
    assert len(warn) == 1
    assert warn[0].evidence is Evidence.CONFIG_WARNING and warn[0].correlation == "lint_only"


def test_probe_only_cases_are_real(lab_info: LabInfo) -> None:
    for sid, target in (("L02", "messages"), ("L04", "notes")):
        fs = scan_and_correlate(lab_info, sid)
        hits = [f for f in proven(fs) if f.target == target]
        assert hits, f"{sid}: the probe must prove access to {target}"
        assert all(f.correlation == "probe_only" and f.lint is None for f in hits), sid
        assert not [f for f in fs if f.rule == "LINT_ONLY"], f"{sid}: splinter has no security lint here"


def test_l12_lint_on_unreachable_table_is_lint_only(lab_info: LabInfo) -> None:
    fs = scan_and_correlate(lab_info, "L12")
    lo = [f for f in fs if f.rule == "LINT_ONLY"]
    assert [(f.target, f.lint, f.correlation) for f in lo] == [("audit_log", "rls_enabled_no_policy", "lint_only")]
    assert not [f for f in proven(fs) if f.target == "audit_log"]
