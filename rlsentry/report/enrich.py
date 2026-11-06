"""report/enrich.py: M5 adds title, repro, references and fix SQL, then sorts (ADR-044)."""
from __future__ import annotations

from rlsentry.contracts.models import SEVERITY_RANK, Finding, Op, ScanReport
from rlsentry.contracts.policy import ScanConfig
from rlsentry.contracts.report import EVIDENCE_RANK, REFERENCES, FixContext
from rlsentry.contracts.rules import RULES
from rlsentry.policy.resolve import resolve_expected
from rlsentry.report.fix_sql import fix_sql
from rlsentry.safety.mask import mask_text


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Order by evidence, then severity (SPEC §5 M5), with deterministic tie-breakers."""
    return sorted(findings, key=lambda f: (
        -EVIDENCE_RANK[f.evidence], -SEVERITY_RANK[f.severity], f.target or "", f.rule,
        f.role.value if f.role else "", f.op.value if f.op else "", f.id))


def _enrich_one(f: Finding, report: ScanReport, config: ScanConfig) -> Finding:
    schema = config.db_schemas[0]
    target = None
    if report.discovery is not None:
        target = next((t for t in report.discovery.targets if t.name == f.target), None)
    ctx = FixContext(
        kind=target.kind if target else None, schema_name=schema,
        policies=[p for p in report.policies if p.table == f.target and p.schema_ == schema])
    if f.target and f.role:
        exp = resolve_expected(config.policy, f.target, f.op or Op.SELECT, f.role,
                               tuple(target.columns) if target else ())
        ctx = ctx.model_copy(update={"scope": exp.scope, "owner_column": exp.owner_column,
                                     "public_column": exp.public_column})
    curl = next((p.evidence_curl for p in f.probes if p.evidence_curl), "")
    return f.model_copy(update={
        "title": RULES[f.rule].description,
        "repro": mask_text(curl) if curl else None,
        "references": list(REFERENCES.get(f.rule, ())),
        "fix_sql": fix_sql(f, ctx)})


def enrich(report: ScanReport, config: ScanConfig) -> ScanReport:
    """Return a sorted copy of the report with title, repro, references and fix SQL filled in."""
    out = [_enrich_one(f, report, config) for f in report.findings]
    return report.model_copy(update={"findings": sort_findings(out)})
