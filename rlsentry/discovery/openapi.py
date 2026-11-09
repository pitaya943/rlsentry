"""discovery/openapi.py (FR-04). Contract: rlsentry/contracts/discovery.py; ADR-023 #1."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from rlsentry.contracts.discovery import IDENT_RE, OPENAPI_PATH, PK_MARKER
from rlsentry.contracts.models import Target
from rlsentry.contracts.safety import SafeClientContract

_RPC_PREFIX = "/rpc/"


async def fetch_openapi(client: SafeClientContract, supabase_url: str,
                        anon_key: str) -> dict[str, Any] | None:
    """Fetch PostgREST's OpenAPI document with the anon key.

    Why None instead of raising: an unavailable document (L12 answers 404) means "fall back to
    the bundle", not "abort the scan".
    """
    url = supabase_url.rstrip("/") + OPENAPI_PATH
    headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}"}
    try:
        resp = await client.request("GET", url, headers=headers)
    except httpx.TransportError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = json.loads(resp.content)
    except ValueError:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("paths"), dict):
        return None
    return body


def _columns(definitions: object, name: str) -> tuple[list[str], list[str]]:
    """Columns and primary key of one definition; ([], []) when absent or malformed."""
    if not isinstance(definitions, Mapping):
        return [], []
    definition = definitions.get(name)
    props = definition.get("properties") if isinstance(definition, Mapping) else None
    if not isinstance(props, Mapping):
        return [], []
    cols = [k for k in props if isinstance(k, str)]
    pk: list[str] = []
    for k in cols:
        prop = props[k]
        desc = prop.get("description") if isinstance(prop, Mapping) else None
        if isinstance(desc, str) and PK_MARKER in desc:
            pk.append(k)
    return cols, pk


def _types(definitions: object, name: str, columns: list[str]) -> tuple[list[str], dict[str, str]]:
    """ADR-034: NOT NULL columns (known, in "required" order) and column -> OpenAPI format."""
    definition = definitions.get(name) if isinstance(definitions, Mapping) else None
    if not isinstance(definition, Mapping):
        return [], {}
    known = set(columns)
    req = definition.get("required")
    required = ([c for c in req if isinstance(c, str) and c in known]
                if isinstance(req, list) else [])
    props = definition.get("properties")
    formats: dict[str, str] = {}
    if isinstance(props, Mapping):
        for c in columns:
            prop = props.get(c)
            fmt = prop.get("format") if isinstance(prop, Mapping) else None
            if isinstance(fmt, str):
                formats[c] = fmt
    return required, formats


def parse_openapi(doc: Mapping[str, Any]) -> list[Target]:
    """Turn a (possibly hostile) PostgREST OpenAPI document into confirmed Targets.

    Views are reported as tables because the document cannot distinguish them (ADR-023 #1).
    """
    paths = doc.get("paths") if isinstance(doc, Mapping) else None
    if not isinstance(paths, Mapping):
        return []
    definitions = doc.get("definitions")
    found: dict[tuple[str, str], Target] = {}
    for key in paths:
        if not isinstance(key, str) or key == "/" or not key.startswith("/"):
            continue
        if key.startswith(_RPC_PREFIX):
            name, kind = key[len(_RPC_PREFIX):], "rpc"
        else:
            name, kind = key[1:], "table"
        if not IDENT_RE.match(name):
            continue
        cols, pk = _columns(definitions, name) if kind == "table" else ([], [])
        required, formats = _types(definitions, name, cols) if kind == "table" else ([], {})
        found[(name, kind)] = Target(name=name, kind=kind, columns=cols, primary_key=pk,
                                     required=required, column_formats=formats,
                                     discovered_by="openapi", confidence="confirmed")
    return [found[k] for k in sorted(found)]
