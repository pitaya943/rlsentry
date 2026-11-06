"""MS4 approval note 5 (d): read_policies is read-only, proven by the database log (NFR-01,
ADR-019, ADR-032 #2), not by the tool's own claim. The positive control shows the same database
user's write does appear in the log, so an empty result is a real measurement."""
from __future__ import annotations

from urllib.parse import urlsplit

import psycopg
import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from rlsentry.whitebox.policies import read_policies

pytestmark = pytest.mark.safety


def db_user(info: LabInfo) -> str:
    user = urlsplit(info.db_url).username
    assert user
    return user


def test_read_policies_writes_nothing(lab_info: LabInfo) -> None:
    labctl.apply("L04")
    marker = labctl.db_log_marker()
    rows = read_policies(lab_info.db_url, ("public",))
    writes = [w for w in labctl.db_writes_since(marker) if w.role == db_user(lab_info)]
    assert {(r.table, r.name) for r in rows} >= {("notes", "notes_select"), ("notes", "notes_insert")}
    assert writes == [], f"read_policies wrote: {writes}"


def test_positive_control_same_user_write_is_logged(lab_info: LabInfo) -> None:
    marker = labctl.db_log_marker()
    with psycopg.connect(lab_info.db_url, autocommit=True) as conn:
        conn.execute("CREATE TEMPORARY TABLE rlsentry_log_control (x int)")
        conn.execute("INSERT INTO rlsentry_log_control VALUES (1)")
    writes = [w for w in labctl.db_writes_since(marker) if w.role == db_user(lab_info)]
    assert {w.command for w in writes} >= {"INSERT"}, writes
