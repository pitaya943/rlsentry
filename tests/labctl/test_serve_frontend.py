"""labctl.serve_frontend: static, local-only, closed afterwards (ADR-036; T-190). No Docker."""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from lab._shared import labctl


def _get(url: str) -> tuple[int, bytes]:
    # urllib without proxies: the server is on 127.0.0.1 and must be reached directly.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def test_serves_the_scenario_frontend_on_loopback() -> None:
    frontend = labctl.scenario_dir("L08") / "frontend"
    with labctl.serve_frontend("L08") as url:
        assert url.startswith("http://127.0.0.1:") and url.endswith("/")
        assert _get(url) == (200, (frontend / "index.html").read_bytes())
        assert _get(url + "assets/app.js") == (200, (frontend / "assets" / "app.js").read_bytes())
        assert _get(url + "missing.js")[0] == 404
        assert _get(url + "../expected.yaml")[0] == 404
        assert _get(url + "%2e%2e/expected.yaml")[0] == 404


def test_server_is_closed_after_the_block() -> None:
    with labctl.serve_frontend("C01") as url:
        assert _get(url)[0] == 200
    with pytest.raises(OSError):
        _get(url)


def test_closed_after_an_error_too() -> None:
    with pytest.raises(RuntimeError), labctl.serve_frontend("C02") as url:
        raise RuntimeError("boom")
    with pytest.raises(OSError):
        _get(url)


def test_unknown_scenario() -> None:
    with pytest.raises(ValueError), labctl.serve_frontend("L99"):
        pass
