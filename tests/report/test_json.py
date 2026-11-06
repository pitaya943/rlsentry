"""report/json.py: the JSON report (FR-12; NFR-03; ADR-044)."""
from __future__ import annotations

import json

from rlsentry.contracts.models import ScanReport
from rlsentry.report.json import render_json
from tests.report.helpers import JWT, report


def test_round_trips_and_keeps_every_field() -> None:
    rep = report()
    text = render_json(rep)
    back = ScanReport.model_validate_json(text)
    assert [(f.id, f.rule, f.evidence, f.severity) for f in back.findings] == \
        [(f.id, f.rule, f.evidence, f.severity) for f in rep.findings]
    curl = back.findings[1].probes[0].evidence_curl
    assert curl.startswith("curl -sS -X GET") and JWT not in curl and "****" in curl      # masked, kept
    data = json.loads(text)
    assert data["authorization"]["confirmed_by"] == "tester" and data["profile"] == "dev"
    assert data["modules"] == ["M1", "M2", "M3", "M5"] and "notes" in data and "timings" in data
    assert data["policies"] == []


def test_no_full_key_anywhere_and_target_has_no_query() -> None:
    text = render_json(report(target=f"http://app.test/?token={JWT}"))
    assert JWT not in text and "token=" not in text
    assert json.loads(text)["target"] == "http://app.test/?…"
