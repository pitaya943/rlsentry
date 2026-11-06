"""L03 USER_METADATA_ESCALATION through run_scan on the lab (MS3 approval note 1; ADR-042).

dev confirms the escalation for both users and leaves both accounts' user_metadata as found;
audit never touches Auth. C04 (no INSERT policy) stays inconclusive in dev: seeding is refused
(ADR-042 #5)."""
from __future__ import annotations

import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Evidence, Op, Outcome, Profile, Role
from tests.e2e.conftest import lab_config, lab_env
from tests.e2e.helpers import gt, scan

pytestmark = pytest.mark.e2e_profiles


@pytest.fixture(scope="module")
def lab(lab_info: LabInfo) -> LabInfo:
    return lab_info


def admin_accounts() -> list[tuple[str, ...]]:
    """(test accounts, of which carry user_metadata.role = admin)."""
    ids = ",".join(f"'{u['id']}'" for u in LAB_USERS.values())
    return labctl.query(f"SELECT count(*), count(*) FILTER (WHERE raw_user_meta_data->>'role' = 'admin') "
                        f"FROM auth.users WHERE id IN ({ids})")


def test_dev_confirms_escalation_and_restores_metadata(lab: LabInfo) -> None:
    labctl.apply("L03")
    with labctl.serve_frontend("L03") as url:
        rep = scan(lab_config(url, lab, gt("L03").policy, Profile.DEV), lab_env(lab))
    esc = [f for f in rep.findings if f.rule == "USER_METADATA_ESCALATION"]
    assert {(f.role, f.target, f.op, f.evidence) for f in esc} == {
        (Role.USER_A, "reports", Op.SELECT, Evidence.CONFIRMED), (Role.USER_B, "reports", Op.SELECT, Evidence.CONFIRMED)}
    assert admin_accounts() == [("2", "0")]


def test_audit_never_escalates(lab: LabInfo) -> None:
    labctl.apply("L03")
    with labctl.serve_frontend("L03") as url:
        rep = scan(lab_config(url, lab, gt("L03").policy, Profile.AUDIT, with_db=False), lab_env(lab))
    assert not [f for f in rep.findings if f.rule == "USER_METADATA_ESCALATION"]


def test_c04_stays_inconclusive_in_dev(lab: LabInfo) -> None:
    labctl.apply("C04")
    with labctl.serve_frontend("C04") as url:
        rep = scan(lab_config(url, lab, gt("C04").policy, Profile.DEV), lab_env(lab))
    cell = next(c for c in rep.matrix.cells if (c.target, c.role, c.op) == ("subscriptions", Role.USER_A, Op.SELECT))
    assert cell.outcome is Outcome.INCONCLUSIVE
    assert any("seed HTTP 403" in n for n in rep.notes)
