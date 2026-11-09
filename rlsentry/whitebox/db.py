"""Read-only database connection for M4 (SPEC §5 M4; FR-11)."""
from __future__ import annotations

from typing import Any

import psycopg


def open_readonly(db_url: str) -> Any:
    """Open a connection on which every transaction is READ ONLY.

    Why two levels: the server default (`default_transaction_read_only=on`) and the BEGIN that
    psycopg sends (`conn.read_only = True`), so a write fails with SQLSTATE 25006 even if one
    level is overridden. Callers never commit; they rollback and close in a finally block.
    """
    conn = psycopg.connect(db_url, autocommit=False, connect_timeout=10,
                           options="-c default_transaction_read_only=on")
    conn.read_only = True
    return conn
