"""probe/read.py (FR-06: HEAD + count, no body). Contract: rlsentry/contracts/probe.py count_visible."""
import httpx
import pytest

from rlsentry.contracts.models import Target
from rlsentry.probe.read import count_visible
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

TOKEN = fake_jwt("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def tgt(kind: str = "table", pk: list[str] | None = None) -> Target:
    return Target(name="notes" if kind == "table" else "get_all", kind=kind, primary_key=["id"] if pk is None else pk,
                  discovered_by="openapi", confidence="confirmed")


def answer(cr: str | None, status: int = 200) -> Recorder:
    return Recorder(lambda r: httpx.Response(status, headers={"Content-Range": cr} if cr else {}))


def test_request_shape() -> None:
    rec = answer("*/0")
    res = run(lambda c: count_visible(c, URL, ANON, tgt(), TOKEN, ["p1", "p2"]), rec)
    (req,) = rec.requests
    assert req.method == "HEAD" and req.url.path == "/rest/v1/notes"
    assert dict(req.url.params) == {"select": "id", "id": 'in.("p1","p2")'}
    assert req.headers["apikey"] == ANON and req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["prefer"] == "count=exact"
    assert res.queried == 2 and res.status == 200 and res.total == 0


@pytest.mark.parametrize("cr,total", [("*/0", 0), ("0-1/2", 2), ("0-0/1", 1), ("*/*", None), ("garbage", None),
                                      (None, None), ("0-1/x", None)])
def test_total_parsing(cr: str | None, total: int | None) -> None:
    assert run(lambda c: count_visible(c, URL, ANON, tgt(), TOKEN, ["p"]), answer(cr)).total == total


def test_values_are_quoted_postgrest_literals() -> None:
    rec = answer("*/0")
    run(lambda c: count_visible(c, URL, ANON, tgt(), TOKEN, ['a,b', 'q"x', "b\\s"]), rec)
    assert rec.requests[0].url.params["id"] == 'in.("a,b","q\\"x","b\\\\s")'


def test_rpc_path_and_status_kept() -> None:
    rec = answer(None, 404)
    res = run(lambda c: count_visible(c, URL, ANON, tgt("rpc"), TOKEN, ["p"]), rec)
    assert rec.requests[0].url.path == "/rest/v1/rpc/get_all" and res.status == 404 and res.total is None


def test_precondition_errors() -> None:
    with pytest.raises(ValueError):
        run(lambda c: count_visible(c, URL, ANON, tgt(), TOKEN, []), answer("*/0"))
    with pytest.raises(ValueError):
        run(lambda c: count_visible(c, URL, ANON, tgt(pk=["a", "b"]), TOKEN, ["p"]), answer("*/0"))


def test_transport_error_is_no_status() -> None:
    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)
    res = run(lambda c: count_visible(c, URL, ANON, tgt(), TOKEN, ["p"]), Recorder(boom))
    assert res.status is None and res.total is None


@pytest.mark.safety
def test_curl_is_masked_head() -> None:
    res = run(lambda c: count_visible(c, URL, ANON, tgt(), TOKEN, ["p"]), answer("*/0"))
    assert res.curl.startswith("curl -sS -I ") and TOKEN not in res.curl and ANON not in res.curl
    assert "count=exact" in res.curl and "/rest/v1/notes" in res.curl
