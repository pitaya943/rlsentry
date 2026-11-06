"""Lab fixtures for the profile end-to-end tests (SPEC §9 Profile 端到端; marker e2e_profiles).

These run the real product path, run_scan, against the local Supabase lab and fail (never skip)
when the lab is missing. One pytest process holds the lab lock for the whole session.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ExpectedPolicy, ScanConfig, TestUser

ANON_ENV, DB_ENV = "E2E_ANON_KEY", "E2E_DB_URL"


@pytest.fixture(scope="session")
def lab() -> Iterator[LabInfo]:
    with labctl.lock():
        yield labctl.ensure_up()


def lab_env(info: LabInfo) -> dict[str, str]:
    env = {u["password_env"]: labctl.lab_password(r) for r, u in LAB_USERS.items()}
    return {**env, ANON_ENV: info.anon_key, DB_ENV: info.db_url}


def lab_config(target: str, info: LabInfo, policy: ExpectedPolicy, profile: Profile, *,
               with_db: bool = True, **kw: Any) -> ScanConfig:
    """What a lab user writes in rlsentry.yaml (authorized, URL named, keys by env var name)."""
    users = [TestUser(name=r, email=u["email"], password_env=u["password_env"]) for r, u in LAB_USERS.items()]
    base: dict[str, Any] = {"target": target, "authorized": True, "profile": profile, "rate_limit_rps": 50.0,
                            "test_users": users, "supabase_url": info.api_url, "anon_key_env": ANON_ENV,
                            "db_url_env": DB_ENV if with_db else None, "tables": policy.tables,
                            "defaults": policy.defaults}
    base.update(kw)
    return ScanConfig(**base)
