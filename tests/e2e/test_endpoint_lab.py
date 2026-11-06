"""MS5 approval note 6 (ADR-043) on the real lab: the L04 frontend bundle names the lab API, but
until the user names it too, not one request reaches the API port."""
from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Profile
from rlsentry.contracts.pipeline import EndpointRefused
from tests.e2e.conftest import lab_config, lab_env
from tests.e2e.helpers import Recording, gt, scan

pytestmark = [pytest.mark.e2e_profiles, pytest.mark.safety]


def test_unconfirmed_bundle_url_gets_zero_api_requests(lab: LabInfo) -> None:
    labctl.apply("L04")
    api_port = urlsplit(lab.api_url).port
    for profile in (Profile.DEV, Profile.AUDIT):
        rec = Recording()
        with labctl.serve_frontend("L04") as url:
            cfg = lab_config(url, lab, gt("L04").policy, profile, supabase_url=None)
            with pytest.raises(EndpointRefused) as exc:
                scan(cfg, lab_env(lab), rec)
        assert rec.seen and api_port not in rec.ports()
        assert lab.api_url in str(exc.value)


def test_cli_flag_confirmation_is_recorded(lab: LabInfo) -> None:
    labctl.apply("C01")
    with labctl.serve_frontend("C01") as url:
        cfg = lab_config(url, lab, gt("C01").policy, Profile.AUDIT, supabase_url=None)
        rep = scan(cfg, lab_env(lab), cli_supabase_url=lab.api_url)
    assert (rep.authorization.supabase_url, rep.authorization.supabase_url_method) == (lab.api_url, "cli_flag")
