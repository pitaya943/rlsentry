"""ADR-040 (MS4 approval note 2): one request per (target, role) for the known-row check.

visible_pks / observation_counts (contract: rlsentry/contracts/probe.py) and probe() using them.
The merge must not change any verdict, must keep the "filter not applied = untrustworthy" check
(ADR-023 #3) and must download primary keys only.
"""
from __future__ import annotations

import httpx
import pytest

from rlsentry.contracts.models import Op, Outcome, Role, Target
from rlsentry.contracts.probe import CountResult, VisibleResult
from rlsentry.probe.read import observation_counts, visible_pks
from tests.fakes import ANON, URL, Recorder, fake_jwt, run
from tests.probe.test_run import ALL, TWO, FakeRest, Rel, scan, sel, todos

TOK = fake_jwt("u-1")
T = Target(name="todos", kind="table", columns=["id", "owner_id"], primary_key=["id"],
           discovered_by="openapi", confidence="confirmed")


def vis(handler: httpx.Response | Exception, pks: list[str], target: Target = T) -> tuple[VisibleResult, Recorder]:
    def h(r: httpx.Request) -> httpx.Response:
        if isinstance(handler, Exception):
            raise handler
        return handler
    rec = Recorder(h)
    return run(lambda c: visible_pks(c, URL, ANON, target, TOK, pks), rec), rec


def test_request_shape_is_one_get_of_primary_keys_only() -> None:
    res, rec = vis(httpx.Response(200, json=[{"id": "b"}]), ["a", 'b"x'])
    [r] = rec.requests
    assert r.method == "GET" and r.url.path == "/rest/v1/todos"
    assert dict(r.url.params) == {"select": "id", "id": 'in.("a","b\\"x")', "limit": "2"}
    assert r.headers["apikey"] == ANON and r.headers["authorization"] == f"Bearer {TOK}"
    assert "prefer" not in r.headers
    assert res.queried == 2 and res.status == 200 and res.curl.startswith("curl -sS -X GET ")
    assert TOK not in res.curl and ANON not in res.curl


def test_rpc_path() -> None:
    rpc = T.model_copy(update={"name": "get_all", "kind": "rpc"})
    _, rec = vis(httpx.Response(200, json=[]), ["a"], rpc)
    assert rec.requests[0].url.path == "/rest/v1/rpc/get_all"


def test_visible_keeps_response_order_and_drops_duplicates() -> None:
    res, _ = vis(httpx.Response(200, json=[{"id": "b"}, {"id": "a"}, {"id": "b"}]), ["a", "b", "c"])
    assert res.visible == ["b", "a"]


@pytest.mark.parametrize("resp", [
    httpx.Response(200, json=[{"id": "zzz"}]),          # a row outside the queried set: filter not applied
    httpx.Response(200, json={"id": "a"}),              # not a list
    httpx.Response(200, json=[{"title": "a"}]),         # pk missing
    httpx.Response(200, json=[{"id": None}]),
    httpx.Response(200, content=b"not json"),
    httpx.Response(401, json=[]),
    httpx.Response(404, json=[]),
])
def test_untrustworthy_responses_give_no_visible_set(resp: httpx.Response) -> None:
    res, _ = vis(resp, ["a", "b"])
    assert res.visible is None and res.status == resp.status_code


def test_transport_error_is_not_raised() -> None:
    res, _ = vis(httpx.ConnectError("boom"), ["a"])
    assert (res.status, res.visible) == (None, None)


def test_preconditions() -> None:
    with pytest.raises(ValueError):
        vis(httpx.Response(200, json=[]), [])
    with pytest.raises(ValueError):
        vis(httpx.Response(200, json=[]), ["a"], T.model_copy(update={"primary_key": ["a", "b"]}))


def test_observation_counts_split() -> None:
    res = VisibleResult(queried=3, status=200, visible=["f1", "p1"], curl="c")
    f, p = observation_counts(res, ["f1", "f2"], ["p1"])
    assert f == CountResult(queried=2, status=200, total=1, curl="c")
    assert p == CountResult(queried=1, status=200, total=1, curl="c")
    assert observation_counts(res, [], ["p1"])[0] is None
    bad = VisibleResult(queried=1, status=200, visible=None, curl="c")
    assert observation_counts(bad, ["f1"], [])[0] == CountResult(queried=1, status=200, total=None, curl="c")
    with pytest.raises(ValueError):
        observation_counts(None, ["f1"], [])


def test_probe_sends_one_request_per_role_and_keeps_the_verdicts() -> None:
    cells, findings, rec = scan(FakeRest({"todos": Rel(TWO, rls=ALL)}), [todos()])
    assert sel(cells) == [(Outcome.DENIED, 2), (Outcome.ALLOWED, 1), (Outcome.ALLOWED, 1)]
    reads = [r for r in rec.requests if "id" in r.url.params]
    assert len(reads) == 3 and {r.method for r in reads} == {"GET"}   # anon, user_a, user_b
    assert len(rec.requests) == 5                                       # + 2 own-row listings
    assert "HEAD" not in rec.methods()
    assert ("todos", Role.USER_A, "CROSS_TENANT_READ") in findings


def test_probe_permitted_rows_still_feed_the_hints() -> None:
    # user_a cannot see its own row → EXPECTED_ACCESS_DENIED from the same merged request
    deny_all = Rel(TWO, rls=lambda uid, r: False)
    cells, findings, rec = scan(FakeRest({"todos": deny_all}), [todos()])
    assert ("todos", Role.USER_A, "EXPECTED_ACCESS_DENIED") in findings
    assert len([r for r in rec.requests if "id" in r.url.params]) == 3
    assert cells[("todos", Role.USER_A, Op.SELECT)][0] is Outcome.DENIED
