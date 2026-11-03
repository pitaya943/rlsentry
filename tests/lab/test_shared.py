"""Shared lab (T-060): lab/_shared/labctl.py against rlsentry/contracts/lab.py. Needs Docker."""
import httpx
import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS, SCENARIO_IDS
from rlsentry.contracts.lab import LAB_DEFAULT_PASSWORDS, POSTGREST_ROLES, LabInfo
from rlsentry.contracts.models import Role
from tests.lab.oracle import jwt_claims


def test_ensure_up_is_idempotent_and_local(lab_info: LabInfo) -> None:
    again = labctl.ensure_up()
    assert again == lab_info
    assert lab_info.api_url.startswith(("http://127.0.0.1:", "http://localhost:"))
    assert "@127.0.0.1:" in lab_info.db_url or "@localhost:" in lab_info.db_url
    assert jwt_claims(lab_info.anon_key)["role"] == "anon"
    assert jwt_claims(lab_info.service_role_key)["role"] == "service_role"


def test_log_statement_is_mod(lab_info: LabInfo) -> None:
    assert labctl.query("show log_statement") == [("mod",)]


def test_query_returns_text_tuples(lab_info: LabInfo) -> None:
    assert labctl.query("select 1, null::text, 'x'") == [("1", "", "x")]


def test_scenario_dir(lab_info: LabInfo) -> None:
    for sid in SCENARIO_IDS:
        assert labctl.scenario_dir(sid).name.startswith(sid + "_")
    with pytest.raises(ValueError):
        labctl.scenario_dir("L99")
    with pytest.raises(ValueError):
        labctl.apply("L99")


def test_lab_password_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LAB_USERS[Role.USER_A]["password_env"], raising=False)
    assert labctl.lab_password(Role.USER_A) == LAB_DEFAULT_PASSWORDS[Role.USER_A]
    monkeypatch.setenv(LAB_USERS[Role.USER_B]["password_env"], "from-env")
    assert labctl.lab_password(Role.USER_B) == "from-env"


def test_lock_is_reentrant() -> None:
    with labctl.lock(), labctl.lock():
        pass


@pytest.mark.safety
def test_login_writes_only_as_gotrue_and_are_attributed(lab_info: LabInfo) -> None:
    """ADR-014 #2: GoTrue's auth.* writes are logged under its own role, never a PostgREST role."""
    marker = labctl.db_log_marker()
    for role in (Role.USER_A, Role.USER_B):
        r = httpx.post(f"{lab_info.api_url}/auth/v1/token", params={"grant_type": "password"},
                       headers={"apikey": lab_info.anon_key},
                       json={"email": LAB_USERS[role]["email"], "password": labctl.lab_password(role)})
        assert r.status_code == 200, f"{role.value} login HTTP {r.status_code}"
        assert jwt_claims(r.json()["access_token"])["sub"] == LAB_USERS[role]["id"]
    writes = labctl.db_writes_since(marker)
    assert writes, "login must leave writes in the DB log (log_statement = mod)"
    assert not {w.role for w in writes} & POSTGREST_ROLES
    assert all(w.command.isupper() and w.command.isalpha() for w in writes)
