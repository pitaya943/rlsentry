"""recon/links.py: script URLs, chunk paths, webpack chunk maps, source-map URLs (FR-01; T-184).

Pure functions: nothing here sends a request. Why: the fetcher (fetch.py) decides what to
request, so URL discovery can be tested and audited without any network.
"""
from __future__ import annotations

import contextlib
from collections.abc import Mapping
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from rlsentry.contracts.recon import (
    CHUNK_LOAD_RE,
    CHUNK_PATH_RE,
    LITERAL_RE,
    SOURCE_MAP_COMMENT_RE,
    SOURCE_MAP_HEADERS,
    WEBPACK_CHUNK_URL_RE,
    WEBPACK_MAP_ENTRY_RE,
)
from rlsentry.safety.mask import mask_text

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int] | None:
    try:
        parts = urlsplit(url)
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            return None
        scheme = parts.scheme.lower()
        host = parts.hostname
        if scheme not in _DEFAULT_PORTS or not host:
            return None
        port = parts.port or _DEFAULT_PORTS[scheme]
    except ValueError:
        return None
    return scheme, host.lower(), port


def same_origin(url: str, origin_url: str) -> bool:
    """True iff both are http(s) with equal scheme, host and effective port (ADR-036 #1)."""
    a, b = _origin(url), _origin(origin_url)
    return a is not None and a == b


def report_url(url: str) -> str:
    """The only form in which a URL may be written to the report (NFR-03).

    Why: query strings carry tokens in any format, userinfo is a credential, and JWT/sb_ keys
    can sit in paths or source-map names; so drop query and userinfo, then mask what remains.
    """
    base, hash_sep, fragment = url.partition("#")
    base, query_sep, query = base.partition("?")
    if query_sep and query:
        base += "?\u2026"
    scheme_sep = base.find("://")
    if scheme_sep != -1:
        start = scheme_sep + 3
        slash = base.find("/", start)
        end = len(base) if slash == -1 else slash
        at = base.rfind("@", start, end)
        if at != -1:
            base = base[:start] + base[at + 1:]
    return mask_text(base + hash_sep + fragment)


def public_base(url: str) -> str:
    """Base that bare chunk paths are relative to: the site root, or up to the first /_next/."""
    parts = urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    idx = parts.path.find("/_next/")
    if idx == -1:
        return root + "/"
    return root + parts.path[: idx + len("/_next/")]


class _ScriptParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.urls: list[str] = []

    def _add(self, value: str | None) -> None:
        if value is None or not value.strip():
            return
        absolute, _ = urldefrag(urljoin(self.base_url, value.strip()))
        if absolute.lower().startswith(("http://", "https://")) and absolute not in self.urls:
            self.urls.append(absolute)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v for k, v in attrs}
        if tag == "script":
            self._add(attr.get("src"))
        elif tag == "link":
            rel = (attr.get("rel") or "").lower().split()
            as_attr = (attr.get("as") or "").strip().lower()
            if "modulepreload" in rel or ("preload" in rel and as_attr == "script"):
                self._add(attr.get("href"))


def html_script_urls(html: str, base_url: str) -> list[str]:
    """Script/modulepreload URLs in document order, deduplicated, http(s) only. Never raises."""
    parser = _ScriptParser(base_url)
    # malformed HTML must not abort recon; keep what was found
    with contextlib.suppress(ValueError, AssertionError):
        parser.feed(html)
        parser.close()
    return parser.urls


def js_chunk_urls(js: str, js_url: str) -> list[str]:
    """JS file URLs named by string literals in js (Vite imports, Next.js build manifest)."""
    out: list[str] = []
    for m in LITERAL_RE.finditer(js):
        s = m.group(2)
        url: str | None = None
        if s.startswith(("http://", "https://")):
            try:
                path = urlsplit(s).path
            except ValueError:
                path = ""
            if path.endswith((".js", ".mjs")):
                url = s
        elif CHUNK_PATH_RE.match(s):
            if s.startswith(("./", "../", "/")):
                url = urljoin(js_url, s)
            elif "/" in s:
                url = urljoin(public_base(js_url), s)
        if url is not None and url not in out:
            out.append(url)
    return out


def webpack_chunk_urls(js_files: list[tuple[str, str]]) -> list[str]:
    """Reconstruct lazy chunk URLs from webpack's `.u` function (forms A and B)."""
    ids = sorted({int(i) for _, text in js_files for i in CHUNK_LOAD_RE.findall(text)})
    out: list[str] = []
    for url, text in js_files:
        for m in WEBPACK_CHUNK_URL_RE.finditer(text):
            prefix, body, suffix = m.group(2), m.group(4), m.group(6)
            if body is not None:
                paths = [f"{prefix}{cid}.{h}{suffix}"
                         for cid, h in WEBPACK_MAP_ENTRY_RE.findall(body)]
            else:
                paths = [f"{prefix}{cid}{suffix}" for cid in ids]
            base = url if prefix.startswith("/") else public_base(url)
            for path in paths:
                full = urljoin(base, path)
                if full not in out:
                    out.append(full)
    return out


def source_map_url(js: str, js_url: str, headers: Mapping[str, str]) -> str | None:
    """Source map named by a response header, else the last comment; never guesses `.map`."""
    lowered = {k.lower(): v for k, v in headers.items()}
    value: str | None = None
    for name in SOURCE_MAP_HEADERS:
        if lowered.get(name, "").strip():
            value = lowered[name].strip()
            break
    if value is None:
        matches = SOURCE_MAP_COMMENT_RE.findall(js)
        value = matches[-1] if matches else None
    if value is None:
        return None
    if value.startswith("data:"):
        return value
    return urljoin(js_url, value)
