"""recon/fetch.py: crawl order, same-origin only, limits, maps, GET without credentials (FR-01; T-186)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from rlsentry.contracts.models import Profile
from rlsentry.contracts.recon import BundleFetch
from rlsentry.contracts.safety import USER_AGENT
from rlsentry.recon.fetch import fetch_bundle
from tests.fakes import Recorder, run
from tests.recon.helpers import ORIGIN, StaticSite


def _site(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, "utf-8")
    return tmp_path


def _fetch(site: StaticSite, profile: Profile = Profile.AUDIT, **kw: int) -> BundleFetch:
    return run(lambda c: fetch_bundle(c, ORIGIN + "/", **kw), Recorder(site), profile)


def test_crawl_order_and_scope(tmp_path: Path) -> None:
    root = _site(tmp_path, {
        "index.html": '<script type="module" src="/assets/index.js"></script>'
                      '<script src="https://cdn.example/lib.js"></script>'
                      '<link rel="modulepreload" href="/assets/vendor.js">',
        "assets/index.js": 'import"./vendor.js";const A=()=>import("./Admin.js");'
                           'x="http://other.example:8080/evil.js"\n//# sourceMappingURL=index.js.map',
        "assets/index.js.map": json.dumps({"sources": ["src/main.ts"], "sourcesContent": ["main()"]}),
        "assets/vendor.js": "v()", "assets/Admin.js": "admin()"})
    site = StaticSite(root)
    got = _fetch(site)
    assert [(f.kind, f.url) for f in got.files] == [
        ("html", ORIGIN + "/"), ("js", ORIGIN + "/assets/index.js"), ("js", ORIGIN + "/assets/vendor.js"),
        ("js", ORIGIN + "/assets/Admin.js"), ("map", ORIGIN + "/assets/index.js.map"),
        ("map_source", ORIGIN + "/assets/index.js.map#src/main.ts")]
    assert got.skipped == ["https://cdn.example/lib.js (cross-origin)",
                           "http://other.example:8080/evil.js (cross-origin)"]
    assert all(u.startswith(ORIGIN) for u in site.urls())
    assert len(site.urls()) == len(set(site.urls())) == 5


def test_only_get_without_credentials(tmp_path: Path) -> None:
    root = _site(tmp_path, {"index.html": '<script src="/a.js"></script>', "a.js": "a()"})
    site = StaticSite(root)
    _fetch(site, Profile.DEV)
    assert {r.method for r in site.requests} == {"GET"}
    for r in site.requests:
        assert r.headers["user-agent"] == USER_AGENT
        assert not {"apikey", "authorization", "cookie"} & {k.lower() for k in r.headers}


@pytest.mark.parametrize("status, reason", [(404, "HTTP 404"), (301, "HTTP 301"), (500, "HTTP 500")])
def test_target_not_ok(status: int, reason: str) -> None:
    site = StaticSite(None, extra={ORIGIN + "/": (status, "x", {"location": "https://elsewhere.example/"})})
    got = _fetch(site)
    assert got.files == [] and got.skipped == [f"{ORIGIN}/ ({reason})"]
    assert site.urls() == [ORIGIN + "/"]


def test_transport_error_is_reported_not_raised() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)
    got = run(lambda c: fetch_bundle(c, ORIGIN + "/"), Recorder(boom))
    assert got.files == [] and got.skipped == [f"{ORIGIN}/ (transport error)"]


def test_chunk_failures_and_spa_fallback(tmp_path: Path) -> None:
    root = _site(tmp_path, {"index.html": '\n <!DOCTYPE html><script src="/a.js"></script>'
                                          '<script src="/gone.js"></script><script src="/big.js"></script>',
                            "a.js": "a()\n//# sourceMappingURL=a.js.map", "big.js": "x" * 2000})
    got = _fetch(StaticSite(root, fallback_html=True), max_bytes=1000)
    # SPA hosting answers 200 + index.html for unknown paths: that is not code and not a map.
    assert [f.url for f in got.files] == [ORIGIN + "/", ORIGIN + "/a.js"]
    assert got.skipped == [f"{ORIGIN}/gone.js (not javascript)", f"{ORIGIN}/big.js (too large)",
                           f"{ORIGIN}/a.js.map (not a source map)"]


def test_file_limit(tmp_path: Path) -> None:
    files = {"index.html": "".join(f'<script src="/c{i}.js"></script>' for i in range(5))}
    files.update({f"c{i}.js": f"c{i}()" for i in range(5)})
    site = StaticSite(_site(tmp_path, files))
    got = _fetch(site, max_files=3)
    assert [f.url for f in got.files] == [ORIGIN + "/", ORIGIN + "/c0.js", ORIGIN + "/c1.js"]
    assert got.skipped == [f"{ORIGIN}/c{i}.js (file limit)" for i in (2, 3, 4)]
    assert len(site.requests) == 3


def test_inline_map_and_header_map(tmp_path: Path) -> None:
    inline = base64.b64encode(json.dumps({"sources": ["s.ts"], "sourcesContent": ["s()"]}).encode()).decode()
    root = _site(tmp_path, {"index.html": '<script src="/a.js"></script><script src="/b.js"></script>',
                            "a.js": f"a()\n//# sourceMappingURL=data:application/json;base64,{inline}",
                            "b.js": "b()",
                            "maps/b.map": json.dumps({"sources": ["b.ts"], "sourcesContent": ["b0()"]})})
    site = StaticSite(root)
    site.extra[ORIGIN + "/b.js"] = (200, "b()", {"SourceMap": "/maps/b.map"})
    got = _fetch(site)
    assert [(f.kind, f.url) for f in got.files] == [
        ("html", ORIGIN + "/"), ("js", ORIGIN + "/a.js"), ("map", ORIGIN + "/a.js#inline-map"),
        ("map_source", ORIGIN + "/a.js#inline-map#s.ts"), ("js", ORIGIN + "/b.js"),
        ("map", ORIGIN + "/maps/b.map"), ("map_source", ORIGIN + "/maps/b.map#b.ts")]
    assert ORIGIN + "/b.js.map" not in site.urls()   # no guessing (ADR-036 #2)


def test_webpack_chunks_after_queue_drains(tmp_path: Path) -> None:
    root = _site(tmp_path, {
        "index.html": '<script src="/static/js/runtime.js"></script><script src="/static/js/main.js"></script>',
        "static/js/runtime.js": 'n.u=e=>"static/js/"+e+"."+{7:"aa11"}[e]+".chunk.js"',
        "static/js/main.js": "n.e(7)", "static/js/7.aa11.chunk.js": 'lazy();x="./more.js"',
        "static/js/more.js": "more()"})
    got = _fetch(StaticSite(root))
    assert [f.url for f in got.files] == [
        ORIGIN + "/", ORIGIN + "/static/js/runtime.js", ORIGIN + "/static/js/main.js",
        ORIGIN + "/static/js/7.aa11.chunk.js", ORIGIN + "/static/js/more.js"]
