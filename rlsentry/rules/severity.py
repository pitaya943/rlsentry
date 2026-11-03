"""Rule selection and severity for confirmed reads (SPEC §5 M5; ADR-023). Pure functions."""
from __future__ import annotations

from rlsentry.contracts.models import Role, Severity
from rlsentry.contracts.rules import RULES, SENSITIVE_COLUMN_PATTERNS


def is_sensitive_column(name: str) -> bool:
    """True iff a sensitive pattern is a substring of the lower-cased name (Critical trigger)."""
    low = name.lower()
    return any(p in low for p in SENSITIVE_COLUMN_PATTERNS)


def read_rule(target_kind: str, role: Role) -> str:
    """Rule id for a confirmed read beyond scope: an RPC is always the L07 pattern."""
    if target_kind == "rpc":
        return "SECURITY_DEFINER_RPC_DATA"
    if role is Role.ANON:
        return "ANON_READ_OWNER_SCOPED"
    return "CROSS_TENANT_READ"


def read_severity(rule: str, columns: list[str]) -> Severity:
    """Escalate only on known sensitive columns; unknown columns never escalate. KeyError on bad rule."""
    spec = RULES[rule]
    if spec.escalates_to is not None and any(is_sensitive_column(c) for c in columns):
        return spec.escalates_to
    return spec.severity
