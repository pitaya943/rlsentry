"""run_scan safety invariants (NFR-01, NFR-02, ADR-020 #6, MS5 approval note 6 / ADR-043).

- no authorization → no SafeClient and not one request;
- a bundle pointing at an unconfirmed Supabase host → not one request to that host (S4);
- audit → only GET/HEAD and the login POST reach the API;
- a write the gate refuses (dev against a remote host) → inconclusive cells, scan completes;
- exactly one SafeClient per run.
"""
from __future__ import annotations

from typing import Any

import pytest

import rlsentry.pipeline as pl
from rlsentry.contracts.interfaces import AuthorizationRefused
from rlsentry.contracts.models import Outcome, Profile
from rlsentry.contracts.pipeline import EndpointRefused
from rlsentry.contracts.probe import WRITE_REFUSED_REASON
from rlsentry.contracts.safety import USER_AGENT
from tests.pipeline.fake_supabase import API, APP, REMOTE, FakeSupabase, notes_table
from tests.pipeline.helpers import cfg, scan

pytestmark = pytest.mark.safety


def test_unauthorized_sends_nothing_and_builds_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []
    real = pl.SafeClient

    def counting(*a: Any, **k: Any) -> Any:
        built.append(k)
        return real(*a, **k)
    monkeypatch.setattr(pl, "SafeClient", counting)
    fake = FakeSupabase(tables={"notes": notes_table()})
    with pytest.raises(AuthorizationRefused):
        scan(fake, cfg(authorized=False))
    assert fake.requests == [] and built == []


def test_exactly_one_safeclient_per_run(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []
    real = pl.SafeClient

    def counting(*a: Any, **k: Any) -> Any:
        built.append(k)
        return real(*a, **k)
    monkeypatch.setattr(pl, "SafeClient", counting)
    scan(FakeSupabase(tables={"notes": notes_table()}), cfg(profile=Profile.DEV))
    assert len(built) == 1 and built[0]["profile"] is Profile.DEV


def test_bundle_pointing_at_an_unconfirmed_host_gets_zero_requests() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, bundle_url="http://evil.test")
    with pytest.raises(EndpointRefused) as exc:
        scan(fake, cfg(supabase_url=None))
    assert fake.hosts() == {"app.test"}                       # only the authorised target
    assert "http://evil.test" in str(exc.value) and "--supabase-url" in str(exc.value)


def test_even_the_real_api_url_is_not_used_until_the_user_names_it() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})     # bundle points at API itself
    with pytest.raises(EndpointRefused):
        scan(fake, cfg(supabase_url=None))
    assert fake.to(API) == []


def test_cli_flag_confirms_the_url_and_is_recorded() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    rep = scan(fake, cfg(supabase_url=None), cli_supabase_url=API + "/")
    assert (rep.authorization.supabase_url, rep.authorization.supabase_url_method) == (API, "cli_flag")
    assert fake.to(API)


def test_config_and_cli_url_disagree_is_refused_before_any_api_request() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    with pytest.raises(EndpointRefused):
        scan(fake, cfg(), cli_supabase_url="http://other.test")
    assert fake.to(API) == [] and "other.test" not in fake.hosts()


def test_audit_sends_only_reads_and_the_login_post() -> None:
    fake = FakeSupabase(tables={"notes": notes_table(rls="all")})
    scan(fake, cfg(profile=Profile.AUDIT))
    for r in fake.requests:
        assert r.headers["user-agent"] == USER_AGENT
        if r.method not in ("GET", "HEAD"):
            assert (r.method, r.url.path, r.url.query) == ("POST", "/auth/v1/token", b"grant_type=password")


def test_dev_against_a_remote_host_makes_write_cells_inconclusive() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, api=REMOTE, bundle_url=REMOTE)
    rep = scan(fake, cfg(profile=Profile.DEV, supabase_url=REMOTE))
    writes = [c for c in rep.matrix.cells if c.target == "notes" and c.op.value != "select"]
    assert len(writes) == 9
    assert all(c.outcome is Outcome.INCONCLUSIVE and c.reason.startswith(WRITE_REFUSED_REASON)
               and c.known_rows_checked == 0 for c in writes)
    assert fake.methods(REMOTE) <= {"GET", "HEAD", "POST"}
    assert all(r.url.path == "/auth/v1/token" for r in fake.to(REMOTE) if r.method == "POST")
    assert any("refused" in n for n in rep.notes)
    sel = [c for c in rep.matrix.cells if c.target == "notes" and c.op.value == "select"]
    assert {c.outcome for c in sel} == {Outcome.DENIED}          # reads still judged


def test_ci_writes_to_a_remote_host_only_when_listed() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, api=REMOTE)
    scan(fake, cfg(profile=Profile.CI, supabase_url=REMOTE, anon_key_env="SB_ANON",
                   write_hosts=["api.test"]))
    assert "PATCH" in fake.methods(REMOTE) and "DELETE" in fake.methods(REMOTE)
    assert APP.removeprefix("http://") not in fake.hosts()
