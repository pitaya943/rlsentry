"""report/sarif.py: SARIF 2.1.0 log for GitHub code scanning (FR-13; ADR-044)."""
from __future__ import annotations

import json
from typing import Any

from rlsentry.contracts.models import Evidence, Finding, ScanReport, Severity
from rlsentry.contracts.report import REFERENCES, SARIF_SCHEMA_URI, TOOL_URI
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.safety import TOOL_VERSION
from rlsentry.recon.links import report_url
from rlsentry.safety.mask import mask_text


def sarif_level(finding: Finding) -> str:
    """Only Confirmed findings annotate as error/warning; the rest stay notes.

    Why: code scanning should not alarm on unproven signals (MS6 focus).
    """
    if finding.evidence is not Evidence.CONFIRMED:
        return "note"
    if finding.severity in (Severity.CRITICAL, Severity.HIGH):
        return "error"
    if finding.severity in (Severity.MEDIUM, Severity.LOW):
        return "warning"
    return "note"


def _rule(rule_id: str) -> dict[str, Any]:
    spec = RULES[rule_id]
    out: dict[str, Any] = {
        "id": rule_id,
        "name": rule_id,
        "shortDescription": {"text": spec.description},
        "properties": {"evidence": spec.evidence.value, "severity": spec.severity.value},
    }
    if REFERENCES.get(rule_id):
        out["helpUri"] = REFERENCES[rule_id][0]
    return out


def _result(f: Finding, config_path: str) -> dict[str, Any]:
    text = (f"{f.title or RULES[f.rule].description} — target {f.target or '-'}, "
            f"role {f.role.value if f.role else '-'}, op {f.op.value if f.op else '-'}")
    return {
        "ruleId": f.rule,
        "level": sarif_level(f),
        "message": {"text": text},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": config_path}}}],
        "partialFingerprints": {"rlsentryFindingId/v1": f.id},
        "properties": {
            "evidence": f.evidence.value,
            "severity": f.severity.value,
            "target": f.target,
            "role": f.role.value if f.role else None,
            "op": f.op.value if f.op else None,
            "correlation": f.correlation,
        },
    }


def render_sarif(report: ScanReport, config_path: str = "rlsentry.yaml") -> str:
    """Render the report as SARIF 2.1.0 JSON, masked as a last step (NFR-03)."""
    rule_ids = list(dict.fromkeys(f.rule for f in report.findings))
    run = {
        "tool": {"driver": {
            "name": "RLSentry", "version": TOOL_VERSION, "informationUri": TOOL_URI,
            "rules": [_rule(r) for r in rule_ids],
        }},
        "results": [_result(f, config_path) for f in report.findings],
        "properties": {"profile": report.profile.value, "target": report_url(report.target)},
    }
    doc = {"version": "2.1.0", "$schema": SARIF_SCHEMA_URI, "runs": [run]}
    return mask_text(json.dumps(doc, indent=2, ensure_ascii=False))
