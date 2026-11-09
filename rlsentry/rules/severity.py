"""Rule selection and severity for confirmed reads (SPEC §5 M5; ADR-023). Pure functions."""
from __future__ import annotations

from rlsentry.contracts.models import Op, Role, Severity
from rlsentry.contracts.rules import RULES, SENSITIVE_COLUMN_PATTERNS


def is_sensitive_column(name: str) -> bool:
    """True iff a sensitive pattern is a substring of the lower-cased name (Critical trigger)."""
    low = name.lower()
    return any(p in low for p in SENSITIVE_COLUMN_PATTERNS)


def read_rule(target_kind: str, role: Role) -> str:
    """Rule id for a confirmed read beyond scope, by role only (ADR-039).

    M3 cannot know whether an RPC is SECURITY DEFINER; M4 correlate relabels when proven.
    """
    del target_kind
    if role is Role.ANON:
        return "ANON_READ_OWNER_SCOPED"
    return "CROSS_TENANT_READ"


def read_severity(rule: str, columns: list[str]) -> Severity:
    """Escalate only on known sensitive columns; unknown columns never escalate. KeyError on bad rule."""
    spec = RULES[rule]
    if spec.escalates_to is not None and any(is_sensitive_column(c) for c in columns):
        return spec.escalates_to
    return spec.severity


def write_rule(role: Role, op: Op) -> str:
    """Rule id for a confirmed forbidden write; `op` is accepted for symmetry (ADR-029 #4)."""
    del op
    return "ANON_WRITE" if role is Role.ANON else "CROSS_TENANT_WRITE"
