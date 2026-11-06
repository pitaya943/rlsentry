"""recon/sourcemap.py: data URLs and sourcesContent extraction (FR-01; ADR-036). Pure."""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any
from urllib.parse import unquote

from rlsentry.contracts.recon import FetchedFile


def decode_data_url(url: str) -> str | None:
    """Decode an inline source-map data URL so its text can be scanned; None when not decodable."""
    try:
        if not url.startswith("data:"):
            return None
        head, sep, payload = url[5:].partition(",")
        if not sep:
            return None
        if head.split(";")[-1].strip().lower() == "base64":
            raw = base64.b64decode(payload, validate=True)
            return raw.decode("utf-8", errors="replace")
        return unquote(payload)
    except (binascii.Error, ValueError):
        return None


def _one_map(obj: dict[str, Any], map_url: str) -> list[FetchedFile]:
    sources = obj.get("sources")
    contents = obj.get("sourcesContent")
    if not isinstance(contents, list):
        return []
    out: list[FetchedFile] = []
    for i, text in enumerate(contents):
        if not isinstance(text, str):
            continue
        name = sources[i] if isinstance(sources, list) and i < len(sources) else None
        label = name if isinstance(name, str) and name else str(i)
        out.append(FetchedFile(url=f"{map_url}#{label}", kind="map_source", text=text))
    return out


def map_sources(map_text: str, map_url: str) -> list[FetchedFile]:
    """Extract original sources embedded in a source map (they may hold keys the bundle lacks)."""
    try:
        obj = json.loads(map_text)
        if not isinstance(obj, dict):
            return []
        sections = obj.get("sections")
        if isinstance(sections, list):
            out: list[FetchedFile] = []
            for sec in sections:
                inner = sec.get("map") if isinstance(sec, dict) else None
                if isinstance(inner, dict):
                    out.extend(_one_map(inner, map_url))
            return out
        return _one_map(obj, map_url)
    except (ValueError, RecursionError):
        return []
