"""MS4 approval note 5 (b), ADR-039: M3 never claims SECURITY_DEFINER_RPC_DATA.

read_rule depends on the role only; an RPC read beyond scope is ANON_READ_OWNER_SCOPED (anon) or
CROSS_TENANT_READ (users) until M4 proves the function is SECURITY DEFINER
(tests/whitebox/test_correlate_roles.py). A SECURITY INVOKER RPC therefore keeps the plain rule.
"""
from __future__ import annotations

import pytest

from rlsentry.contracts.models import Op, Outcome, ProbeResult, Role, Severity, Target
from rlsentry.contracts.policy import ExpectedAccess, RowScope
from rlsentry.contracts.probe import CountResult, ReadObservation
from rlsentry.probe.diff import read_findings
from rlsentry.rules.severity import read_rule, read_severity


@pytest.mark.parametrize("kind", ["table", "view", "rpc"])
def test_rule_depends_on_role_only(kind: str) -> None:
    assert read_rule(kind, Role.ANON) == "ANON_READ_OWNER_SCOPED"
    assert read_rule(kind, Role.USER_A) == "CROSS_TENANT_READ"
    assert read_rule(kind, Role.USER_B) == "CROSS_TENANT_READ"


def test_invoker_rpc_read_is_not_labelled_security_definer() -> None:
    rpc = Target(name="list_notes", kind="rpc", columns=[], primary_key=["id"], discovered_by="openapi",
                 confidence="confirmed")
    exp = ExpectedAccess(target="list_notes", op=Op.SELECT, role=Role.ANON, scope=RowScope.DENY)
    cnt = CountResult(queried=2, status=200, total=2, curl="curl x")
    obs = ReadObservation(target="list_notes", role=Role.ANON, expected=exp, forbidden=cnt)
    cell = ProbeResult(target="list_notes", role=Role.ANON, op=Op.SELECT, outcome=Outcome.ALLOWED,
                       known_rows_checked=2, reason="r", evidence_curl="curl x")
    [f] = read_findings(rpc, obs, cell)
    assert f.rule == "ANON_READ_OWNER_SCOPED" and f.severity is Severity.HIGH
    assert read_severity("SECURITY_DEFINER_RPC_DATA", []) is Severity.MEDIUM
