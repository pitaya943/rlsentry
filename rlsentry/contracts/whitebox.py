"""M4 Whitebox contracts (SPEC §5 M4; FR-11). Owned by the architect. Design: ADR-032.

Implementations live in rlsentry/whitebox/<file>.py with exactly these names and signatures
and import the constants from here.

    open_readonly (db.py) ─┬→ run_splinter (splinter.py) → list[Lint] ┐
                           └→ read_policies (policies.py) → list[PolicyRow]   (report only)
    probe findings + lints → correlate (correlate.py) → findings with `correlation` set
    whitebox (run.py) = run_splinter + correlate  (the Whitebox Protocol in interfaces.py)

What M4 answers (SPEC §5 M4 解讀): splinter is a static linter, M3 is a dynamic probe; they
answer different questions. `probe_only` means the probe proved access that splinter does not
lint; it is NOT a splinter defect. A SECURITY DEFINER function or view is a vulnerability only
when the probe actually obtained protected rows through it; otherwise M4 reports a
Configuration warning. M4 NEVER creates a confirmed finding: it only annotates probe findings
and adds non-vulnerability warnings, so it cannot change recall, precision or FPR by itself.

Safety: M4 only reads. Every connection is opened read-only (open_readonly) and every
transaction is rolled back; M4 never commits. It runs in every profile, including audit.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from rlsentry.contracts.models import Finding, PolicyRow, Role

SPLINTER_VERSION = "2026.09.1"
"""Pinned supabase/splinter release tag (SPEC §5 M4 「固定版本」). Upgrading = new ADR plus
re-measuring every lab scenario's splinter_expected (SPEC §8)."""

SPLINTER_COMMIT = "e74a9e36cb12258cb67d1464bc1cb196e9cd8446"
"""Commit of SPLINTER_VERSION on https://github.com/supabase/splinter."""

SPLINTER_SHA256 = "d8d558baad3e03832e521c527907fa50a9a172fabd899dd0f5c2504a5a0e9349"
"""sha256 of `splinter.sql` at SPLINTER_COMMIT. rlsentry/whitebox/splinter.sql is that file,
byte for byte (vendored; PostgreSQL License, Copyright (c) 2024, Supabase). run_splinter
refuses to run a file with another hash, so a modified copy can never be passed off as the
pinned version."""

SPLINTER_SQL_RESOURCE = ("rlsentry.whitebox", "splinter.sql")
"""(package, resource) for importlib.resources: the vendored file ships with the package."""

DEFAULT_DB_SCHEMAS: tuple[str, ...] = ("public",)
"""Schemas exposed through PostgREST. splinter reads `current_setting('pgrst.db_schemas')`
and, on a direct connection where that GUC is unset, several lints return nothing (SPEC §5 M4
第 1 點), so run_splinter always sets it from this value."""

SECURITY_CATEGORY = "SECURITY"
"""Only lints whose `categories` contain this value take part in correlation (ADR-032);
PERFORMANCE and other categories are outside RLSentry's question (authorization)."""

SECURITY_DEFINER_LINTS: dict[str, str | None] = {
    "anon_security_definer_function_executable": "anon",
    "authenticated_security_definer_function_executable": None,
}
"""splinter lints meaning "a SECURITY DEFINER function is executable by this API role" →
the Finding.role of the SECURITY_DEFINER_EXECUTABLE warning (None = any signed-in user;
RLSentry's roles are the test accounts, not the DB role `authenticated`)."""

DEFINER_LINT_ROLES: dict[str, frozenset[Role]] = {
    "anon_security_definer_function_executable": frozenset({Role.ANON}),
    "authenticated_security_definer_function_executable": frozenset({Role.USER_A, Role.USER_B}),
}
"""ADR-039: which RLSentry roles each SECURITY DEFINER lint speaks for (per-role suppression and
relabelling in correlate)."""

DEFINER_RELABEL_RULES: frozenset[str] = frozenset({"ANON_READ_OWNER_SCOPED", "CROSS_TENANT_READ"})
"""M3 read rules that correlate turns into SECURITY_DEFINER_RPC_DATA when splinter proves the
object is an executable SECURITY DEFINER function (ADR-039)."""


