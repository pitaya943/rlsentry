"""Contract tests for rlsentry.contracts.models and .rules (T-010). SPEC §6, §5 M5."""
import pytest
from pydantic import ValidationError

from rlsentry.contracts.models import (
    SEVERITY_RANK,
    Evidence,
    Finding,
    KeyFinding,
    Op,
    Outcome,
    ProbeResult,
    Role,
    Severity,
    finding_id,
)
from rlsentry.contracts.rules import RULES, SENSITIVE_COLUMN_PATTERNS


def _probe(outcome: Outcome, known: int, op: Op = Op.SELECT) -> ProbeResult:
    return ProbeResult(target="notes", role=Role.USER_B, op=op, outcome=outcome,
                       known_rows_checked=known, reason="r", evidence_curl="curl ...")


def test_enum_values_match_spec_section_6() -> None:
    assert [r.value for r in Role] == ["anon", "user_a", "user_b"]
    assert [o.value for o in Op] == ["select", "insert", "update", "delete"]
    assert [o.value for o in Outcome] == ["allowed", "denied", "inconclusive", "not_tested"]
    assert [e.value for e in Evidence] == ["confirmed", "suspected", "config_warning"]
    assert [s.value for s in Severity] == ["critical", "high", "medium", "low", "review"]


@pytest.mark.safety
@pytest.mark.parametrize("op", list(Op))
def test_zero_known_rows_can_never_be_a_verdict(op: Op) -> None:
    # SPEC §6: known_rows_checked == 0 ⇒ inconclusive; "denied" would read as "safe".
    for outcome in (Outcome.ALLOWED, Outcome.DENIED):
        with pytest.raises(ValidationError):
            _probe(outcome, 0, op)
    assert _probe(Outcome.INCONCLUSIVE, 0, op).outcome is Outcome.INCONCLUSIVE
    assert _probe(Outcome.NOT_TESTED, 0, op).outcome is Outcome.NOT_TESTED
    assert _probe(Outcome.DENIED, 1, op).outcome is Outcome.DENIED


def test_finding_id_is_stable_and_content_based() -> None:
    a = finding_id("notes", Role.USER_B, Op.SELECT, "CROSS_TENANT_READ")
    assert a == finding_id("notes", Role.USER_B, Op.SELECT, "CROSS_TENANT_READ")
    assert len(a) == 16 and int(a, 16) >= 0
    assert a != finding_id("notes", Role.USER_A, Op.SELECT, "CROSS_TENANT_READ")
    assert finding_id(None, None, None, "SECRET_KEY_IN_BUNDLE") != finding_id("x", None, None, "SECRET_KEY_IN_BUNDLE")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate({"id": "x", "rule": "ANON_WRITE", "evidence": "confirmed",
                                "severity": "critical", "raw_rows": [{"email": "a@b"}]})


def test_key_finding_kind_is_restricted() -> None:
    KeyFinding(kind="publishable", masked="eyJhbG…abcd", source_file="a.js")
    with pytest.raises(ValidationError):
        KeyFinding(kind="anon", masked="x", source_file="a.js")


def test_severity_rank_orders_review_lowest() -> None:
    order = sorted(Severity, key=lambda s: -SEVERITY_RANK[s])
    assert order == [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.REVIEW]


def test_rule_catalog_matches_spec_severity_table() -> None:
    # SPEC §5 M5 嚴重度表
    assert RULES["SECRET_KEY_IN_BUNDLE"].severity is Severity.CRITICAL
    assert RULES["ANON_WRITE"].severity is Severity.CRITICAL
    assert RULES["ANON_READ_OWNER_SCOPED"].severity is Severity.HIGH
    assert RULES["ANON_READ_OWNER_SCOPED"].escalates_to is Severity.CRITICAL
    assert RULES["CROSS_TENANT_WRITE"].severity is Severity.HIGH
    assert RULES["CROSS_TENANT_READ"].severity is Severity.MEDIUM
    assert RULES["SECURITY_DEFINER_RPC_DATA"].severity is Severity.MEDIUM
    assert RULES["NO_OWNER_COLUMN"].severity is Severity.REVIEW
    assert {"email", "phone", "token"} <= set(SENSITIVE_COLUMN_PATTERNS)


def test_only_confirmed_rules_are_vulnerabilities() -> None:
    # SPEC §5 M5: SECURITY DEFINER without data, lint-only, unverified key are config warnings.
    for r in RULES.values():
        assert r.id == r.id.upper()
        if r.vulnerability:
            assert r.evidence is Evidence.CONFIRMED, r.id
    assert RULES["SECURITY_DEFINER_EXECUTABLE"].evidence is Evidence.CONFIG_WARNING
    assert RULES["UNVERIFIED_KEY"].evidence is Evidence.CONFIG_WARNING
    assert RULES["INCONCLUSIVE_CELL"].evidence is Evidence.SUSPECTED
