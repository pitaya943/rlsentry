"""MS6 holdout: same behaviour as the visible tests, different inputs (never shown to implementers)."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from rlsentry.contracts.models import Evidence, Op, PolicyRow, Profile, Role, Severity, finding_id
from rlsentry.contracts.pipeline import EndpointRefused
from rlsentry.contracts.policy import FailOn, ScanConfig, TestUser
from rlsentry.contracts.probe import WRITE_REFUSED_REASON, Sessions
from rlsentry.contracts.recon import Candidate
from rlsentry.contracts.report import EXIT_FINDINGS, EXIT_OK, FixContext
from rlsentry.contracts.whitebox import Lint
from rlsentry.pipeline import run_scan
from rlsentry.probe.escalation import escalation_pass
from rlsentry.probe.session import build_sessions
from rlsentry.recon.classify import classify_key, findings_from_keys, key_finding
from rlsentry.report.exit_code import exit_code
from rlsentry.report.fix_sql import fix_sql
from rlsentry.report.html import render_html
from rlsentry.safety.endpoint import resolve_endpoint
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from rlsentry.whitebox.correlate import correlate
from tests.pipeline.fake_supabase import (
    ANON_KEY, API, APP, ENV, OWNER_ONLY, REMOTE, USERS, FakeSupabase, Table, jwt, notes_table,
)
from tests.pipeline.helpers import cfg, scan
from tests.probe.test_escalation import DENIED
from tests.probe.test_seed_pass import tgt
from tests.report.helpers import finding, report


# --- MS5 approval note 4 --------------------------------------------------------------------
@pytest.mark.parametrize("role, kind", [("supabase_read_only_user", "secret"), ("supabase_etl_admin", "secret"),
                                        ("authenticated", "unverified"), ("anon", "publishable"),
                                        ("supabase_auth_admin", "unverified")])
def test_holdout_privileged_roles(role: str, kind: str) -> None:
    tok = jwt({"role": role, "ref": "zyxwvutsrqponmlkjihg", "exp": 1999999999})
    assert classify_key(Candidate(tok, "jwt"))[0] == kind
    fs = findings_from_keys([key_finding(Candidate(tok, "jwt"), "main.js")])
    if kind == "secret":
        assert [(f.rule, f.severity, f.evidence) for f in fs] == [("SECRET_KEY_IN_BUNDLE", Severity.CRITICAL,
                                                                   Evidence.CONFIRMED)]
    elif kind == "publishable":
        assert fs == []
    else:
        assert [f.rule for f in fs] == ["UNVERIFIED_KEY"]


# --- S4 (MS5 approval note 6) ----------------------------------------------------------------
def test_holdout_bundle_on_another_port_gets_nothing() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, bundle_url="http://127.0.0.1:9999")
    with pytest.raises(EndpointRefused) as exc:
        scan(fake, cfg(supabase_url=None, profile=Profile.DEV))
    assert all(r.url.host == "app.test" for r in fake.requests)
    assert "127.0.0.1:9999" in str(exc.value)


def test_holdout_resolve_prefers_named_url_over_bundle() -> None:
    c = ScanConfig(target="https://shop.example.test", supabase_url="https://Proj.supabase.co:443")
    assert resolve_endpoint(c, None, "https://attacker.test") == ("https://proj.supabase.co", "config")
    with pytest.raises(EndpointRefused):
        resolve_endpoint(ScanConfig(target="https://shop.example.test"), None, "https://proj.supabase.co")


# --- audit cannot write; the stricter profile wins ------------------------------------------
@pytest.mark.parametrize("conf, cli", [(Profile.AUDIT, Profile.DEV), (Profile.CI, Profile.AUDIT)])
def test_holdout_audit_never_writes(conf: Profile, cli: Profile) -> None:
    fake = FakeSupabase(tables={"notes": notes_table(rls="all"), "todo": notes_table()})
    rep = scan(fake, cfg(profile=conf, anon_key_env="SB_ANON",
                         tables={"notes": OWNER_ONLY, "todo": OWNER_ONLY}), cli_profile=cli)
    assert rep.profile is Profile.AUDIT
    bad = [r for r in fake.requests if r.method not in ("GET", "HEAD") and r.url.path != "/auth/v1/token"]
    assert bad == []
    assert all(c.outcome.value == "not_tested" for c in rep.matrix.cells if c.op is not Op.SELECT)


# --- CI fails only on Confirmed --------------------------------------------------------------
def test_holdout_exit_codes() -> None:
    key = finding("SECRET_KEY_IN_BUNDLE", "jwt:supabase_admin")
    sus = finding("ANON_WRITE", "t", Role.ANON, Op.DELETE, evidence=Evidence.SUSPECTED, severity=Severity.CRITICAL)
    assert exit_code(report(findings=[key], profile=Profile.CI), FailOn()) == EXIT_FINDINGS
    assert exit_code(report(findings=[sus], profile=Profile.CI), FailOn()) == EXIT_OK
    assert exit_code(report(findings=[key], profile=Profile.AUDIT), FailOn()) == EXIT_OK
    high = finding("CROSS_TENANT_WRITE", "t", Role.USER_B, Op.DELETE)
    assert exit_code(report(findings=[high], profile=Profile.CI), FailOn(severity=Severity.CRITICAL)) == EXIT_OK


# --- correlate per (object, role) ------------------------------------------------------------
def test_holdout_correlate_user_only_proof() -> None:
    f = finding("CROSS_TENANT_READ", "export_all", Role.USER_B, Op.SELECT)
    lints = [Lint(name=n, level="WARN", categories=["SECURITY"], object_schema="public", object_name="export_all")
             for n in ("authenticated_security_definer_function_executable", "anon_security_definer_function_executable")]
    out = correlate([f], lints)
    assert (out[0].rule, out[0].id) == ("SECURITY_DEFINER_RPC_DATA",
                                        finding_id("export_all", Role.USER_B, Op.SELECT, "SECURITY_DEFINER_RPC_DATA"))
    warn = [x for x in out if x.rule == "SECURITY_DEFINER_EXECUTABLE"]
    assert [(w.role, w.evidence) for w in warn] == [(Role.ANON, Evidence.CONFIG_WARNING)]


# --- fix SQL and HTML never let target text escape ------------------------------------------
def test_holdout_fix_sql_quotes_schema_and_policy() -> None:
    f = finding("ANON_READ_OWNER_SCOPED", "orders", Role.ANON, Op.SELECT)
    sql = fix_sql(f, FixContext(kind="table", schema_name='my"schema', scope=None, policies=[PolicyRow(
        schema='my"schema', table="orders", name="open read", command="ALL", roles=["anon"], permissive=True)]))
    assert sql is not None and '"my""schema"."orders"' in sql and 'DROP POLICY "open read"' in sql
    # MS7 update (ADR-053): since ADR-051 #1 only policies that can serve the finding's role are
    # dropped, so the unsafe name sits on a policy for anon (pg_policies never has empty roles).
    bad = FixContext(kind="table", policies=[PolicyRow(schema="public", table="orders", name="x\n; DROP", command="ALL",
                                                       roles=["anon"], permissive=True)])
    assert fix_sql(f, bad) is None


def test_holdout_html_escapes_notes() -> None:
    rep = report(findings=[]).model_copy(update={"notes": ['<img src="http://x.test/a.png">']})
    doc = render_html(rep)
    assert "<img" not in doc and "&lt;img" in doc


# --- merged reads across targets ------------------------------------------------------------
def test_holdout_one_read_request_per_role_and_target() -> None:
    fake = FakeSupabase(tables={"a": notes_table(), "b": notes_table(rls="all")})
    rep = scan(fake, cfg(tables={"a": OWNER_ONLY, "b": OWNER_ONLY}))
    reads = [r for r in fake.to(API) if r.method == "GET" and "id" in r.url.params]
    assert len(reads) == 6 and not [r for r in fake.to(API) if r.method == "HEAD"]
    assert {(f.target, f.rule) for f in rep.findings if f.evidence is Evidence.CONFIRMED} == {("b", "CROSS_TENANT_READ")}


# --- escalation restores even when re-login fails ---------------------------------------------
def test_holdout_escalation_restores_after_failed_relogin() -> None:
    fake = FakeSupabase(tables={"notes": Table(rows=notes_table().rows, admin_metadata=True)})
    wrong = [TestUser(name=Role.USER_A, email="nobody@test.dev", password_env="RLS_A_PW")]

    async def go() -> tuple[list[Any], list[str]]:
        async with SafeClient(profile=Profile.DEV, limiter=RateLimiter(rps=1e6, concurrency=8),
                              transport=fake.transport()) as c:
            s: Sessions = await build_sessions(c, API, ANON_KEY, USERS, ENV)
            return await escalation_pass(c, API, ANON_KEY, [tgt("notes")], cfg().policy, s, wrong, ENV, DENIED)
    findings, notes = asyncio.run(go())
    assert findings == [] and any("re-login after escalation failed" in n for n in notes)
    assert all(v is None for v in fake.metadata_role.values()) and fake.metadata_role


# --- ci without write_hosts against a remote host -------------------------------------------
def test_holdout_ci_unlisted_remote_host_is_inconclusive() -> None:
    fake = FakeSupabase(tables={"notes": notes_table()}, api=REMOTE)
    rep = scan(fake, cfg(profile=Profile.CI, supabase_url=REMOTE, anon_key_env="SB_ANON"))
    writes = [c for c in rep.matrix.cells if c.op is not Op.SELECT]
    assert writes and all(c.reason.startswith(WRITE_REFUSED_REASON) for c in writes)
    assert not [r for r in fake.requests if r.method in ("PATCH", "DELETE", "PUT")]
    assert APP and httpx
