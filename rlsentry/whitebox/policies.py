"""M4: read pg_policies read-only so the report can show each table's policy conditions."""
from __future__ import annotations

from collections.abc import Sequence

from rlsentry.contracts.discovery import IDENT_RE
from rlsentry.contracts.models import PolicyRow
from rlsentry.contracts.whitebox import DEFAULT_DB_SCHEMAS, STATEMENT_TIMEOUT_MS
from rlsentry.whitebox.db import open_readonly

_QUERY = (
    "SELECT schemaname, tablename, policyname, permissive, roles::text[], cmd, qual, with_check "
    "FROM pg_catalog.pg_policies WHERE schemaname = ANY(%s)"
)


def read_policies(db_url: str, db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[PolicyRow]:
    """Return pg_policies entries for db_schemas, sorted by (schema, table, name).

    Why read-only and rolled back: M4 must never change the target; policies are DDL text,
    never row data. Validation happens before connecting so bad input costs no connection.
    """
    if not db_schemas or not all(IDENT_RE.match(s) for s in db_schemas):
        raise ValueError("db_schemas must be non-empty identifiers")
    conn = open_readonly(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}")
            cur.execute(_QUERY, (list(db_schemas),))
            fetched = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()
    rows = [
        PolicyRow(
            schema=str(r[0]), table=str(r[1]), name=str(r[2]),
            command=str(r[5]), roles=[str(x) for x in (r[4] or [])],
            permissive=(r[3] == "PERMISSIVE"), using=r[6], with_check=r[7],
        )
        for r in fetched
    ]
    return sorted(rows, key=lambda p: (p.schema_, p.table, p.name))
