"""M4 correlation of probe findings and splinter lints (SPEC §5 M4; ADR-032). Pure.

Why: M4 only annotates probe findings and adds non-vulnerability warnings, so a SECURITY
DEFINER object is a vulnerability only if the probe actually obtained protected rows."""
from __future__ import annotations

from collections.abc import Sequence

from rlsentry.contracts.models import Evidence, Finding, Op, Role, finding_id
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.whitebox import (
    DEFAULT_DB_SCHEMAS,
    SECURITY_CATEGORY,
    SECURITY_DEFINER_LINTS,
    Lint,
)


def _proven(f: Finding) -> bool:
    return (f.evidence is Evidence.CONFIRMED and RULES[f.rule].vulnerability
            and f.target is not None)


def _warning(target: str, rule: str, role: Role | None, op: Op | None, lint: str) -> Finding:
    spec = RULES[rule]
    return Finding(id=finding_id(target, role, op, rule), rule=rule, evidence=spec.evidence,
                   severity=spec.severity, target=target, role=role, op=op, probes=[],
                   lint=lint, correlation="lint_only")


def correlate(findings: list[Finding], lints: list[Lint],
              db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[Finding]:
    """Annotate proven findings confirmed/probe_only and add lint-only warnings (see contract)."""
    schemas = set(db_schemas)
    by_object: dict[str, list[Lint]] = {}
    for ln in lints:
        if (SECURITY_CATEGORY in ln.categories and ln.object_name is not None
                and ln.object_schema in schemas):
            by_object.setdefault(ln.object_name, []).append(ln)

    out: list[Finding] = []
    proven_targets: set[str] = set()
    for f in findings:
        if f.target is not None and _proven(f):
            proven_targets.add(f.target)
            names = sorted({ln.name for ln in by_object.get(f.target, [])})
            if names:
                out.append(f.model_copy(update={"correlation": "confirmed", "lint": ",".join(names)}))
            else:
                out.append(f.model_copy(update={"correlation": "probe_only", "lint": None}))
        else:
            out.append(f.model_copy())

    seen = {f.id for f in out}
    new: list[Finding] = []
    for obj, obj_lints in by_object.items():
        if obj in proven_targets:
            continue
        for name in sorted({ln.name for ln in obj_lints if ln.name in SECURITY_DEFINER_LINTS}):
            role_value = SECURITY_DEFINER_LINTS[name]
            new.append(_warning(obj, "SECURITY_DEFINER_EXECUTABLE",
                                Role(role_value) if role_value else None, Op.SELECT, name))
        others = sorted({ln.name for ln in obj_lints if ln.name not in SECURITY_DEFINER_LINTS})
        if others:
            new.append(_warning(obj, "LINT_ONLY", None, None, ",".join(others)))

    new.sort(key=lambda f: (f.target or "", f.rule, f.role.value if f.role else ""))
    for f in new:
        if f.id not in seen:
            seen.add(f.id)
            out.append(f)
    return out
