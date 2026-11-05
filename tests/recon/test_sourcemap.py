"""recon/sourcemap.py: data URLs and sourcesContent extraction (FR-01; T-187)."""
from __future__ import annotations

import base64
import json

from rlsentry.recon.sourcemap import decode_data_url, map_sources
from tests.recon.helpers import FIXTURES


def test_decode_data_url() -> None:
    body = json.dumps({"version": 3, "sources": ["a.ts"]})
    b64 = base64.b64encode(body.encode()).decode()
    assert decode_data_url(f"data:application/json;base64,{b64}") == body
    assert decode_data_url(f"data:application/json;charset=utf-8;base64,{b64}") == body
    assert decode_data_url("data:application/json,%7B%22a%22%3A1%7D") == '{"a":1}'
    assert decode_data_url("data:application/json;base64,!!!not-base64") is None
    assert decode_data_url("http://h/a.map") is None


def test_map_sources_names_and_gaps() -> None:
    m = {"version": 3, "sources": ["src/admin.ts", "", None, "src/c.ts"],
         "sourcesContent": ["const k = 1;", "b()", "c()", None]}
    got = map_sources(json.dumps(m), "http://h/assets/a.js.map")
    assert [(f.url, f.kind, f.text) for f in got] == [
        ("http://h/assets/a.js.map#src/admin.ts", "map_source", "const k = 1;"),
        ("http://h/assets/a.js.map#1", "map_source", "b()"),
        ("http://h/assets/a.js.map#2", "map_source", "c()")]


def test_map_sources_index_map_and_garbage() -> None:
    idx = {"version": 3, "sections": [
        {"offset": {"line": 0, "column": 0}, "map": {"sources": ["x.js"], "sourcesContent": ["x()"]}},
        {"offset": {"line": 9, "column": 0}, "url": "remote.map"},
        {"offset": {"line": 20, "column": 0}, "map": {"sources": ["y.js"], "sourcesContent": ["y()"]}}]}
    assert [f.url for f in map_sources(json.dumps(idx), "http://h/i.map")] == [
        "http://h/i.map#x.js", "http://h/i.map#y.js"]
    for garbage in ("not json", "[1,2]", '{"sources": "x", "sourcesContent": 5}', ""):
        assert map_sources(garbage, "http://h/i.map") == []


def test_map_sources_real_vite_map() -> None:
    # 真實的 Vite 8 map：原始碼 src/Admin.tsx 在其中，但金鑰只在建置後的 chunk（以 env 注入）。
    text = (FIXTURES / "vite" / "assets" / "Admin-DJaTEGsj.js.map").read_text("utf-8")
    got = map_sources(text, "http://fixture.test/assets/Admin-DJaTEGsj.js.map")
    assert [f.url.rsplit("#", 1)[1] for f in got] == ["../../src/Admin.tsx"]
    assert "VITE_SUPABASE_SERVICE_ROLE_KEY" in got[0].text and "eyJ" not in got[0].text
