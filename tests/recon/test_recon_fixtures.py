"""recon(): the three real-framework builds end to end (SPEC §9 測試層級; FR-01..03; T-189).

Expected values are documented in tests/recon/fixtures/README.md. Exact key lists also prove the
absence of false positives on real minified code and real source maps (supabase-js docs inside).
"""
from __future__ import annotations

import pytest

from rlsentry.contracts.models import Evidence, Severity
from rlsentry.contracts.recon import ReconOutput
from rlsentry.recon.run import recon
from tests.fakes import Recorder, run
from tests.recon.helpers import FIXTURE_SECRETS, FIXTURES, ORIGIN, StaticSite

EXPECTED = {
    "nextjs": ("https://fxtrnextjsfixture0001.supabase.co",
               [("jwt:anon", "publishable"), ("jwt:service_role", "secret"),
                ("jwt:authenticated", "unverified")],
               [("jwt:service_role", "SECRET_KEY_IN_BUNDLE"), ("jwt:authenticated", "UNVERIFIED_KEY")]),
    "vite": ("https://fxtrvitefixture000001.supabase.co",
             [("sb_publishable", "publishable"), ("jwt:service_role", "secret")],
             [("jwt:service_role", "SECRET_KEY_IN_BUNDLE")]),
    "cra": ("https://api.fixture-cra.example",
            [("jwt:anon", "publishable"), ("unverified", "unverified")],
            [("unverified", "UNVERIFIED_KEY")]),
}

# Lazily loaded files that only static structure reveals (ADR-037 rationale).
LAZY = {
    "nextjs": ["/_next/static/chunks/pages/admin-5f184c93fe297a37.js",   # _buildManifest only
               "/_next/static/chunks/43.45a1b549800bdb67.js"],           # webpack u() + l.e(43)
    "vite": ["/assets/Admin-DJaTEGsj.js", "/assets/Admin-DJaTEGsj.js.map"],  # import(`./Admin…`)
    "cra": ["/static/js/203.08bac55d.chunk.js", "/static/js/453.cfd0efe7.chunk.js",
            "/static/js/203.08bac55d.chunk.js.map"],                    # webpack chunk map
}


def _recon(fw: str) -> tuple[ReconOutput, StaticSite]:
    site = StaticSite(FIXTURES / fw)
    return run(lambda c: recon(c, ORIGIN + "/"), Recorder(site)), site


@pytest.mark.parametrize("fw", ["nextjs", "vite", "cra"])
def test_framework_keys_url_and_findings(fw: str) -> None:
    out, _ = _recon(fw)
    url, keys, findings = EXPECTED[fw]
    assert out.result.supabase_url == url
    assert [(k.label, k.kind) for k in out.result.keys] == keys
    assert [(f.target, f.rule) for f in out.findings] == findings
    for f in out.findings:
        if f.rule == "SECRET_KEY_IN_BUNDLE":
            assert (f.evidence, f.severity) == (Evidence.CONFIRMED, Severity.CRITICAL)
        else:
            assert f.evidence is Evidence.CONFIG_WARNING


@pytest.mark.parametrize("fw", ["nextjs", "vite", "cra"])
def test_framework_lazy_chunks_scanned(fw: str) -> None:
    out, site = _recon(fw)
    scanned = out.result.chunks_scanned
    assert scanned[0] == ORIGIN + "/"
    for path in LAZY[fw]:
        assert ORIGIN + path in scanned
    assert len(scanned) == len(set(scanned)) == len(site.requests) - len(out.result.chunks_skipped)


def test_cra_missing_map_is_listed_as_skipped() -> None:
    out, _ = _recon("cra")
    assert out.result.chunks_skipped == [ORIGIN + "/static/js/main.f5d1831d.js.map (HTTP 404)"]


@pytest.mark.parametrize("fw, kind", [("nextjs", "eyJ"), ("vite", "sb_publishable_"), ("cra", "eyJ")])
def test_anon_key_handed_to_m2(fw: str, kind: str) -> None:
    out, _ = _recon(fw)
    assert out.anon_key is not None and out.anon_key.startswith(kind)
    assert out.anon_key in FIXTURE_SECRETS[fw]


def test_sources_feed_bundle_inference() -> None:
    # M2 (FR-05) infers .from()/.rpc() targets from these texts; the lazy admin page is included.
    out, _ = _recon("nextjs")
    assert any('.rpc("list_all_users")' in s for s in out.sources)
    assert any('.from("notes")' in s for s in out.sources)
