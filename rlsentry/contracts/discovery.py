"""M2 Discovery contracts (SPEC §5 M2; FR-04, FR-05). Owned by the architect.

Implementations live in rlsentry/discovery/<file>.py with exactly these names and signatures;
they import constants from here instead of redefining them. Design decisions: ADR-023.

Pipeline: fetch_openapi → parse_openapi (confirmed) ┐
          infer_from_bundle (inferred) ─────────────┼→ merge_targets → DiscoveryResult
          policy.tables (unknown) ──────────────────┘
Every network call goes through the SafeClient it is given (SPEC §5 Safety); discovery only
ever sends GET.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from rlsentry.contracts.models import DiscoveryResult, Target
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.safety import SafeClientContract

OPENAPI_PATH = "/rest/v1/"
"""PostgREST root: Swagger 2.0 document listing every relation and RPC the caller may see."""

PK_MARKER = "<pk/>"
"""PostgREST marks primary-key columns by putting this tag in the property description
(e.g. "Note:\\nThis is a Primary Key.<pk/>"). Verified on the lab (test_design_assumptions)."""

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""Accepted target names (OpenAPI paths and bundle literals). Anything else is ignored, so a
hostile document or bundle can never inject path segments, query strings or quotes."""

BUNDLE_CALL_RE = re.compile(
    r"""(?:([A-Za-z_$][\w$]*)\s*)?\.\s*(from|rpc)\s*\(\s*(['"`])([A-Za-z_][A-Za-z0-9_]*)\3\s*[,)]""")
"""supabase-js calls in (possibly minified) JS: group 1 = receiver identifier right before the
dot (may be absent, e.g. `)).from(`), group 2 = from|rpc, group 4 = the literal name. Only a
plain string literal counts: `.from(x)` with a variable is not inferable."""

NON_SUPABASE_RECEIVERS: frozenset[str] = frozenset({
    "storage", "Array", "Buffer", "Object", "String", "Uint8Array", "Int8Array", "Uint16Array",
    "Int16Array", "Uint32Array", "Int32Array", "Float32Array", "Float64Array", "Set", "Map",
    "Promise", "Iterator",
})
"""`.from('x')` on these receivers is not a table: `supabase.storage.from('bucket')` names a
Storage bucket (L11), the others are JS built-ins. `.rpc` is never filtered."""


# --- function contracts ----------------------------------------------------------------------

async def fetch_openapi(client: SafeClientContract, supabase_url: str,
                        anon_key: str) -> dict[str, Any] | None:
    """Contract only; implemented by rlsentry.discovery.openapi.fetch_openapi (FR-04).

    One `GET <supabase_url without trailing slash><OPENAPI_PATH>` with headers
    `apikey: <anon_key>` and `Authorization: Bearer <anon_key>`. Returns the parsed JSON body
    iff the status is 200 and the body is a JSON object whose "paths" is an object; otherwise
    (any other status — L12 answers 404 PGRST126 —, invalid JSON, other shape) returns None.
    Never raises for HTTP-level problems; WriteRefused cannot happen (GET). Transport errors
    (httpx.TransportError) also yield None: an unreachable OpenAPI means "fall back to the
    bundle", not "abort the scan".
    """
    raise NotImplementedError


def parse_openapi(doc: Mapping[str, Any]) -> list[Target]:
    """Contract only; implemented by rlsentry.discovery.openapi.parse_openapi (FR-04). Pure.

    For every key of doc["paths"]:
    - "/" is skipped;
    - "/rpc/<name>" → Target(kind="rpc", columns=[], primary_key=[]): PostgREST does not
      describe RPC result columns;
    - "/<name>" → Target(kind="table", columns=list(doc["definitions"][name]["properties"]) in
      document order, primary_key = those properties whose "description" (a string) contains
      PK_MARKER, in document order). Missing definition → columns=[] and primary_key=[].
      ADR-034 (MS4): required = the definition's "required" list (PostgREST lists NOT NULL
      columns without a default) filtered to strings that are among `columns`, in "required"
      order; column_formats = {column: property["format"]} for every property whose "format"
      is a string (e.g. "uuid", "text", "integer", "boolean", "timestamp with time zone").
      A non-list "required" or a non-dict property is ignored for these two fields. RPC
      targets keep required=[] and column_formats={};
      ADR-023 #1: PostgREST's OpenAPI cannot tell a view from a table (same methods, same PK
      marker; verified on L06), so M2 never reports kind="view";
    - every other key, or a <name> not matching IDENT_RE, is ignored.
    All targets: discovered_by="openapi", confidence="confirmed". Result sorted by (name, kind),
    one entry per (name, kind). Malformed parts (non-dict values, missing keys) are skipped,
    never raised: the document comes from the target and may be hostile.
    """
    raise NotImplementedError


def infer_from_bundle(sources: list[str]) -> list[Target]:
    """Contract only; implemented by rlsentry.discovery.bundle.infer_from_bundle (FR-05). Pure.

    Scan every source with BUNDLE_CALL_RE. `.from('<name>')` → kind "table" unless the
    receiver (group 1) is in NON_SUPABASE_RECEIVERS; `.rpc('<name>')` → kind "rpc".
    Every target: columns=[], primary_key=[], discovered_by="bundle", confidence="inferred".
    Deduplicated by (name, kind) across all sources; sorted by (name, kind).
    """
    raise NotImplementedError


def merge_targets(openapi: list[Target] | None, inferred: list[Target],
                  policy: ExpectedPolicy) -> list[Target]:
    """Contract only; implemented by rlsentry.discovery.merge.merge_targets. Pure.

    `openapi` is None when the document was unavailable. Rules (ADR-023 #2):
    1. Every OpenAPI target is kept as is (confirmed).
    2. Every inferred target whose name is not among the OpenAPI targets' names is added
       (bundle / inferred) — also when OpenAPI is available, because with PostgREST's
       follow-privileges mode anon's document hides relations only authenticated can use.
    3. Every name in policy.tables found by neither is added as Target(name, kind="table",
       discovered_by="policy", confidence="unknown") (SPEC §5 M2 step 3).
    4. primary_key: a target whose primary_key is empty takes
       policy.tables[name].primary_key when that is set (ADR-014: RPC results, L12). A
       non-empty OpenAPI primary key is never overridden.
    Result sorted by (name, kind); one entry per (name, kind). Inputs are not mutated.
    """
    raise NotImplementedError


async def discover(client: SafeClientContract, supabase_url: str, anon_key: str,
                   policy: ExpectedPolicy, bundle_sources: list[str]) -> DiscoveryResult:
    """Contract only; implemented by rlsentry.discovery.discover.discover (M2 entry point).

    doc = fetch_openapi(...); targets = merge_targets(parse_openapi(doc) if doc is not None
    else None, infer_from_bundle(bundle_sources), policy);
    returns DiscoveryResult(targets=targets, openapi_available=doc is not None).
    """
    raise NotImplementedError
