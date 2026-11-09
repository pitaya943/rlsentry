"""pipeline.run_scan (SPEC §4, §2 profiles, FR-16; ADR-042). Contract: rlsentry/contracts/pipeline.py.

Behaviour on a fake Supabase (tests/pipeline/fake_supabase.py) through the real SafeClient.
Safety properties (authorization, S4, write gate, single client) are in test_run_scan_safety.py.
"""
from __future__ import annotations

from typing import Any

import pytest

from rlsentry.contracts.models import Evidence, Outcome, PolicyRow, Profile, Role
from rlsentry.contracts.pipeline import M4_SKIPPED_NOTE, WRITES_AUDIT_NOTE, ScanSetupError
from rlsentry.contracts.whitebox import Lint
from tests.pipeline.fake_supabase import (
    ANON_KEY,
    API,
    APP,
    ENV,
    SERVICE_KEY,
    A,
    FakeSupabase,
    Table,
    notes_table,
)
from tests.pipeline.helpers import cfg, rules, scan


def test_audit_finds_cross_tenant_read_and_reports_everything() -> None:
    fake = FakeSupabase(tables={"notes": notes_table(rls="all")})
    rep = scan(fake, cfg())
    assert rep.profile is Profile.AUDIT and rep.target == APP
    assert rep.modules == ["M1", "M2", "M3", "M5"]
    assert WRITES_AUDIT_NOTE in rep.notes and M4_SKIPPED_NOTE in rep.notes
    assert set(rep.timings) == {"M1", "M2", "M3"}
    assert ("notes", "user_a", "CROSS_TENANT_READ") in rules(rep)
    assert ("notes", "user_b", "CROSS_TENANT_READ") in rules(rep)
    auth = rep.authorization
    assert (auth.supabase_url, auth.supabase_url_method, auth.method) == (API, "config", "config")
    assert auth.confirmed_by == "tester"
    assert rep.recon is not None and rep.discovery is not None and rep.discovery.openapi_available
    # M5 ran: enriched and sorted (confirmed first)
    first = rep.findings[0]
    assert first.evidence is Evidence.CONFIRMED and first.title and first.references
    assert first.repro is not None and first.repro.startswith("curl ") and "****" in first.repro
    assert first.fix_sql is not None and "CREATE POLICY" in first.fix_sql
    ranks = [{"confirmed": 2, "suspected": 1, "config_warning": 0}[f.evidence.value] for f in rep.findings]
    assert ranks == sorted(ranks, reverse=True)


def test_correct_rls_has_no_vulnerability() -> None:
    rep = scan(FakeSupabase(tables={"notes": notes_table()}), cfg())
    assert not [f for f in rep.findings if f.evidence is Evidence.CONFIRMED]
    sel = {(c.role, c.op.value): c.outcome for c in rep.matrix.cells if c.target == "notes"}
    assert sel[(Role.USER_A, "select")] is Outcome.DENIED and sel[(Role.ANON, "select")] is Outcome.DENIED


def test_ci_skips_m1_and_takes_the_anon_key_from_the_environment() -> None:
    fake = FakeSupabase(tables={"notes": notes_table(rls="all")})
    rep = scan(fake, cfg(profile=Profile.CI, anon_key_env="SB_ANON"))
    assert rep.modules == ["M2", "M3", "M5"] and rep.recon is None
    assert fake.to(APP) == []                       # the frontend is never fetched in ci
    assert ("notes", "user_a", "CROSS_TENANT_READ") in rules(rep)


def test_ci_without_anon_key_env_stops_before_any_request() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    with pytest.raises(ScanSetupError):
        scan(fake, cfg(profile=Profile.CI))
    assert fake.requests == []


def test_named_anon_key_env_that_is_unset_stops_before_any_request() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    with pytest.raises(ScanSetupError) as exc:
        scan(fake, cfg(anon_key_env="NOT_SET_ANYWHERE"))
    assert "NOT_SET_ANYWHERE" in str(exc.value) and fake.requests == []


def test_cli_profile_can_only_make_the_scan_stricter() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()})
    rep = scan(fake, cfg(profile=Profile.DEV), cli_profile=Profile.AUDIT)
    assert rep.profile is Profile.AUDIT
    rep2 = scan(FakeSupabase(tables={"notes": notes_table()}), cfg(profile=Profile.AUDIT), cli_profile=Profile.DEV)
    assert rep2.profile is Profile.AUDIT


def test_bundle_url_that_differs_from_the_confirmed_one_is_noted_never_contacted() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, bundle_url="http://other.test")
    rep = scan(fake, cfg())
    assert any("http://other.test" in n for n in rep.notes)
    assert "other.test" not in fake.hosts()


