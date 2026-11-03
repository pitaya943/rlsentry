"""MS2 holdout: M3 read probing with inputs not used by the visible tests."""
import base64
import json
from collections.abc import Callable

import httpx
import pytest

from rlsentry.contracts.models import AccessMatrix, Finding, Op, Outcome, Profile, Role, Severity, Target
from rlsentry.contracts.policy import (
    ExpectedAccess,
    ExpectedPolicy,
    RoleScopes,
    RowScope,
    TablePolicy,
    TestUser,
)
from rlsentry.contracts.probe import CountResult, KnownRow, LoginFailed, ReadObservation, Sessions
from rlsentry.probe.cross_tenant import collect_known_rows
from rlsentry.probe.diff import read_findings
from rlsentry.probe.evidence import curl_command
from rlsentry.probe.read import count_visible
from rlsentry.probe.run import probe
from rlsentry.probe.session import build_sessions, login
from rlsentry.probe.verdict import read_cell, split_known
from rlsentry.rules.severity import read_severity
from rlsentry.safety.mask import mask
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TA, TB = fake_jwt(A, "x"), fake_jwt(B, "y")
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: TA, Role.USER_B: TB}, user_ids={Role.USER_A: A, Role.USER_B: B})


def cr(status: int | None, total: int | None, q: int) -> CountResult:
    return CountResult(queried=q, status=status, total=total, curl="c")


def ob(f: CountResult | None) -> ReadObservation:
    e = ExpectedAccess(target="t", op=Op.SELECT, role=Role.ANON, scope=RowScope.DENY)
    return ReadObservation(target="t", role=Role.ANON, expected=e, forbidden=f)


@pytest.mark.parametrize("f,outcome", [(cr(206, 3, 3), Outcome.ALLOWED), (cr(200, 4, 3), Outcome.INCONCLUSIVE),
                                       (cr(200, None, 3), Outcome.INCONCLUSIVE), (cr(204, 0, 3), Outcome.INCONCLUSIVE),
                                       (cr(200, 0, 1), Outcome.DENIED), (cr(403, 0, 1), Outcome.INCONCLUSIVE)])
def test_verdict_edges(f: CountResult, outcome: Outcome) -> None:
    c = read_cell(ob(f))
    assert c.outcome is outcome
    assert c.known_rows_checked == (f.queried if outcome is not Outcome.INCONCLUSIVE else 0)


def test_split_anon_public_or_own_and_unknown_owner() -> None:
    e = ExpectedAccess(target="t", op=Op.SELECT, role=Role.ANON, scope=RowScope.PUBLIC_OR_OWN_ROWS)
    rows = [KnownRow(pk="1", owner=Role.USER_B, public=True), KnownRow(pk="2", owner=Role.USER_B)]
    assert split_known(e, rows, {Role.USER_B: B}) == (["2"], ["1"])


def test_severity_case_insensitive_escalation() -> None:
    assert read_severity("ANON_READ_OWNER_SCOPED", ["Mobile_Phone"]) is Severity.CRITICAL
    assert read_severity("SECURITY_DEFINER_RPC_DATA", ["email"]) is Severity.MEDIUM


@pytest.mark.safety
def test_curl_masks_publishable_key_and_basic_auth() -> None:
    key = "sb_publishable_" + "AbCdEfGhIjKlMnOpQrSt"
    cmd = curl_command("HEAD", URL + "/rest/v1/t", {"apikey": key, "Authorization": "Basic dXNlcjpwYXNzd29yZDEyMzQ1Njc4OQ=="})
    assert key not in cmd and "dXNlcjpwYXNzd29yZDEyMzQ1Njc4OQ==" not in cmd and mask(key) in cmd


def test_count_single_quoted_value() -> None:
    rec = Recorder(lambda r: httpx.Response(206, headers={"Content-Range": "0-0/1"}))
    t = Target(name="t", kind="table", primary_key=["code"], discovered_by="openapi", confidence="confirmed")
    res = run(lambda c: count_visible(c, URL, ANON, t, TA, ["it's"]), rec)
    assert rec.requests[0].url.params["code"] == 'in.("it\'s")' and (res.status, res.total) == (206, 1)


