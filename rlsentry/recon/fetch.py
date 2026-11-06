"""M1 bundle fetch: same-origin GET crawl of HTML, JS, chunks and source maps (FR-01, ADR-036).

Why this module decides what is sent: every request is a header-less GET to the target's own
origin through the SafeClient, so the frontend host never receives credentials and no third
party is ever contacted.
"""
from __future__ import annotations

from collections import deque

import httpx

from rlsentry.contracts.recon import (
    MAX_FILE_BYTES,
    MAX_FILES,
    BundleFetch,
    FetchedFile,
)
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.recon.links import (
    html_script_urls,
    js_chunk_urls,
    report_url,
    same_origin,
    source_map_url,
    webpack_chunk_urls,
)
from rlsentry.recon.sourcemap import decode_data_url, map_sources


async def _get(client: SafeClientContract, url: str, max_bytes: int) -> tuple[str | None, str, dict[str, str]]:
    """GET url; returns (body, reason, headers). body is None when the URL is not usable."""
    try:
        resp = await client.request("GET", url)
    except httpx.TransportError:
        return None, "transport error", {}
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}", {}
    if len(resp.content) > max_bytes:
        return None, "too large", {}
    return resp.text, "", dict(resp.headers)


def _is_html(body: str) -> bool:
    head = body.lstrip().lower()
    return head.startswith(("<!doctype", "<html"))


async def fetch_bundle(client: SafeClientContract, target_url: str, *,
                       max_files: int = MAX_FILES,
                       max_bytes: int = MAX_FILE_BYTES) -> BundleFetch:
    """Crawl the target's own bundle (HTML → scripts → chunks → maps) with GET only.

    Why: FR-01 needs every first-party text that may hold a Supabase URL or key, while NFR-03
    forbids sending credentials or touching other origins. Never raises for HTTP-level problems.
    """
    def skip(url: str, reason: str) -> None:
        skipped.append(f"{report_url(url)} ({reason})")

    skipped: list[str] = []
    body, reason, _ = await _get(client, target_url, max_bytes)
    if body is None:
        skip(target_url, reason)
        return BundleFetch(files=[], skipped=skipped)
    files: list[FetchedFile] = [FetchedFile(url=target_url, kind="html", text=body)]
    fetches = 1
    handled: set[str] = {target_url}
    queue: deque[tuple[str, bool]] = deque((u, False) for u in html_script_urls(body, target_url))

    while True:
        while queue:
            url, is_map = queue.popleft()
            if url in handled:
                continue
            handled.add(url)
            if not same_origin(url, target_url):
                skip(url, "cross-origin")
                continue
            if fetches >= max_files:
                skip(url, "file limit")
                continue
            fetches += 1
            text, reason, headers = await _get(client, url, max_bytes)
            if text is None:
                skip(url, reason)
                continue
            if _is_html(text):
                skip(url, "not a source map" if is_map else "not javascript")
                continue
            if is_map:
                files.append(FetchedFile(url=url, kind="map", text=text))
                files.extend(map_sources(text, url))
                continue
            files.append(FetchedFile(url=url, kind="js", text=text))
            queue.extend((u, False) for u in js_chunk_urls(text, url))
            m = source_map_url(text, url, headers)
            if m is None:
                continue
            if m.startswith("data:"):
                decoded = decode_data_url(m)
                if decoded is not None:
                    inline = url + "#inline-map"
                    files.append(FetchedFile(url=inline, kind="map", text=decoded))
                    files.extend(map_sources(decoded, inline))
            else:
                queue.append((m, True))
        js_files = [(f.url, f.text) for f in files if f.kind == "js"]
        new = [u for u in webpack_chunk_urls(js_files) if u not in handled]
        if not new:
            break
        queue.extend((u, False) for u in new)
    return BundleFetch(files=files, skipped=skipped)
