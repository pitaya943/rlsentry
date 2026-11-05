"""M4 entry point (interfaces.Whitebox): run splinter read-only, then correlate."""
from __future__ import annotations

from collections.abc import Sequence

from rlsentry.contracts.models import Finding
from rlsentry.contracts.whitebox import DEFAULT_DB_SCHEMAS
from rlsentry.whitebox.correlate import correlate
from rlsentry.whitebox.splinter import run_splinter


def whitebox(db_url: str, findings: list[Finding],
             db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[Finding]:
    """Correlate probe findings with splinter lints; run_splinter errors propagate unchanged."""
    return correlate(findings, run_splinter(db_url, db_schemas), db_schemas)
