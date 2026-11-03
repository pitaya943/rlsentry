"""discovery/discover.py: the M2 entry point. Contract: rlsentry/contracts/discovery.py."""
import httpx

from rlsentry.contracts.policy import ExpectedPolicy, TablePolicy
from rlsentry.discovery.discover import discover
from tests.fakes import ANON, URL, Recorder, run

DOC = {"swagger": "2.0", "paths": {"/notes": {"get": {}}},
       "definitions": {"notes": {"properties": {"id": {"description": "<pk/>"}, "owner_id": {}}}}}
POLICY = ExpectedPolicy(tables={"secret_table": TablePolicy(primary_key=["id"])})


def test_openapi_available() -> None:
    rec = Recorder(lambda r: httpx.Response(200, json=DOC))
    res = run(lambda c: discover(c, URL, ANON, POLICY, ["s.from('notes'); s.rpc('f')"]), rec)
    assert res.openapi_available is True
    assert [(t.name, t.kind, t.discovered_by, t.confidence) for t in res.targets] == [
        ("f", "rpc", "bundle", "inferred"), ("notes", "table", "openapi", "confirmed"),
        ("secret_table", "table", "policy", "unknown")]
    assert rec.methods() == {"GET"} and len(rec.requests) == 1


def test_openapi_restricted_falls_back_to_bundle() -> None:
    rec = Recorder(lambda r: httpx.Response(404, json={"code": "PGRST126"}))
    res = run(lambda c: discover(c, URL, ANON, POLICY, ["s.from('notes')"]), rec)
    assert res.openapi_available is False
    assert [(t.name, t.confidence) for t in res.targets] == [("notes", "inferred"), ("secret_table", "unknown")]
