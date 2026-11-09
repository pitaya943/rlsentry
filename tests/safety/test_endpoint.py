"""safety/endpoint.py: S4 — the Supabase URL must be named by the user (ADR-043; MS5 note 6).

Contract: rlsentry/contracts/pipeline.py normalize_api_url, resolve_endpoint. Pure functions;
the "zero requests" property of the whole pipeline is in tests/pipeline/test_run_scan_safety.py.
"""
from __future__ import annotations

import pytest

from rlsentry.contracts.pipeline import EndpointRefused
from rlsentry.contracts.policy import ScanConfig
from rlsentry.safety.endpoint import normalize_api_url, resolve_endpoint

pytestmark = pytest.mark.safety
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJlLW5vdC12ZXJpZmllZA"


@pytest.mark.parametrize("raw, norm", [
    ("https://abc.supabase.co", "https://abc.supabase.co"),
    ("https://ABC.Supabase.CO/", "https://abc.supabase.co"),
    ("HTTPS://abc.supabase.co:443", "https://abc.supabase.co"),
    ("http://127.0.0.1:54321/", "http://127.0.0.1:54321"),
    ("http://localhost:80", "http://localhost"),
    ("https://api.example.test:8443", "https://api.example.test:8443"),
])
def test_normalize(raw: str, norm: str) -> None:
    assert normalize_api_url(raw) == norm


@pytest.mark.parametrize("bad", [
    "ftp://abc.supabase.co", "https://", "abc.supabase.co", "https://abc.supabase.co/rest/v1",
    "https://abc.supabase.co?apikey=x", "https://abc.supabase.co#frag", "https://u:p@abc.supabase.co",
    "javascript:alert(1)",
])
def test_normalize_rejects(bad: str) -> None:
    with pytest.raises(EndpointRefused) as exc:
        normalize_api_url(bad)
    assert str(exc.value).startswith("invalid Supabase URL ")


def test_rejection_message_never_echoes_secrets() -> None:
    with pytest.raises(EndpointRefused) as exc:
        normalize_api_url(f"https://user:hunter2@abc.supabase.co/x?apikey={JWT}")
    msg = str(exc.value)
    assert "hunter2" not in msg and JWT not in msg and "apikey" not in msg


def cfg(url: str | None = None) -> ScanConfig:
    return ScanConfig(target="https://app.example.test", supabase_url=url)


def test_config_url_wins_and_the_bundle_url_is_ignored() -> None:
    assert resolve_endpoint(cfg("https://ABC.supabase.co/"), None, "https://evil.test") == \
        ("https://abc.supabase.co", "config")


def test_cli_flag_names_the_url() -> None:
    assert resolve_endpoint(cfg(), "http://127.0.0.1:54321/", None) == ("http://127.0.0.1:54321", "cli_flag")


def test_same_url_in_config_and_cli_is_config() -> None:
    assert resolve_endpoint(cfg("https://abc.supabase.co"), "https://ABC.supabase.co/", None) == \
        ("https://abc.supabase.co", "config")


def test_config_and_cli_disagree() -> None:
    with pytest.raises(EndpointRefused) as exc:
        resolve_endpoint(cfg("https://abc.supabase.co"), "https://other.supabase.co", None)
    assert "disagree" in str(exc.value)


@pytest.mark.parametrize("found", ["https://abc.supabase.co", "https://app.example.test"])
def test_a_bundle_url_alone_is_never_used(found: str) -> None:
    # even when it is the real project or the target's own origin (MS5 approval note 6)
    with pytest.raises(EndpointRefused) as exc:
        resolve_endpoint(cfg(), None, found)
    msg = str(exc.value)
    assert found in msg and "supabase_url" in msg and "--supabase-url" in msg


def test_bundle_url_in_the_message_goes_through_report_url() -> None:
    with pytest.raises(EndpointRefused) as exc:
        resolve_endpoint(cfg(), None, f"https://u:pw@evil.test/x?k={JWT}")
    msg = str(exc.value)
    assert "pw@" not in msg and JWT not in msg and "evil.test" in msg


def test_no_url_anywhere() -> None:
    with pytest.raises(EndpointRefused) as exc:
        resolve_endpoint(cfg(), None, None)
    assert "no Supabase URL" in str(exc.value)


def test_malformed_config_or_cli_url_is_refused() -> None:
    with pytest.raises(EndpointRefused):
        resolve_endpoint(cfg("https://abc.supabase.co/rest/v1"), None, None)
    with pytest.raises(EndpointRefused):
        resolve_endpoint(cfg(), "https://abc.supabase.co?x=1", None)
