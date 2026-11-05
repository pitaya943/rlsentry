"""labctl.apply_synthetic (SPEC §9 Runtime fixture; ADR-033). Needs Docker."""
from __future__ import annotations

import httpx
import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import SYNTHETIC_PK_FMT, SYNTHETIC_TABLE_FMT, LabInfo
from rlsentry.contracts.models import Role
from rlsentry.contracts.policy import RowScope


def login(info: LabInfo, role: Role) -> str:
    r = httpx.post(f"{info.api_url}/auth/v1/token?grant_type=password", headers={"apikey": info.anon_key},
                   json={"email": LAB_USERS[role]["email"], "password": labctl.lab_password(role)}, timeout=10)
    r.raise_for_status()
    return str(r.json()["access_token"])


def visible(info: LabInfo, table: str, token: str) -> set[str]:
    r = httpx.get(f"{info.api_url}/rest/v1/{table}?select=id",
                  headers={"apikey": info.anon_key, "Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return {row["id"] for row in r.json()}


def test_five_owner_scoped_tables(lab_info: LabInfo) -> None:
    policy = labctl.apply_synthetic(5)
    names = [SYNTHETIC_TABLE_FMT.format(i) for i in range(1, 6)]
    assert sorted(policy.tables) == names
    tp = policy.tables[names[0]]
    assert tp.owner_column == "owner_id" and tp.primary_key == ["id"]
    assert tp.select is not None and tp.select.anon is RowScope.DENY and tp.select.user is RowScope.OWN_ROWS_ONLY
    got = labctl.query("select count(*) from pg_tables where schemaname = 'public' and tablename like 'rt\\_%'")
    assert got == [("5",)]
    a, b = login(lab_info, Role.USER_A), login(lab_info, Role.USER_B)
    t3 = SYNTHETIC_TABLE_FMT.format(3)
    pk1, pk2 = SYNTHETIC_PK_FMT.format(table=3, row=1), SYNTHETIC_PK_FMT.format(table=3, row=2)
    assert len(visible(lab_info, t3, a)) == 1 and len(visible(lab_info, t3, b)) == 1
    assert visible(lab_info, t3, a) | visible(lab_info, t3, b) == {pk1, pk2}
    assert visible(lab_info, t3, lab_info.anon_key) == set()


def test_bounds_and_cleanup(lab_info: LabInfo) -> None:
    for bad in (0, 201):
        with pytest.raises(ValueError):
            labctl.apply_synthetic(bad)
    labctl.apply_synthetic(2)
    labctl.apply("C01")
    got = labctl.query("select count(*) from pg_tables where schemaname = 'public' and tablename like 'rt\\_%'")
    assert got == [("0",)]