def test_known_rows_public_request_fails_private_kept() -> None:
    def h(r: httpx.Request) -> httpx.Response:
        if r.url.params.get("flag") == "is.true":
            return httpx.Response(500)
        return httpx.Response(200, json=[{"pk": "p-" + r.headers["authorization"][-12:]}])
    t = Target(name="t", kind="table", primary_key=["pk"], discovered_by="openapi", confidence="confirmed")
    got = run(lambda c: collect_known_rows(c, URL, ANON, t, "uid", "flag", SESS), Recorder(h))
    assert len(got.rows) == 2 and not any(r.public for r in got.rows)
    assert got.notes == ["user_a: HTTP 500", "user_b: HTTP 500"]


@pytest.mark.safety
def test_login_sub_must_be_string() -> None:
    bad = "eyJhbGciOiJIUzI1NiJ9." + base64.urlsafe_b64encode(json.dumps({"sub": 5}).encode()).decode().rstrip("=") + ".s"
    with pytest.raises(LoginFailed):
        run(lambda c: login(c, URL, ANON, "a@x", "pw-123"), Recorder(lambda r: httpx.Response(200, json={"access_token": bad})))


def test_no_passwords_no_requests() -> None:
    rec = Recorder()
    users = [TestUser(name=Role.USER_A, email="a@x", password_env="PA"), TestUser(name=Role.USER_B, email="b@x", password_env="PB")]
    s = run(lambda c: build_sessions(c, URL, ANON, users, {}), rec)
    assert rec.requests == [] and set(s.missing) == {Role.USER_A, Role.USER_B} and s.tokens == {Role.ANON: ANON}


def test_rpc_user_leak_finding() -> None:
    t = Target(name="f", kind="rpc", primary_key=["id"], discovered_by="openapi", confidence="confirmed")
    e = ExpectedAccess(target="f", op=Op.SELECT, role=Role.USER_B, scope=RowScope.OWN_ROWS_ONLY)
    o = ReadObservation(target="f", role=Role.USER_B, expected=e, forbidden=cr(200, 1, 1))
    (f,) = read_findings(t, o, read_cell(o))
    assert (f.rule, f.severity) == ("SECURITY_DEFINER_RPC_DATA", Severity.MEDIUM)


def run_probe(handler: Callable[[httpx.Request], httpx.Response], targets: list[Target],
              policy: ExpectedPolicy) -> tuple[AccessMatrix, list[Finding], Recorder]:
    rec = Recorder(handler)
    matrix, findings = run(lambda c: probe(c, URL, ANON, targets, SESS, policy, Profile.CI), rec, Profile.CI)
    return matrix, findings, rec


def test_public_profiles_anon_sensitive_warning_and_401_never_denied() -> None:
    rows = [("p1", A, True), ("p2", B, False)]

    def h(r: httpx.Request) -> httpx.Response:
        uid = {f"Bearer {TA}": A, f"Bearer {TB}": B}.get(r.headers["authorization"])
        p = r.url.params
        vis = [x for x in rows if x[2] or x[1] == uid]
        if r.method == "GET":
            vis = [x for x in vis if p["user_id"] == f"eq.{x[1]}" and p["is_public"] == ("is.true" if x[2] else "is.false")]
            return httpx.Response(200, json=[{"id": x[0]} for x in vis])
        if uid is None and "p2" in p["id"]:
            return httpx.Response(401)
        want = p["id"]
        n = len([x for x in vis if f'"{x[0]}"' in want])
        return httpx.Response(200, headers={"Content-Range": f"*/{n}" if not n else f"0-{n - 1}/{n}"})

    t = Target(name="pp", kind="table", columns=["id", "user_id", "email", "is_public"], primary_key=["id"],
               discovered_by="openapi", confidence="confirmed")
    pol = ExpectedPolicy(tables={"pp": TablePolicy(owner_column="user_id", public_column="is_public", select=RoleScopes(
        anon=RowScope.PUBLIC_ROWS_ONLY, user=RowScope.PUBLIC_OR_OWN_ROWS))})
    matrix, findings, rec = run_probe(h, [t], pol)
    cells = {(c.role, c.op): c for c in matrix.cells}
    assert cells[(Role.ANON, Op.SELECT)].outcome is Outcome.INCONCLUSIVE   # 401 is never "denied"
    assert cells[(Role.USER_A, Op.SELECT)].outcome is Outcome.DENIED
    assert cells[(Role.USER_B, Op.SELECT)].outcome is Outcome.INCONCLUSIVE  # A has only a public row
    assert ("SENSITIVE_COLUMN_PUBLIC", Role.ANON) in {(f.rule, f.role) for f in findings}
    assert not any(f.evidence.value == "confirmed" for f in findings)
    assert rec.methods() <= {"GET", "HEAD"}
