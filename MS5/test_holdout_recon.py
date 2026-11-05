"""MS5 holdout: M1 recon with DIFFERENT inputs than the visible tests. No network, no Docker.
Contracts: rlsentry/contracts/recon.py (ADR-036). Focus: service_role is Critical, anon/publishable
never a finding, every output masked (NFR-03)."""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from rlsentry.contracts.models import Evidence, Profile, Severity
from rlsentry.contracts.recon import Candidate
from rlsentry.recon.classify import classify_key, decode_jwt_claims, findings_from_keys, key_finding
from rlsentry.recon.extract import client_pairs, key_candidates, supabase_hosts
from rlsentry.recon.links import js_chunk_urls, public_base, webpack_chunk_urls
from rlsentry.recon.run import recon
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter


def jwt(payload: dict[str, object]) -> str:
    def b(o: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
    return f"{b({'typ': 'JWT', 'alg': 'HS256'})}.{b(payload)}.ZmFrZS1zaWduYXR1cmUtaG9sZG91dA"


SVC = jwt({"role": "service_role", "iss": "supabase-demo"})          # no ref, no exp
ANON = jwt({"role": "anon", "ref": "zyxwvutsrqponmlkjihg", "iat": 1, "exp": 1999999999, "x": "y"})
SBS = "sb_" + "secret_" + "Hj3Kd9Wq2Lm7Xc5Vb8Nz4Rt1Py6Fs0Ga_Q2"
SBP = "sb_" + "publishable_" + "Wn5Bq8Zr2Kt7Lm4Xc9Vd1Hs6Jp3Fy0Ga"


@pytest.mark.parametrize("n", range(4))
def test_decode_any_padding(n: int) -> None:
    tok = jwt({"role": "anon", "ref": "r" * n, "sub": "drop-me"})
    assert decode_jwt_claims(tok) == {"role": "anon", "ref": "r" * n}


def test_service_role_without_ref_is_secret_and_critical() -> None:
    assert classify_key(Candidate(SVC, "jwt"))[:2] == ("secret", "jwt:service_role")
    keys = [key_finding(Candidate(ANON, "jwt"), "x.js"), key_finding(Candidate(SBP, "sb_publishable"), "x.js"),
            key_finding(Candidate(SVC, "jwt"), "y.js"), key_finding(Candidate(SBS, "sb_secret"), "z.js")]
    fs = findings_from_keys(keys)
    assert [(f.target, f.rule, f.severity, f.evidence) for f in fs] == [
        ("jwt:service_role", "SECRET_KEY_IN_BUNDLE", Severity.CRITICAL, Evidence.CONFIRMED),
        ("sb_secret", "SECRET_KEY_IN_BUNDLE", Severity.CRITICAL, Evidence.CONFIRMED)]
    assert all(SVC not in k.model_dump_json() and SBS not in k.model_dump_json() for k in keys)


def test_extract_variants() -> None:
    text = (f"q.createClient( 'https://zyxwvutsrqponmlkjihg.supabase.co/' , '{ANON}' );"
            f'cfg={{"supabaseKey": "Tq8Wn3Lz6Kv1Xb9Rm4Pc7Hd2Jf5Gs0Ya"}};'
            f"other='https://hjklmnbvcxzasdfghjkl.supabase.in';dsn='your-service-role-key-here-12'")
    assert client_pairs(text) == [("https://zyxwvutsrqponmlkjihg.supabase.co", ANON)]
    assert supabase_hosts(text) == ["https://zyxwvutsrqponmlkjihg.supabase.co",
                                    "https://hjklmnbvcxzasdfghjkl.supabase.in"]
    assert [(c.form, c.value) for c in key_candidates(text)] == [
        ("jwt", ANON), ("generic", "Tq8Wn3Lz6Kv1Xb9Rm4Pc7Hd2Jf5Gs0Ya")]


def test_links_other_layouts() -> None:
    assert public_base("https://h:8443/shop/_next/static/x/_buildManifest.js") == "https://h:8443/shop/_next/"
    js = 'const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/Page-q1.js","assets/Page-q1.css"])))'
    assert js_chunk_urls(js, "https://h/assets/main-z.js") == ["https://h/assets/Page-q1.js"]
    rt = 'a.u=function(c){return"chunks/"+c+"."+{9:"f0",31:"e2"}[c]+".js"}'
    assert webpack_chunk_urls([("https://h/js/rt.js", rt)]) == ["https://h/chunks/9.f0.js", "https://h/chunks/31.e2.js"]


def test_recon_synthetic_vite_site() -> None:
    origin = "http://holdout.test"
    site = {
        "/": '<!doctype html><link rel="modulepreload" href="/assets/vendor-a.js">'
             '<script type="module" src="/assets/main-b.js"></script>'
             '<script src="https://analytics.example/t.js"></script>',
        "/assets/main-b.js": (f"var c=k(`http://localhost:8000`,`{ANON}`);"
                              "const P=()=>import(`./Ops-c.js`);"),
        "/assets/vendor-a.js": "v()",
        "/assets/Ops-c.js": f'export const o=k("http://localhost:8000","{SVC}");o.rpc("purge")',
    }
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        body = site.get(req.url.path) if f"{req.url.scheme}://{req.url.netloc.decode()}" == origin else None
        return httpx.Response(200, text=body) if body is not None else httpx.Response(404)

    async def go() -> object:
        async with SafeClient(profile=Profile.AUDIT, limiter=RateLimiter(rps=1e6, concurrency=4),
                              transport=httpx.MockTransport(handler)) as c:
            return await recon(c, origin + "/")
    out = asyncio.run(go())
    assert out.result.supabase_url == "http://localhost:8000"
    assert out.anon_key == ANON
    assert [(k.label, k.kind) for k in out.result.keys] == [("jwt:anon", "publishable"),
                                                            ("jwt:service_role", "secret")]
    assert [(f.target, f.rule, f.severity) for f in out.findings] == [
        ("jwt:service_role", "SECRET_KEY_IN_BUNDLE", Severity.CRITICAL)]
    assert out.result.chunks_skipped == ["https://analytics.example/t.js (cross-origin)"]
    assert origin + "/assets/Ops-c.js" in out.result.chunks_scanned
    assert {r.method for r in seen} == {"GET"} and all("analytics" not in str(r.url) for r in seen)
    dump = out.result.model_dump_json() + "".join(f.model_dump_json() for f in out.findings) + repr(out)
    assert SVC not in dump and ANON not in dump
