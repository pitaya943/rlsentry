"""run_splinter against the real lab (SPEC §5 M4 第 1 點; ADR-032). Needs Docker.

Proves: the pinned splinter really runs over a read-only connection, `pgrst.db_schemas` is set
(a direct connection without it lints nothing exposed), and the connection cannot write."""
from __future__ import annotations

import psycopg
import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.whitebox import Lint
from rlsentry.whitebox.db import open_readonly
from rlsentry.whitebox.splinter import run_splinter


def security(lints: list[Lint]) -> set[tuple[str, str | None]]:
    return {(x.name, x.object_name) for x in lints if "SECURITY" in x.categories}


def test_l01_rls_disabled_is_reported(lab_info: LabInfo) -> None:
    labctl.apply("L01")
    lints = run_splinter(lab_info.db_url)
    assert ("rls_disabled_in_public", "customers") in security(lints)
    # SECURITY lints only (MS5 approval note 7, ADR-045): after a crash recovery Postgres resets
    # index statistics, so PERFORMANCE lints such as unused_index appear in non-public schemas.
    assert all(x.object_schema in (None, "public") for x in lints if x.object_name and "SECURITY" in x.categories)
    assert lints == sorted(lints, key=lambda x: (x.name, x.object_schema or "", x.object_name or "", x.cache_key))


def test_l07_both_definer_functions_are_linted(lab_info: LabInfo) -> None:
    labctl.apply("L07")
    sec = security(run_splinter(lab_info.db_url))
    for fn in ("get_all_accounts", "ping_definer"):
        assert ("anon_security_definer_function_executable", fn) in sec
        assert ("authenticated_security_definer_function_executable", fn) in sec


def test_db_schemas_is_applied(lab_info: LabInfo) -> None:
    # With an exposed-schema list that does not contain public, the public-schema lints vanish:
    # the setting run_splinter makes is what splinter reads (SPEC: 否則可能回傳空結果).
    labctl.apply("L01")
    other = run_splinter(lab_info.db_url, ("graphql_public",))
    assert ("rls_disabled_in_public", "customers") not in security(other)


def test_connection_is_read_only(lab_info: LabInfo) -> None:
    labctl.apply("C01")
    conn = open_readonly(lab_info.db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("show default_transaction_read_only")
            row = cur.fetchone()
            assert row is not None and row[0] == "on"
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                cur.execute("create table public.rlsentry_should_not_exist (x int)")
    finally:
        conn.rollback()
        conn.close()
    assert labctl.query("select to_regclass('public.rlsentry_should_not_exist') is null") == [("t",)]


def test_run_splinter_leaves_no_writes_in_db_log(lab_info: LabInfo) -> None:
    labctl.apply("L07")
    marker = labctl.db_log_marker()
    run_splinter(lab_info.db_url)
    assert [w for w in labctl.db_writes_since(marker) if w.role == "postgres"] == []
