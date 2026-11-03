"""discovery/bundle.py (FR-05). Contract: rlsentry/contracts/discovery.py; ADR-023 #2."""
from __future__ import annotations

from rlsentry.contracts.discovery import BUNDLE_CALL_RE, NON_SUPABASE_RECEIVERS
from rlsentry.contracts.models import Target


def infer_from_bundle(sources: list[str]) -> list[Target]:
    """Infer targets from supabase-js calls in JS sources.

    Why: when OpenAPI is hidden (L12) the client bundle is the only hint of which relations
    exist. Results are only "inferred"; columns and keys stay empty. Pure.
    """
    found: set[tuple[str, str]] = set()
    for src in sources:
        for m in BUNDLE_CALL_RE.finditer(src):
            receiver, method, name = m.group(1), m.group(2), m.group(4)
            if method == "rpc":
                found.add((name, "rpc"))
            elif receiver not in NON_SUPABASE_RECEIVERS:
                found.add((name, "table"))
    return [
        Target(name=n, kind=k, discovered_by="bundle", confidence="inferred")
        for n, k in sorted(found)
    ]
