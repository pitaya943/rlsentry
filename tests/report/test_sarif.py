"""report/sarif.py: SARIF 2.1.0 (FR-13; ADR-044), validated against the official OASIS schema.

sarif-schema-2.1.0.json is a verbatim copy of
https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json
(sha256 c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e), fetched once by the
architect; tests never use the network.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from rlsentry.contracts.models import Evidence, Op, Profile, Role, Severity
from rlsentry.contracts.report import REFERENCES, SARIF_SCHEMA_URI, TOOL_URI
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.safety import TOOL_VERSION
from rlsentry.report.sarif import render_sarif, sarif_level
from tests.report.helpers import JWT, finding, report

SCHEMA = Path(__file__).with_name("sarif-schema-2.1.0.json")


def test_vendored_schema_is_the_official_file() -> None:
    digest = hashlib.sha256(SCHEMA.read_bytes()).hexdigest()
    assert digest == "c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e"


def test_valid_against_the_oasis_schema() -> None:
    doc = json.loads(render_sarif(report(profile=Profile.CI)))
    jsonschema.validate(doc, json.loads(SCHEMA.read_text("utf-8")))
    assert doc["version"] == "2.1.0" and doc["$schema"] == SARIF_SCHEMA_URI


def test_tool_rules_and_results() -> None:
    rep = report(profile=Profile.CI)
    doc = json.loads(render_sarif(rep, config_path="conf/rlsentry.yaml"))
    [run] = doc["runs"]
    drv = run["tool"]["driver"]
    assert (drv["name"], drv["version"], drv["informationUri"]) == ("RLSentry", TOOL_VERSION, TOOL_URI)
    assert [r["id"] for r in drv["rules"]] == [f.rule for f in rep.findings]          # distinct here
    cross = next(r for r in drv["rules"] if r["id"] == "CROSS_TENANT_READ")
    assert cross["shortDescription"]["text"] == RULES["CROSS_TENANT_READ"].description
    assert cross["helpUri"] == REFERENCES["CROSS_TENANT_READ"][0]
    assert cross["properties"] == {"evidence": "confirmed", "severity": "medium"}
    res = run["results"]
    assert len(res) == len(rep.findings)
    for r, f in zip(res, rep.findings, strict=True):
        assert r["ruleId"] == f.rule and r["partialFingerprints"] == {"rlsentryFindingId/v1": f.id}
        assert r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "conf/rlsentry.yaml"
        assert r["properties"]["evidence"] == f.evidence.value and r["properties"]["severity"] == f.severity.value
    assert run["properties"] == {"profile": "ci", "target": "http://app.test/"}


def test_message_names_target_role_and_op() -> None:
    doc = json.loads(render_sarif(report(findings=[finding("CROSS_TENANT_READ", "notes", Role.USER_B, Op.SELECT)])))
    text = doc["runs"][0]["results"][0]["message"]["text"]
    assert "notes" in text and "user_b" in text and "select" in text


@pytest.mark.parametrize("evidence, severity, level", [
    (Evidence.CONFIRMED, Severity.CRITICAL, "error"), (Evidence.CONFIRMED, Severity.HIGH, "error"),
    (Evidence.CONFIRMED, Severity.MEDIUM, "warning"), (Evidence.CONFIRMED, Severity.LOW, "warning"),
    (Evidence.SUSPECTED, Severity.CRITICAL, "note"), (Evidence.CONFIG_WARNING, Severity.HIGH, "note"),
    (Evidence.SUSPECTED, Severity.REVIEW, "note"),
])
def test_levels(evidence: Evidence, severity: Severity, level: str) -> None:
    f = finding("CROSS_TENANT_READ", "t", Role.USER_A, Op.SELECT, severity=severity, evidence=evidence)
    assert sarif_level(f) == level


def test_no_full_key_or_query() -> None:
    text = render_sarif(report(target=f"http://app.test/?k={JWT}"))
    assert JWT not in text and "k=eyJ" not in text
