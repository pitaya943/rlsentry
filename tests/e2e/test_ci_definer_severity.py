"""MS6 approval note 1, ADR-049: supplying a DB connection never changes ci's fail_on result.

L07 in ci, with and without M4 (db_url_env). Without M4 the RPC reads keep M3's rules; with M4
they are relabelled SECURITY_DEFINER_RPC_DATA, but the severity never drops: anon High,
users Medium. Both runs fail ci with the default fail_on (Confirmed and >= high).
"""
from __future__ import annotations

import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile, Role, Severity
from rlsentry.contracts.policy import FailOn
from rlsentry.contracts.report import EXIT_FINDINGS
from rlsentry.report.exit_code import exit_code
from tests.e2e.conftest import lab_config, lab_env
from tests.e2e.helpers import gt, proven, scan

pytestmark = pytest.mark.e2e_profiles

WITHOUT_M4 = {(Role.ANON, "ANON_READ_OWNER_SCOPED", Severity.HIGH),
              (Role.USER_A, "CROSS_TENANT_READ", Severity.MEDIUM),
              (Role.USER_B, "CROSS_TENANT_READ", Severity.MEDIUM)}
WITH_M4 = {(Role.ANON, "SECURITY_DEFINER_RPC_DATA", Severity.HIGH),
           (Role.USER_A, "SECURITY_DEFINER_RPC_DATA", Severity.MEDIUM),
           (Role.USER_B, "SECURITY_DEFINER_RPC_DATA", Severity.MEDIUM)}


@pytest.mark.parametrize("with_db, want, modules", [
    (False, WITHOUT_M4, ["M2", "M3", "M5"]),
    (True, WITH_M4, ["M2", "M3", "M4", "M5"]),
])
def test_l07_ci_fails_the_same_with_and_without_m4(lab: LabInfo, with_db: bool,
                                                   want: set[tuple[Role, str, Severity]],
                                                   modules: list[str]) -> None:
    labctl.apply("L07")
    cfg = lab_config("http://127.0.0.1:1", lab, gt("L07").policy, Profile.CI, with_db=with_db)
    rep = scan(cfg, lab_env(lab))
    assert rep.modules == modules
    got = {(f.role, f.rule, f.severity) for f in proven(rep) if f.target == "get_all_accounts"}
    assert got == want
    assert all(f.target == "get_all_accounts" for f in proven(rep))
    assert exit_code(rep, FailOn()) == EXIT_FINDINGS
