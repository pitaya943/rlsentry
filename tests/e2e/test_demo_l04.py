"""SPEC §9 展示情境 (ADR-035; MS4 approval note 3): splinter reports nothing on L04, RLSentry
confirms that user B reads user A's note through the normal API, the report carries a masked
curl reproduction and fix SQL, and after applying that SQL a rescan finds no vulnerability."""
from __future__ import annotations

import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile, Role
from tests.e2e.conftest import lab_config, lab_env
from tests.e2e.helpers import gt, proven, scan

pytestmark = pytest.mark.e2e_profiles


def test_l04_demo_report_fix_and_clean_rescan(lab: LabInfo) -> None:
    labctl.apply("L04")
    try:
        with labctl.serve_frontend("L04") as url:
            cfg = lab_config(url, lab, gt("L04").policy, Profile.DEV)
            rep = scan(cfg, lab_env(lab))
            found = [f for f in proven(rep) if f.rule == "CROSS_TENANT_READ" and f.target == "notes"]
            assert {f.role for f in found} == {Role.USER_A, Role.USER_B}
            assert all(f.correlation == "probe_only" for f in found)         # splinter has no lint here
            for f in found:
                assert f.repro and f.repro.startswith("curl ") and "****" in f.repro
                assert lab.anon_key not in f.repro
                assert f.fix_sql and 'DROP POLICY "notes_select" ON "public"."notes";' in f.fix_sql
                assert 'USING (auth.uid() = "owner_id")' in f.fix_sql
            for sql in sorted({f.fix_sql for f in found if f.fix_sql}):
                labctl.execute(sql)                        # what the user would paste, verbatim
            again = scan(cfg, lab_env(lab))
        assert proven(again) == []
        assert labctl.query("SELECT count(*) FROM pg_policies WHERE tablename = 'notes' AND cmd = 'SELECT'") == [("1",)]
    finally:
        labctl.apply("L04")
