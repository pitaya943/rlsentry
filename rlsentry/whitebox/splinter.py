"""Run the vendored, version-pinned supabase/splinter lints read-only (SPEC §5 M4; ADR-032)."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from importlib import resources
from typing import Any

import rlsentry.contracts.whitebox as wc
from rlsentry.contracts.discovery import IDENT_RE
from rlsentry.contracts.whitebox import (
    DEFAULT_DB_SCHEMAS,
    SPLINTER_SQL_RESOURCE,
    STATEMENT_TIMEOUT_MS,
    Lint,
)
from rlsentry.whitebox.db import open_readonly


def load_splinter_sql() -> str:
    """Return the vendored splinter script, refusing any file whose sha256 is not the pin.

    Why: a modified copy must never be passed off as the pinned version.
    """
    pkg, name = SPLINTER_SQL_RESOURCE
    data = resources.files(pkg).joinpath(name).read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != wc.SPLINTER_SHA256:
        raise RuntimeError(f"splinter.sql sha256 mismatch: expected {wc.SPLINTER_SHA256}, got {got}")
    return data.decode("utf-8")


def _categories(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        inner = value.strip().removeprefix("{").removesuffix("}")
        return [p.strip().strip('"') for p in inner.split(",") if p.strip()]
    return [str(v) for v in value]


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def parse_lint(row: dict[str, Any]) -> Lint:
    """Reduce one splinter result row to a Lint (names only, never row data)."""
    meta = _metadata(row.get("metadata"))

    def opt(key: str) -> str | None:
        v = meta.get(key)
        return None if v is None else str(v)

    return Lint(
        name=str(row.get("name") or ""),
        level=str(row.get("level") or ""),
        categories=_categories(row.get("categories")),
        object_schema=opt("schema"),
        object_name=opt("name"),
        object_type=opt("type"),
        detail=str(row.get("detail") or ""),
        cache_key=str(row.get("cache_key") or ""),
    )


def run_splinter(db_url: str, db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[Lint]:
    """Run splinter in one read-only transaction that is always rolled back.

    Why set_config: splinter reads `pgrst.db_schemas`, unset on a direct connection; a bound
    parameter avoids building SQL by string formatting.
    """
    if not db_schemas or not all(IDENT_RE.match(s) for s in db_schemas):
        raise ValueError(f"invalid db_schemas: {list(db_schemas)!r}")
    sql = load_splinter_sql()
    conn = open_readonly(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}")
            cur.execute("SELECT set_config('pgrst.db_schemas', %s, true)", (", ".join(db_schemas),))
            cur.execute(sql)
            cols: list[str] = []
            rows: list[Any] = []
            while True:
                if cur.description is not None:
                    cols = [d.name for d in cur.description]
                    rows = cur.fetchall()
                if not cur.nextset():
                    break
            lints = [parse_lint(dict(zip(cols, r, strict=True))) for r in rows]
    finally:
        conn.rollback()
        conn.close()
    return sorted(lints, key=lambda x: (x.name, x.object_schema or "", x.object_name or "", x.cache_key))
