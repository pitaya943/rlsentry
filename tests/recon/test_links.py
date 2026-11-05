"""recon/links.py: script URLs, chunk paths, webpack chunk maps, source-map URLs (FR-01; T-186)."""
from __future__ import annotations

from rlsentry.recon.links import (
    html_script_urls,
    js_chunk_urls,
    public_base,
    same_origin,
    source_map_url,
    webpack_chunk_urls,
)


def test_same_origin() -> None:
    assert same_origin("http://h:80/a.js", "http://H/")
    assert same_origin("https://h/a.js", "https://h:443/x")
    assert not same_origin("http://h:8080/a.js", "http://h/")
    assert not same_origin("https://h/a.js", "http://h/")
    assert not same_origin("https://cdn.example/a.js", "https://h/")
    assert not same_origin("data:text/javascript,1", "https://h/")


def test_public_base() -> None:
    assert public_base("http://h:3000/_next/static/b1/_buildManifest.js") == "http://h:3000/_next/"
    assert public_base("http://h/app/_next/static/chunks/x.js") == "http://h/app/_next/"
    assert public_base("https://h/assets/index-B8.js") == "https://h/"


def test_html_script_urls() -> None:
    html = """<html><head><base href="/ignored/">
    <script defer nomodule src="/_next/static/chunks/polyfills.js"></script>
    <SCRIPT type="module" crossorigin SRC="assets/index.js#frag"></SCRIPT>
    <link rel="modulepreload" href="/assets/vendor.js"><link rel="stylesheet" href="/a.css">
    <link rel="preload" as="script" href="https://cdn.example/lib.js">
    <link rel="preload" as="style" href="/b.css"><link rel="Preload ModulePreload" href="/assets/x.js">
    <script>inline()</script><script src="data:text/javascript,1"></script>
    <script src="/assets/vendor.js"></script><script src="javascript:void(0)"></script>
    </head><body><div <unclosed"""
    assert html_script_urls(html, "http://h/app/") == [
        "http://h/_next/static/chunks/polyfills.js", "http://h/app/assets/index.js",
        "http://h/assets/vendor.js", "https://cdn.example/lib.js", "http://h/assets/x.js"]


def test_js_chunk_urls_forms() -> None:
    js = ('import{n as e}from"./index-B8.js";const a=()=>import(`./Admin-DJ.js`);'
          'm=["assets/Lazy-1.js","assets/Lazy-1.js"];n="/abs/root.mjs";'
          'o="https://cdn.example/x.js";p="../up/one.js";q="react-dom.production.min.js";'
          'r="static/css/a.css";s="./not js.js";t="https://h/a.json"')
    assert js_chunk_urls(js, "http://h/assets/index-B8.js") == [
        "http://h/assets/index-B8.js", "http://h/assets/Admin-DJ.js", "http://h/assets/Lazy-1.js",
        "http://h/abs/root.mjs", "https://cdn.example/x.js", "http://h/up/one.js"]


def test_js_chunk_urls_next_build_manifest() -> None:
    js = ('self.__BUILD_MANIFEST=function(e,s,r,t,a){return{"/":[t,a,"static/chunks/pages/index-29.js"],'
          '"/admin":[t,a,"static/chunks/pages/admin-5f.js"]}}(0,1e-4,null,"static/chunks/dc55.js",'
          '"static/chunks/989-54.js")')
    url = "http://h/_next/static/Z5Q/_buildManifest.js"
    assert js_chunk_urls(js, url) == [
        "http://h/_next/static/chunks/pages/index-29.js", "http://h/_next/static/chunks/pages/admin-5f.js",
        "http://h/_next/static/chunks/dc55.js", "http://h/_next/static/chunks/989-54.js"]


def test_webpack_chunk_map_cra() -> None:
    runtime = ('n.u=e=>"static/js/"+e+"."+{203:"e04c0c4b",453:"cfd0efe7","ab-c":"11"}[e]+".chunk.js",'
               'n.miniCssF=e=>{}')
    assert webpack_chunk_urls([("http://h/static/js/main.9a.js", runtime)]) == [
        "http://h/static/js/203.e04c0c4b.chunk.js", "http://h/static/js/453.cfd0efe7.chunk.js",
        "http://h/static/js/ab-c.11.chunk.js"]


def test_webpack_single_hash_uses_chunk_loads() -> None:
    runtime = 'r.u=e=>"static/chunks/"+e+".de20ce76fac57100.js",r.miniCssF=e=>{}'
    page = "i=u()(()=>l.e(43).then(l.bind(l,2043)));j=l.e( 7 );k=l.e(43)"
    files = [("http://h/_next/static/chunks/webpack-a0.js", runtime),
             ("http://h/_next/static/chunks/pages/index-22.js", page)]
    assert webpack_chunk_urls(files) == ["http://h/_next/static/chunks/7.de20ce76fac57100.js",
                                         "http://h/_next/static/chunks/43.de20ce76fac57100.js"]


def test_webpack_function_form_and_no_runtime() -> None:
    runtime = 'o.u=function(e){return"static/js/"+e+"."+{12:"abcd"}[e]+".chunk.js"}'
    assert webpack_chunk_urls([("http://h/static/js/runtime.js", runtime)]) == [
        "http://h/static/js/12.abcd.chunk.js"]
    assert webpack_chunk_urls([("http://h/a.js", "l.e(5);no runtime here")]) == []


def test_source_map_url() -> None:
    js = "x()\n//# sourceMappingURL=old.map\ny()\n//# sourceMappingURL=index-B8.js.map\n"
    assert source_map_url(js, "http://h/assets/index-B8.js", {}) == "http://h/assets/index-B8.js.map"
    assert source_map_url(js, "http://h/a/i.js", {"SourceMap": "/maps/i.map"}) == "http://h/maps/i.map"
    assert source_map_url("y()", "http://h/a/i.js", {"X-SourceMap": "i.map"}) == "http://h/a/i.map"
    assert source_map_url("//@ sourceMappingURL=data:application/json;base64,e30=", "http://h/i.js",
                          {}) == "data:application/json;base64,e30="
    assert source_map_url("no map here", "http://h/i.js", {}) is None
