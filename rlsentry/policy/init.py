"""`rlsentry init` policy draft (FR-15). Contract: rlsentry/contracts/policy.py draft_policy."""
from __future__ import annotations

import json

from rlsentry.contracts.models import Target
from rlsentry.contracts.policy import OWNER_COLUMN_CANDIDATES, PUBLIC_COLUMN_CANDIDATES


def _first(candidates: tuple[str, ...], columns: list[str]) -> str | None:
    return next((c for c in candidates if c in columns), None)


def _q(s: str) -> str:
    # JSON strings are valid YAML double-quoted scalars; quoting keeps odd names safe.
    return json.dumps(s)


def _entry(t: Target) -> list[str]:
    name = _q(t.name)
    if t.kind == "rpc":
        return [f"  # {t.name}: no owner column was found; denying by default.",
                f"  {name}:", "    select: {anon: deny, user: deny}"]
    cols = list(t.columns)
    owner = _first(OWNER_COLUMN_CANDIDATES, cols)
    public = _first(PUBLIC_COLUMN_CANDIDATES, cols)
    if owner and public:
        user_sel = "public_or_own_rows"
    elif owner:
        user_sel = "own_rows_only"
    elif public:
        user_sel = "public_rows_only"
    else:
        user_sel = "deny"
    user_w = "own_rows_only" if owner else "deny"
    lines: list[str] = []
    if owner is None:
        lines.append(f"  # {t.name}: no owner column was found; denying by default.")
    lines.append(f"  {name}:")
    if t.primary_key:
        lines.append("    primary_key: [" + ", ".join(_q(c) for c in t.primary_key) + "]")
    if owner:
        lines.append(f"    owner_column: {_q(owner)}")
    if public:
        lines.append(f"    public_column: {_q(public)}")
    lines.append(f"    select: {{anon: {'public_rows_only' if public else 'deny'}, user: {user_sel}}}")
    for op in ("insert", "update", "delete"):
        lines.append(f"    {op}: {{anon: deny, user: {user_w}}}")
    return lines


def draft_policy(targets: list[Target]) -> str:
    """Draft the `tables:` section from discovered names only, so a user edits rather than
    writes from scratch; deterministic so reruns diff cleanly."""
    unique: dict[str, Target] = {}
    for t in targets:
        unique.setdefault(t.name, t)
    if not unique:
        return "tables: {}\n"
    out = ["tables:"]
    for name in sorted(unique):
        out.extend(_entry(unique[name]))
    return "\n".join(out) + "\n"
