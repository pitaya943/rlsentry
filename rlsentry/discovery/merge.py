"""Merge OpenAPI, bundle-inferred and policy-declared targets (SPEC §5 M2 step 3; ADR-023 #2)."""
from __future__ import annotations

from rlsentry.contracts.models import Target
from rlsentry.contracts.policy import ExpectedPolicy


def merge_targets(openapi: list[Target] | None, inferred: list[Target],
                  policy: ExpectedPolicy) -> list[Target]:
    """Combine the three discovery sources into one sorted, de-duplicated target list.

    Why: anon's OpenAPI hides relations only authenticated can use, so bundle and policy names
    must be added even when the document is available. Inputs are copied, never mutated.
    """
    merged: dict[tuple[str, str], Target] = {}
    openapi_names: set[str] = set()
    for t in openapi or []:
        merged.setdefault((t.name, t.kind), t.model_copy(deep=True))
        openapi_names.add(t.name)
    for t in inferred:
        if t.name not in openapi_names:
            merged.setdefault((t.name, t.kind), t.model_copy(deep=True))
    known = {name for name, _ in merged}
    for name in policy.tables:
        if name not in known:
            merged[(name, "table")] = Target(name=name, kind="table", discovered_by="policy",
                                             confidence="unknown")
    for (name, _), t in merged.items():
        if not t.primary_key:
            pk = policy.tables[name].primary_key if name in policy.tables else None
            if pk:
                t.primary_key = list(pk)
    return [merged[k] for k in sorted(merged)]
