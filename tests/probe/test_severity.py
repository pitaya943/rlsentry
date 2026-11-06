"""rules/severity.py. Contract: rlsentry/contracts/rules.py (is_sensitive_column, read_rule, read_severity)."""
import pytest

from rlsentry.contracts.models import Role, Severity
from rlsentry.rules.severity import is_sensitive_column, read_rule, read_severity


@pytest.mark.parametrize("name,hit", [("email", True), ("Contact_EMAIL", True), ("phone_number", True),
                                      ("refresh_token", True), ("password_hash", True), ("api_secret", True),
                                      ("ssn", True), ("display_name", False), ("owner_id", False), ("", False)])
def test_sensitive_columns(name: str, hit: bool) -> None:
    assert is_sensitive_column(name) is hit


@pytest.mark.parametrize("kind,role,rule", [
    ("table", Role.ANON, "ANON_READ_OWNER_SCOPED"), ("view", Role.ANON, "ANON_READ_OWNER_SCOPED"),
    ("table", Role.USER_A, "CROSS_TENANT_READ"), ("table", Role.USER_B, "CROSS_TENANT_READ"),
    # RPC rows moved to tests/probe/test_rule_rpc.py (ADR-039: the RPC rule changed in MS6)
])
def test_read_rule(kind: str, role: Role, rule: str) -> None:
    assert read_rule(kind, role) == rule


def test_read_severity() -> None:
    assert read_severity("ANON_READ_OWNER_SCOPED", ["id", "owner_id", "name", "email"]) is Severity.CRITICAL
    assert read_severity("ANON_READ_OWNER_SCOPED", ["id", "body"]) is Severity.HIGH
    assert read_severity("ANON_READ_OWNER_SCOPED", []) is Severity.HIGH
    assert read_severity("CROSS_TENANT_READ", ["email"]) is Severity.MEDIUM   # no escalates_to
    with pytest.raises(KeyError):
        read_severity("NOT_A_RULE", [])
