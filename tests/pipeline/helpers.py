"""Config and runner shared by the pipeline and CLI unit tests (fake Supabase, no network)."""
from __future__ import annotations

import asyncio
from typing import Any

from rlsentry.contracts.models import Profile, Role, ScanReport
from rlsentry.contracts.policy import RoleScopes, RowScope, ScanConfig, TablePolicy, TestUser
from rlsentry.pipeline import run_scan
from tests.pipeline.fake_supabase import API, APP, ENV, FakeSupabase

USERS = [TestUser(name=Role.USER_A, email="a@test.dev", password_env="RLS_A_PW"),
         TestUser(name=Role.USER_B, email="b@test.dev", password_env="RLS_B_PW")]
OWNER_ONLY = TablePolicy(owner_column="owner_id",
                         select=RoleScopes(anon=RowScope.DENY, user=RowScope.OWN_ROWS_ONLY))


def cfg(**kw: Any) -> ScanConfig:
    """A config like a user would write for the fake project (authorized, audit, URL named)."""
    base: dict[str, Any] = {"target": APP, "authorized": True, "profile": Profile.AUDIT,
                            "rate_limit_rps": 1000.0, "test_users": USERS, "supabase_url": API,
                            "tables": {"notes": OWNER_ONLY}}
    base.update(kw)
    return ScanConfig(**base)


def scan(fake: FakeSupabase, config: ScanConfig, env: dict[str, str] | None = None,
         **kw: Any) -> ScanReport:
    kw.setdefault("confirmed_by", "tester")
    return asyncio.run(run_scan(config, env=ENV if env is None else env,
                                transport=fake.transport(), **kw))


def rules(report: ScanReport) -> set[tuple[str | None, str | None, str]]:
    return {(f.target, f.role.value if f.role else None, f.rule) for f in report.findings}
