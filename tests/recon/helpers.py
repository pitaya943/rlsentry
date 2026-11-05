"""Shared helpers for M1 recon tests: fake keys, a static-site MockTransport, raw-key checks.

No network: sites are served by httpx.MockTransport through the real SafeClient (tests/fakes.py),
so every recon test also exercises the write gate and the User-Agent rule.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ORIGIN = "http://fixture.test"


def make_jwt(payload: object, header: object | None = None, sig: str = "c2lnbmF0dXJlLW5vdC12ZXJpZmllZA") -> str:
    """JWT-shaped token with `payload` (any JSON value). The signature is junk: never verified."""
    def b64(obj: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{b64(header or {'alg': 'HS256', 'typ': 'JWT'})}.{b64(payload)}.{sig}"


ANON_JWT = make_jwt({"iss": "supabase", "ref": "abcdefghijklmnopqrst", "role": "anon", "exp": 2000000000})
SERVICE_JWT = make_jwt({"iss": "supabase", "ref": "abcdefghijklmnopqrst", "role": "service_role",
                        "exp": 2000000000})
# Built by concatenation so no complete secret-looking literal sits in the repository.
SB_SECRET = "sb_" + "secret_" + "Q7xT2mVb9KpL4zWc8RnJ5yHd_3fGa6s1E"
SB_PUBLISHABLE = "sb_" + "publishable_" + "Zr4Nq8Lm2Xv7Bc5Kt9Wy3Hp_6dJs1Fg0"

# Raw values planted in the real-framework fixtures (see fixtures/README.md).
FIXTURE_SECRETS: dict[str, list[str]] = {}
_KEY_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sb_publishable_[A-Za-z0-9_-]{10,}"
                     r"|AIzaSy[A-Za-z0-9_-]{20,}")
for _fw in ("nextjs", "vite", "cra"):
    _text = "\n".join(f.read_text("utf-8") for f in sorted((FIXTURES / "_sources" / _fw).rglob("*"))
                      if f.is_file())
    FIXTURE_SECRETS[_fw] = sorted(set(_KEY_RE.findall(_text)))


class StaticSite:
    """MockTransport handler serving files of `root` at `origin`; records every request.

    "/" → index.html. Unknown paths → 404, or `fallback_html` with 200 (SPA hosting) when set.
    `extra` maps absolute URLs to (status, body, headers) and wins over files.
    """

    def __init__(self, root: Path | None, origin: str = ORIGIN, *, fallback_html: bool = False,
                 extra: dict[str, tuple[int, str, dict[str, str]]] | None = None) -> None:
        self.root, self.origin, self.fallback_html = root, origin, fallback_html
        self.extra = extra or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url in self.extra:
            status, body, headers = self.extra[url]
            return httpx.Response(status, text=body, headers=headers)
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" != self.origin or self.root is None:
            return httpx.Response(404, text="not found")
        path = parts.path.lstrip("/") or "index.html"
        f = (self.root / path).resolve()
        if f.is_file() and self.root.resolve() in f.parents:
            return httpx.Response(200, content=f.read_bytes())
        if self.fallback_html:
            return httpx.Response(200, content=(self.root / "index.html").read_bytes())
        return httpx.Response(404, text="not found")

    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]


def assert_no_raw(text: str, raws: list[str]) -> None:
    """NFR-03: none of the raw key values may appear in `text` (message never quotes them)."""
    leaked = [i for i, raw in enumerate(raws) if raw and raw in text]
    assert not leaked, f"raw key values #{leaked} appear unmasked in the output"