def _with_m4(monkeypatch: pytest.MonkeyPatch, lints: list[Lint] | Exception,
             policies: list[PolicyRow]) -> list[tuple[str, tuple[str, ...]]]:
    import rlsentry.pipeline as pl
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_splinter(db_url: str, db_schemas: Any = ("public",)) -> list[Lint]:
        calls.append(("splinter", tuple(db_schemas)))
        if isinstance(lints, Exception):
            raise lints
        return lints

    def fake_policies(db_url: str, db_schemas: Any = ("public",)) -> list[PolicyRow]:
        calls.append(("policies", tuple(db_schemas)))
        return policies
    monkeypatch.setattr(pl, "run_splinter", fake_splinter)
    monkeypatch.setattr(pl, "read_policies", fake_policies)
    return calls


def test_m4_correlates_m3_only_and_fills_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    pol = PolicyRow(schema="api", table="notes", name="notes_select", command="SELECT",
                    roles=["authenticated"], permissive=True, using="(auth.uid() IS NOT NULL)")
    calls = _with_m4(monkeypatch, [Lint(name="rls_policy_always_true", level="WARN", categories=["SECURITY"],
                                        object_schema="api", object_name="notes")], [pol])
    fake = FakeSupabase(tables={"notes": notes_table(rls="all")}, bundle_keys=(ANON_KEY, SERVICE_KEY))
    rep = scan(fake, cfg(db_url_env="DB", db_schemas=["api"]), env={**ENV, "DB": "postgresql://u:p@db/x"})
    assert rep.modules == ["M1", "M2", "M3", "M4", "M5"] and "M4" in rep.timings
    assert calls == [("splinter", ("api",)), ("policies", ("api",))]     # config db_schemas reach M4
    assert rep.policies == [pol]
    cross = [f for f in rep.findings if f.rule == "CROSS_TENANT_READ"]
    assert cross and all(f.correlation == "confirmed" for f in cross)
    key = [f for f in rep.findings if f.rule == "SECRET_KEY_IN_BUNDLE"]
    assert len(key) == 1 and key[0].correlation is None          # M1 never goes through correlate
    assert 'DROP POLICY "notes_select" ON "api"."notes";' in (cross[0].fix_sql or "")


def test_m4_failure_is_a_note_without_its_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_m4(monkeypatch, RuntimeError("could not connect to postgresql://u:secretpw@db/x"), [])
    rep = scan(FakeSupabase(tables={"notes": notes_table()}), cfg(db_url_env="DB"),
               env={**ENV, "DB": "postgresql://u:secretpw@db/x"})
    assert "M4" not in rep.modules and "M4 failed: RuntimeError" in rep.notes
    assert "secretpw" not in rep.model_dump_json()


def test_empty_db_url_env_means_no_m4() -> None:
    rep = scan(FakeSupabase(tables={"notes": notes_table()}), cfg(db_url_env="DB"), env={**ENV, "DB": ""})
    assert "M4" not in rep.modules and M4_SKIPPED_NOTE in rep.notes


def test_dev_on_localhost_probes_writes_seeds_and_cleans_up() -> None:
    table = notes_table()
    fake = FakeSupabase(tables={"notes": table})
    rep = scan(fake, cfg(profile=Profile.DEV))
    assert rep.modules == ["M1", "M2", "M3", "M5"]
    assert {"POST", "PATCH", "DELETE"} <= fake.methods()
    writes = [c for c in rep.matrix.cells if c.op.value != "select" and c.outcome is not Outcome.NOT_TESTED]
    assert writes and all(c.outcome is Outcome.DENIED for c in writes)
    assert not [f for f in rep.findings if f.rule == "CLEANUP_FAILED"]
    assert sorted(str(r["id"]) for r in table.rows) == sorted(str(r["id"]) for r in notes_table().rows)


def test_dev_detects_user_metadata_escalation_and_restores_it() -> None:
    t = Table(rows=notes_table().rows, admin_metadata=True)
    fake = FakeSupabase(tables={"notes": t})
    rep = scan(fake, cfg(profile=Profile.DEV))
    esc = {(f.role, f.evidence) for f in rep.findings if f.rule == "USER_METADATA_ESCALATION"}
    assert esc == {(Role.USER_A, Evidence.CONFIRMED), (Role.USER_B, Evidence.CONFIRMED)}
    assert set(fake.metadata_role.values()) == {None}                 # both accounts restored
    assert fake.metadata_role.keys() >= {A}


def test_report_never_contains_a_full_key_or_password() -> None:
    fake = FakeSupabase(tables={"notes": notes_table(rls="all")}, bundle_keys=(ANON_KEY, SERVICE_KEY))
    text = scan(fake, cfg(profile=Profile.DEV)).model_dump_json()
    for secret in (ANON_KEY, SERVICE_KEY, "pw-a", "pw-b"):
        assert secret not in text
