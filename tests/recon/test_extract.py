"""recon/extract.py: URLs, key candidates, entropy filter (FR-02; SPEC §5 M1 steps 3, 5; T-185)."""
from __future__ import annotations

import math

from rlsentry.recon.extract import client_pairs, key_candidates, shannon_entropy, supabase_hosts
from tests.recon.helpers import ANON_JWT, SB_PUBLISHABLE, SB_SECRET, SERVICE_JWT

GOOGLE = "AIzaSyQ7xT2mVb9KpL4zWc8RnJ5yHd3fGa6s1E"


def test_shannon_entropy() -> None:
    assert shannon_entropy("") == 0.0
    assert shannon_entropy("aaaa") == 0.0
    assert math.isclose(shannon_entropy("abcd"), 2.0)
    assert math.isclose(shannon_entropy("aabb"), 1.0)


def test_supabase_hosts() -> None:
    text = ('a="https://abcdefghijklmnopqrst.supabase.co";b=`https://qrstuvwxyzabcdefghij.supabase.in/rest`;'
            'c="https://abcdefghijklmnopqrst.supabase.co";d="*.supabase.co";'
            'e="https://evil.supabase.co.attacker.example";f="http://plain.supabase.co"')
    assert supabase_hosts(text) == ["https://abcdefghijklmnopqrst.supabase.co",
                                    "https://qrstuvwxyzabcdefghij.supabase.in"]


def test_client_pairs_minified_and_custom_domain() -> None:
    # 壓縮後的 createClient 呼叫沒有函式名（Next.js fixture 實測）；Vite 8 用反引號。
    text = (f'let r=(0,t(8033).UU)("https://abcdefghijklmnopqrst.supabase.co","{ANON_JWT}");'
            f"var a=e(`https://api.example.org/`,`{SB_PUBLISHABLE}`);"
            f'x=createClient("http://127.0.0.1:54321", "{SERVICE_JWT}");')
    assert client_pairs(text) == [("https://abcdefghijklmnopqrst.supabase.co", ANON_JWT),
                                  ("https://api.example.org", SB_PUBLISHABLE),
                                  ("http://127.0.0.1:54321", SERVICE_JWT)]


def test_client_pairs_ignore_placeholders() -> None:
    # supabase-js 的文件範例（實測出現在 source map 中）不是 key。
    text = ("createClient('https://xyzcompany.supabase.co', 'your-publishable-key-here-xx')\n"
            'f("https://my-custom-domain.com","public-anon-key-placeholder")')
    assert client_pairs(text) == []


def test_jwt_and_sb_candidates_in_order() -> None:
    text = f'a="{SB_SECRET}";b=`{ANON_JWT}`;c={{k:"{SB_PUBLISHABLE}"}};d="{ANON_JWT}"'
    got = [(c.form, c.value) for c in key_candidates(text)]
    assert got == [("sb_secret", SB_SECRET), ("jwt", ANON_JWT), ("sb_publishable", SB_PUBLISHABLE)]


def test_jwt_found_outside_string_literals() -> None:
    text = f"// token: {SERVICE_JWT}\nfetch(u,{{headers:{{Authorization:'Bearer {ANON_JWT}'}}}})"
    assert [c.value for c in key_candidates(text)] == [SERVICE_JWT, ANON_JWT]


def test_sb_placeholder_filtered_by_entropy() -> None:
    text = 'a="sb_publishable_xxxxxxxxxxxxxxxxxxxx";b="sb_' + 'secret_aaaaaaaaaaaaaaaaaaaaaaaa"'
    assert key_candidates(text) == []


def test_generic_needs_key_context() -> None:
    text = (f'const cfg={{apiKey:"{GOOGLE}"}};let SERVICE_ROLE_KEY=`{GOOGLE[::-1]}`;'
            f'o={{"x-access-token":"Kq9Zt4Lr7Wm2Np5Xv8Bc3Jh6Df1Gs0Ya"}};createClient({{supabaseKey:"Pw2Lk9Xm4Zt7Vb1Nc8Rq5Hd3Jf6Gs0Ya"}});'
            f'h={{integrity:"Zr4Nq8Lm2Xv7Bc5Kt9Wy3Hp6dJs1Fg0Qa"}};key:"Mb7Tn2Wq9Lx4Pz8Rc3Vk6Hy1Jd5Fs0Ga"')
    assert [(c.form, c.value) for c in key_candidates(text)] == [
        ("generic", GOOGLE), ("generic", GOOGLE[::-1]), ("generic", "Kq9Zt4Lr7Wm2Np5Xv8Bc3Jh6Df1Gs0Ya"),
        ("generic", "Pw2Lk9Xm4Zt7Vb1Nc8Rq5Hd3Jf6Gs0Ya")]


def test_generic_rejects_low_entropy_short_urls_and_words() -> None:
    text = ('apiKey:"your-anon-key-goes-here-123";token:"Ab1Cd2Ef3Gh4";secret:"https://x.example/a1b2c3d4e5f6g7"'
            ';AUTH_TOKEN_PREFIX="base64url.bearer.phx.";anonKey:"abcdefghijklmnopqrstuvwxyzabcdef"')
    assert key_candidates(text) == []
