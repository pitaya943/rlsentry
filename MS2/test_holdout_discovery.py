"""MS2 holdout: M2 discovery with inputs not used by the visible tests."""
import httpx

from rlsentry.contracts.policy import ExpectedPolicy, TablePolicy
from rlsentry.discovery.bundle import infer_from_bundle
from rlsentry.discovery.discover import discover
from rlsentry.discovery.merge import merge_targets
from rlsentry.discovery.openapi import parse_openapi
from tests.fakes import ANON, URL, Recorder, run


def test_openapi_other_document() -> None:
    doc = {"paths": {"/rpc/do_stuff": {"post": {}}, "/Orders": {"get": {}}, "/line_items": {"get": {}},
                     "/rpc/2bad": {}, "/rest/v1/x": {}},
           "definitions": {"Orders": {"properties": {"order_no": {"description": "Primary Key.<pk/> note"},
                                                     "customer_email": {"description": "plain"}}},
                           "line_items": {"properties": {"order_no": {"description": "<pk/>"},
                                                         "line": {"description": "x <pk/>"}, "qty": {}}}}}
    got = {(t.name, t.kind): (t.columns, t.primary_key) for t in parse_openapi(doc)}
    assert got == {("Orders", "table"): (["order_no", "customer_email"], ["order_no"]),
                   ("do_stuff", "rpc"): ([], []),
                   ("line_items", "table"): (["order_no", "line", "qty"], ["order_no", "line"])}
    assert [t.name for t in parse_openapi(doc)] == sorted(n for n, _ in got)


def test_bundle_other_shapes() -> None:
    src = ('await t.from("orders").select("*");r.rpc("do_thing",{a:1});supabase .storage .from(\'b\');'
           'Object.from("o");x.from(`line_items`).delete();$.from("dollar")')
    assert [(t.name, t.kind) for t in infer_from_bundle([src])] == [
        ("do_thing", "rpc"), ("dollar", "table"), ("line_items", "table"), ("orders", "table")]


def test_merge_policy_pk_for_inferred_and_unknown() -> None:
    from tests.discovery.test_merge import bd
    got = merge_targets(None, [bd("orders"), bd("get_x", "rpc")],
                        ExpectedPolicy(tables={"orders": TablePolicy(primary_key=["order_no"]),
                                               "get_x": TablePolicy(primary_key=["k"]),
                                               "hidden": TablePolicy()}))
    assert [(t.name, t.kind, t.primary_key, t.confidence) for t in got] == [
        ("get_x", "rpc", ["k"], "inferred"), ("hidden", "table", [], "unknown"),
        ("orders", "table", ["order_no"], "inferred")]


def test_discover_server_error_falls_back() -> None:
    rec = Recorder(lambda r: httpx.Response(503, text="down"))
    res = run(lambda c: discover(c, URL, ANON, ExpectedPolicy(), ["a.rpc('f'); a.from('g')"]), rec)
    assert res.openapi_available is False and [t.name for t in res.targets] == ["f", "g"]
