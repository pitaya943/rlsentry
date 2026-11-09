"""discovery/openapi.py (FR-04). Contract: rlsentry/contracts/discovery.py; ADR-023 #1."""
from typing import Any

import httpx
import pytest

from rlsentry.contracts.models import Target
from rlsentry.discovery.openapi import fetch_openapi, parse_openapi
from tests.fakes import ANON, URL, Recorder, run

PK = {"format": "uuid", "description": "Note:\nThis is a Primary Key.<pk/>"}


def doc(**extra: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "swagger": "2.0",
        "paths": {"/": {"get": {}}, "/accounts": {"get": {}, "post": {}},
                  "/rpc/get_all_accounts": {"get": {}, "post": {}},
                  "/invoice_summary": {"get": {}}},
        "definitions": {
            "accounts": {"properties": {"id": PK, "owner_id": {"format": "uuid"}, "balance": {}}},
            "invoice_summary": {"properties": {"amount": {}, "id": PK}},
        },
    }
    d.update(extra)
    return d


OLD_FIELDS = {"name", "kind", "columns", "primary_key", "discovered_by", "confidence"}


def test_tables_and_rpcs_with_columns_and_primary_keys() -> None:
    # Compares the MS2 fields; required/column_formats (ADR-034) are tested in test_openapi_types.
    got = [t.model_dump(include=OLD_FIELDS) for t in parse_openapi(doc())]
    assert got == [t.model_dump(include=OLD_FIELDS) for t in [
        Target(name="accounts", kind="table", columns=["id", "owner_id", "balance"], primary_key=["id"],
               discovered_by="openapi", confidence="confirmed"),
        Target(name="get_all_accounts", kind="rpc", discovered_by="openapi", confidence="confirmed"),
        Target(name="invoice_summary", kind="table", columns=["amount", "id"], primary_key=["id"],
               discovered_by="openapi", confidence="confirmed"),
    ]]


def test_view_is_reported_as_table_never_view() -> None:
    # ADR-023 #1: a GET-only path (as a view could be) is still kind "table".
    assert {t.kind for t in parse_openapi(doc())} == {"table", "rpc"}


def test_composite_primary_key_in_document_order() -> None:
    d = doc(definitions={"accounts": {"properties": {"b": PK, "x": {}, "a": PK}}})
    acc = next(t for t in parse_openapi(d) if t.name == "accounts")
    assert acc.primary_key == ["b", "a"] and acc.columns == ["b", "x", "a"]


def test_missing_definition_gives_empty_columns() -> None:
    d = doc(definitions={})
    acc = next(t for t in parse_openapi(d) if t.name == "accounts")
    assert acc.columns == [] and acc.primary_key == []


def test_hostile_or_odd_paths_are_ignored() -> None:
    d = doc(paths={"/a/b": {}, "/rpc/": {}, "/rpc/x y": {}, "/x?y=1": {}, "/1abc": {}, "notes": {},
                   "/rpc/a/b": {}, "/ok_name": {}})
    assert [t.name for t in parse_openapi(d)] == ["ok_name"]


@pytest.mark.parametrize("bad", [{}, {"paths": []}, {"paths": None}, {"paths": {"/t": {}}, "definitions": []},
                                 {"paths": {"/t": {}}, "definitions": {"t": {"properties": [1]}}},
                                 {"paths": {"/t": {}}, "definitions": {"t": {"properties": {"id": {"description": 5}}}}}])
def test_malformed_documents_never_raise(bad: dict[str, Any]) -> None:
    for t in parse_openapi(bad):
        assert t.name == "t" and t.primary_key == []


def test_fetch_sends_one_get_with_anon_headers() -> None:
    rec = Recorder(lambda r: httpx.Response(200, json=doc()))
    got = run(lambda c: fetch_openapi(c, URL + "/", ANON), rec)
    assert got == doc()
    (req,) = rec.requests
    assert req.method == "GET" and str(req.url) == URL + "/rest/v1/"
    assert req.headers["apikey"] == ANON and req.headers["authorization"] == f"Bearer {ANON}"


@pytest.mark.parametrize("resp", [
    httpx.Response(404, json={"code": "PGRST126", "message": "Root endpoint metadata is disabled"}),
    httpx.Response(200, text="<html>not json</html>"),
    httpx.Response(200, json=[{"paths": {}}]),
    httpx.Response(200, json={"swagger": "2.0", "paths": ["/x"]}),
    httpx.Response(500, json={"paths": {}}),
])
def test_fetch_returns_none_when_unavailable(resp: httpx.Response) -> None:
    assert run(lambda c: fetch_openapi(c, URL, ANON), Recorder(lambda r: resp)) is None


def test_fetch_transport_error_is_none_not_raised() -> None:
    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=r)
    assert run(lambda c: fetch_openapi(c, URL, ANON), Recorder(boom)) is None
