"""M2 entry point: OpenAPI + bundle + policy → DiscoveryResult (SPEC §5 M2)."""
from __future__ import annotations

from rlsentry.contracts.models import DiscoveryResult
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.discovery.bundle import infer_from_bundle
from rlsentry.discovery.merge import merge_targets
from rlsentry.discovery.openapi import fetch_openapi, parse_openapi


async def discover(client: SafeClientContract, supabase_url: str, anon_key: str,
                   policy: ExpectedPolicy, bundle_sources: list[str]) -> DiscoveryResult:
    """Run discovery through the given SafeClient (GET only).

    Why: an unavailable OpenAPI document (L12) must degrade to bundle/policy sources rather
    than abort, and `openapi_available` tells later stages how much to trust the target list.
    """
    doc = await fetch_openapi(client, supabase_url, anon_key)
    targets = merge_targets(parse_openapi(doc) if doc is not None else None,
                            infer_from_bundle(bundle_sources), policy)
    return DiscoveryResult(targets=targets, openapi_available=doc is not None)
