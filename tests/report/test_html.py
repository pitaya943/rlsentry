"""report/html.py: the static HTML report (FR-12; NFR-03; ADR-044)."""
from __future__ import annotations

import re

from rlsentry.contracts.models import Op, PolicyRow, Role
from rlsentry.contracts.policy import ScanConfig
from rlsentry.report.enrich import enrich
from rlsentry.report.html import render_html
from tests.report.helpers import JWT, finding, report

CONFIG = ScanConfig(target="http://app.test")


def html(target: str = "http://app.test/") -> str:
    return render_html(enrich(report(target=target), CONFIG))


def test_document_structure_and_evidence_sections_in_order() -> None:
    doc = html()
    assert doc.lstrip().lower().startswith("<!doctype html>") and 'lang="zh-Hant"' in doc
    pos = [doc.index(h) for h in ("Confirmed", "Suspected", "Configuration warning")]
    assert pos == sorted(pos)
    for needle in ("tester", "cli_flag", "http://127.0.0.1:54321", "CROSS_TENANT_READ", "SECRET_KEY_IN_BUNDLE",
                   "INCONCLUSIVE_CELL", "SECURITY_DEFINER_EXECUTABLE", "M4 skipped", "notes", "user_b"):
        assert needle in doc, needle
    assert "<pre" in doc and "CREATE POLICY" in doc and "curl -sS" in doc
    assert 'href="https://supabase.com/docs/' in doc


def test_self_contained_no_script_no_external_resources() -> None:
    doc = html()
    assert "<script" not in doc.lower()
    assert not re.search(r"<(link|img|iframe)\b", doc, re.IGNORECASE)
    assert not re.search(r"""\bsrc\s*=\s*["']?https?:""", doc, re.IGNORECASE)
    assert "@import" not in doc and "url(" not in doc


def test_values_are_escaped() -> None:
    hostile = finding("CROSS_TENANT_READ", "<script>alert(1)</script>", Role.USER_A, Op.SELECT)
    doc = render_html(report(findings=[hostile], policies=[PolicyRow(
        schema="public", table="t", name="<b>p</b>", command="SELECT", roles=["anon"], permissive=True,
        using="x < 1 AND y > 2")]))
    assert "<script>alert(1)</script>" not in doc and "&lt;script&gt;" in doc
    assert "<b>p</b>" not in doc and "x &lt; 1" in doc


def test_keys_and_queries_never_appear() -> None:
    doc = html(target=f"http://app.test/?k={JWT}")
    assert JWT not in doc and "k=eyJ" not in doc
