"""Contracts added in MS1 (T-041): ci write_hosts (ADR-017), safety constants, lab models."""
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from rlsentry.contracts.lab import POSTGREST_ROLES, DbWrite, LabInfo
from rlsentry.contracts.models import AuthorizationRecord
from rlsentry.contracts.policy import ScanConfig
from rlsentry.contracts.safety import JWT_RE, SB_KEY_RE, TOOL_VERSION, USER_AGENT

ROOT = Path(__file__).resolve().parents[2]


def cfg(**kw: object) -> ScanConfig:
    return ScanConfig.model_validate({"target": "https://x.test", **kw})


def test_write_hosts_default_empty() -> None:
    assert cfg().write_hosts == []


def test_write_hosts_lowercased_and_deduplicated() -> None:
    assert cfg(write_hosts=["Preview.Example.test", "preview.example.test", "db.test:8443"]
               ).write_hosts == ["preview.example.test", "db.test:8443"]


@pytest.mark.safety
@pytest.mark.parametrize("bad", ["*.supabase.co", "https://a.test", "a.test/rest", "a .test", "",
                                 "a.test:", "[::1]", "-a.test"])
def test_write_hosts_rejects_non_exact_entries(bad: str) -> None:
    with pytest.raises(ValidationError, match="write_hosts"):
        cfg(write_hosts=[bad])


def test_authorization_record_lists_write_hosts() -> None:
    rec = AuthorizationRecord(confirmed_by="me", method="config",
                              confirmed_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert rec.write_hosts == []


def test_tool_version_matches_pyproject() -> None:
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["version"] == TOOL_VERSION
    assert USER_AGENT == f"RLSentry/{TOOL_VERSION}"


def test_secret_patterns() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.c2lnbmF0dXJl"
    assert JWT_RE.fullmatch(jwt)
    assert SB_KEY_RE.fullmatch("sb_" + "secret_abcdefghijklmnop")
    assert not SB_KEY_RE.search("sb_secret_short")


def test_lab_models_forbid_extra_and_keep_no_values() -> None:
    assert set(DbWrite.model_fields) == {"role", "command"}
    with pytest.raises(ValidationError):
        LabInfo.model_validate({"api_url": "a", "db_url": "b", "anon_key": "c",
                                "service_role_key": "d", "extra": "x"})
    assert POSTGREST_ROLES == {"anon", "authenticated", "authenticator"}
