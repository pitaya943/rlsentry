"""M4 correlation of probe findings and splinter lints (SPEC §5 M4; ADR-032). Pure.

Why: M4 only annotates probe findings and adds non-vulnerability warnings, so a SECURITY
DEFINER object is a vulnerability only if the probe actually obtained protected rows."""
from __future__ import annotations

from collections.abc import Sequence

from rlsentry.contracts.models import Evidence, Finding, Op, Role, finding_id
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.whitebox import (
    DEFAULT_DB_SCHEMAS,
    DEFINER_LINT_ROLES,
    DEFINER_RELABEL_RULES,
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
    proven_roles: dict[str, set[Role]] = {}
    for f in findings:
        if f.target is not None and _proven(f):
            if f.role is not None:
                proven_roles.setdefault(f.target, set()).add(f.role)
            else:
                proven_roles.setdefault(f.target, set())
            obj_lints = by_object.get(f.target, [])
            names = sorted({ln.name for ln in obj_lints})
            if not names:
                out.append(f.model_copy(update={"correlation": "probe_only", "lint": None}))
                continue
            update: dict[str, object] = {"correlation": "confirmed", "lint": ",".join(names)}
            if (f.rule in DEFINER_RELABEL_RULES and f.op is Op.SELECT and f.role is not None
                    and any(ln.name in SECURITY_DEFINER_LINTS
                            and f.role in DEFINER_LINT_ROLES[ln.name] for ln in obj_lints)):
                rule = "SECURITY_DEFINER_RPC_DATA"
                update.update(rule=rule, severity=RULES[rule].severity,
                              id=finding_id(f.target, f.role, f.op, rule))
            out.append(f.model_copy(update=update))
        else:
            out.append(f.model_copy())

    seen = {f.id for f in out}
    new: list[Finding] = []
    for obj, obj_lints in by_object.items():
        proven = proven_roles.get(obj)
        for name in sorted({ln.name for ln in obj_lints if ln.name in SECURITY_DEFINER_LINTS}):
            if proven and proven & DEFINER_LINT_ROLES[name]:
                continue
            role_value = SECURITY_DEFINER_LINTS[name]
            new.append(_warning(obj, "SECURITY_DEFINER_EXECUTABLE",
                                Role(role_value) if role_value else None, Op.SELECT, name))
        if proven is not None:
            continue
        others = sorted({ln.name for ln in obj_lints if ln.name not in SECURITY_DEFINER_LINTS})
        if others:
            new.append(_warning(obj, "LINT_ONLY", None, None, ",".join(others)))

    new.sort(key=lambda f: (f.target or "", f.rule, f.role.value if f.role else ""))
    for f in new:
        if f.id not in seen:
            seen.add(f.id)
            out.append(f)
    return out
