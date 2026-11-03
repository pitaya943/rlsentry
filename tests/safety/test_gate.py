"""authorize (T-050). NFR-02; contract: rlsentry/contracts/safety.py; ADR-017 #3."""
from datetime import UTC, datetime, timedelta, timezone

import pytest

from rlsentry.contracts.interfaces import AuthorizationRefused
from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ScanConfig
from rlsentry.safety.gate import authorize

T0 = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


def cfg(**kw: object) -> ScanConfig:
    return ScanConfig.model_validate({"target": "http://localhost:54321", **kw})


@pytest.mark.safety
def test_refuses_without_any_confirmation() -> None:
    with pytest.raises(AuthorizationRefused) as e:
        authorize(cfg(), cli_confirmed=False, confirmed_by="kuei", now=T0)
    assert "--i-own-this-target" in str(e.value) and "authorized: true" in str(e.value)


@pytest.mark.safety
@pytest.mark.parametrize("who", ["", "   ", "\t\n"])
def test_refuses_blank_confirmer(who: str) -> None:
    with pytest.raises(AuthorizationRefused):
        authorize(cfg(authorized=True), cli_confirmed=True, confirmed_by=who, now=T0)


def test_config_confirmation_is_recorded() -> None:
    rec = authorize(cfg(authorized=True), cli_confirmed=False, confirmed_by="kuei", now=T0)
    assert (rec.method, rec.confirmed_by, rec.confirmed_at) == ("config", "kuei", T0)


def test_cli_flag_wins_over_config() -> None:
    rec = authorize(cfg(authorized=True), cli_confirmed=True, confirmed_by="kuei", now=T0)
    assert rec.method == "cli_flag"
    assert authorize(cfg(), cli_confirmed=True, confirmed_by="kuei", now=T0).method == "cli_flag"


@pytest.mark.safety
def test_naive_time_rejected() -> None:
    with pytest.raises(ValueError):
        authorize(cfg(authorized=True), cli_confirmed=False, confirmed_by="k",
                  now=T0.replace(tzinfo=None))


def test_default_time_is_aware_utc_now() -> None:
    before = datetime.now(UTC)
    rec = authorize(cfg(authorized=True), cli_confirmed=False, confirmed_by="k")
    assert rec.confirmed_at.tzinfo is not None
    assert before - timedelta(seconds=1) <= rec.confirmed_at <= datetime.now(UTC) + timedelta(seconds=1)


def test_other_timezone_kept() -> None:
    tw = datetime(2026, 11, 3, 16, 0, tzinfo=timezone(timedelta(hours=8)))
    assert authorize(cfg(authorized=True), cli_confirmed=False, confirmed_by="k", now=tw).confirmed_at == tw


@pytest.mark.safety
def test_write_hosts_recorded_only_for_ci() -> None:
    c = cfg(authorized=True, profile="ci", write_hosts=["preview.example.test"])
    assert authorize(c, cli_confirmed=False, confirmed_by="k", now=T0).write_hosts == ["preview.example.test"]
    assert authorize(c, cli_confirmed=False, confirmed_by="k", profile=Profile.AUDIT, now=T0).write_hosts == []
    d = cfg(authorized=True, profile="dev", write_hosts=["preview.example.test"])
    assert authorize(d, cli_confirmed=False, confirmed_by="k", now=T0).write_hosts == []
    assert authorize(d, cli_confirmed=False, confirmed_by="k", profile=Profile.CI,
                     now=T0).write_hosts == ["preview.example.test"]