STATEMENT_TIMEOUT_MS = 30_000
"""`SET LOCAL statement_timeout` for every M4 transaction (a lint must not hang a scan)."""


class Lint(BaseModel):
    """One splinter result row, reduced to what correlation and the report need.

    `object_schema`/`object_name`/`object_type` come from splinter's `metadata` JSON keys
    `schema`/`name`/`type` (None when absent). No row data is ever part of a lint; `detail` is
    splinter's text about the object (names only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str                         # e.g. "rls_disabled_in_public"
    level: str                        # ERROR | WARN | INFO
    categories: list[str]
    object_schema: str | None = None
    object_name: str | None = None
    object_type: str | None = None    # table | view | function name in metadata.type, if any
    detail: str = ""
    cache_key: str = ""


# --- whitebox/db.py --------------------------------------------------------------------------

def open_readonly(db_url: str) -> Any:
    """Contract only; implemented by rlsentry.whitebox.db.open_readonly. ⚠ opens a DB connection.

    psycopg.connect(db_url, autocommit=False, connect_timeout=10,
    options="-c default_transaction_read_only=on") and then `conn.read_only = True`, so every
    transaction on it is READ ONLY at two levels (server default and the BEGIN psycopg sends).
    A write attempted on it fails with SQLSTATE 25006. Returns the psycopg.Connection (typed Any
    here so the contracts package does not import psycopg). Callers never commit: they wrap
    their work in try/finally and call conn.rollback() and conn.close() in the finally block
    (not `with conn:`, whose successful exit commits).
    """
    raise NotImplementedError


# --- whitebox/splinter.py ----------------------------------------------------------------------

def load_splinter_sql() -> str:
    """Contract only; implemented by rlsentry.whitebox.splinter.load_splinter_sql.

    Read SPLINTER_SQL_RESOURCE with importlib.resources (bytes), check sha256 == SPLINTER_SHA256
    (else RuntimeError naming both hashes), return it decoded as UTF-8."""
    raise NotImplementedError


def parse_lint(row: dict[str, Any]) -> Lint:
    """Contract only; implemented by rlsentry.whitebox.splinter.parse_lint. Pure.

    `row` is one splinter result row as a dict of its columns (name, title, level, facing,
    categories, description, detail, remediation, metadata, cache_key). `categories` may be a
    list or a Postgres array text "{SECURITY}"; `metadata` may be a dict, JSON text or None.
    Missing keys give the Lint defaults. object_* from metadata schema/name/type."""
    raise NotImplementedError


def run_splinter(db_url: str, db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[Lint]:
    """Contract only; implemented by rlsentry.whitebox.splinter.run_splinter. ⚠ DB, read-only.

    1. sql = load_splinter_sql() (hash-checked).
    2. With open_readonly(db_url) as conn, in ONE transaction:
       `SET LOCAL statement_timeout = <STATEMENT_TIMEOUT_MS>`;
       `SELECT set_config('pgrst.db_schemas', %s, true)` with ", ".join(db_schemas) as a bound
       parameter (the parameterised equivalent of SET LOCAL pgrst.db_schemas = '…'; never build
       it by string formatting);
       then execute `sql` (it is a multi-statement script: run it without parameters and take
       the result set of its last statement, the lint query);
       then conn.rollback().
    3. Return [parse_lint(row) for each row] sorted by (name, object_schema or "",
       object_name or "", cache_key).
    db_schemas must be non-empty and every entry must match IDENT_RE from
    rlsentry.contracts.discovery, else ValueError before connecting.
    psycopg errors propagate (the caller decides; the pipeline reports M4 as failed, never as
    "no lints")."""
    raise NotImplementedError


# --- whitebox/policies.py ----------------------------------------------------------------------

def read_policies(db_url: str, db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[PolicyRow]:
    """Contract only; implemented by rlsentry.whitebox.policies.read_policies. ⚠ DB, read-only.

    SPEC §5 M4 第 2 點: one row per pg_policies entry whose schemaname is in db_schemas, so the
    report can show each table's policy conditions. With open_readonly(db_url), one transaction
    with `SET LOCAL statement_timeout`, a single parameterised query
    `SELECT schemaname, tablename, policyname, permissive, roles::text[], cmd, qual, with_check
     FROM pg_catalog.pg_policies WHERE schemaname = ANY(%s)`, then rollback.
    PolicyRow.permissive = (permissive == 'PERMISSIVE'). Sorted by (schema, table, name).
    Same db_schemas validation as run_splinter. Policies are DDL text, never row data."""
    raise NotImplementedError


# --- whitebox/correlate.py ---------------------------------------------------------------------

def correlate(findings: list[Finding], lints: list[Lint],
              db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[Finding]:
    """Contract only; implemented by rlsentry.whitebox.correlate.correlate. Pure (ADR-032).

    Callers pass M3 (probe) findings only. M1 key findings (contracts.recon.KEY_RULES) are
    appended AFTER correlate by the caller (bench/run.py; MS6 pipeline): their targets are key
    labels, not database objects, so correlate would wrongly mark them probe_only (ADR-036 #7).

    Relevant lints: SECURITY_CATEGORY in categories, object_name is not None, and
    object_schema in db_schemas. A lint's *object* is its object_name (PostgREST exposes
    db_schemas objects by bare name, the same string as Finding.target).
    A finding is *proven* when evidence is CONFIRMED, RULES[rule].vulnerability is True and
    target is not None.

    Output = the input findings, in order, each a copy (model_copy; inputs are not mutated):
      - proven finding whose target is the object of ≥1 relevant lint →
        correlation="confirmed", lint=",".join(sorted distinct lint names on that object);
        additionally (ADR-039, MS4 approval note 5 (b)) when its rule is in
        DEFINER_RELABEL_RULES, its op is SELECT and the object has a relevant lint L with
        name in SECURITY_DEFINER_LINTS that *covers* the finding's role (see below), the copy
        gets rule="SECURITY_DEFINER_RPC_DATA", severity=RULES[that].severity and
        id=finding_id(target, role, op, "SECURITY_DEFINER_RPC_DATA"): only splinter can prove
        a function is SECURITY DEFINER, so only M4 may use that rule;
      - other proven finding → correlation="probe_only", lint=None;
      - every other finding unchanged — in particular findings whose rule is in
        recon.KEY_RULES are never correlated, even if a caller passes them in (ADR-036 #7,
        enforced here too since the MS6 audit, ADR-047);
    followed by the new findings, sorted by (target, rule, role value or ""):
      - per object with relevant lints:
        * each relevant lint L whose name is in SECURITY_DEFINER_LINTS → one
          SECURITY_DEFINER_EXECUTABLE finding (target=object, role=Role(value) or None,
          op=Op.SELECT (calling an RPC is SELECT, ADR-007), lint=L's name) UNLESS a proven
          finding on that object has a role L covers (ADR-039, MS4 approval note 5 (a): proof
          for one role never silences the warning for another role);
        * only when NO proven finding is on the object: if any relevant lint not in
          SECURITY_DEFINER_LINTS remains → ONE LINT_ONLY finding for the object: role=None,
          op=None, lint=",".join(sorted distinct names of those other lints);
        both with correlation="lint_only", evidence and severity from RULES[rule], probes=[],
        id=finding_id(target, role, op, rule). A new finding whose id equals an existing
        finding's id is not added (no duplicates).
      Coverage: DEFINER_LINT_ROLES[L.name] is the set of RLSentry roles that lint speaks for
      (anon lint → {anon}; authenticated lint → {user_a, user_b}).
    So a SECURITY DEFINER object that the probe could not get protected rows from yields only a
    Configuration warning; one it did get rows from keeps its confirmed finding (marked
    "confirmed", rule SECURITY_DEFINER_RPC_DATA) and gets no warning for the roles that were
    proven (SPEC §5 M4 解讀; MS4 focus).
    """
    raise NotImplementedError


# --- whitebox/run.py ---------------------------------------------------------------------------

def whitebox(db_url: str, findings: list[Finding],
             db_schemas: Sequence[str] = DEFAULT_DB_SCHEMAS) -> list[Finding]:
    """Contract only; implemented by rlsentry.whitebox.run.whitebox (interfaces.Whitebox).

    correlate(findings, run_splinter(db_url, db_schemas), db_schemas). Errors from run_splinter
    propagate unchanged."""
    raise NotImplementedError
