"""read_policies against the real lab (SPEC §5 M4 第 2 點; ADR-032). Needs Docker."""
from __future__ import annotations

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from rlsentry.whitebox.policies import read_policies


def test_l05_policies_with_conditions(lab_info: LabInfo) -> None:
    labctl.apply("L05")
    rows = read_policies(lab_info.db_url)
    by_name = {r.name: r for r in rows if r.table == "projects"}
    assert set(by_name) == {"projects_select", "projects_insert", "projects_update", "projects_delete"}
    upd = by_name["projects_update"]
    assert (upd.schema_, upd.command, upd.roles, upd.permissive) == ("public", "UPDATE", ["authenticated"], True)
    assert upd.using is not None and "auth.uid()" in upd.using
    assert upd.with_check == "true"                          # the planted flaw is visible
    assert by_name["projects_insert"].using is None
    assert rows == sorted(rows, key=lambda r: (r.schema_, r.table, r.name))


def test_only_requested_schemas(lab_info: LabInfo) -> None:
    labctl.apply("L04")
    assert {r.schema_ for r in read_policies(lab_info.db_url)} == {"public"}
    assert all(r.table != "objects" for r in read_policies(lab_info.db_url))   # storage excluded
    assert read_policies(lab_info.db_url, ("graphql_public",)) == []
