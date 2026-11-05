"""probe.fill.fill_required (ADR-034): values for required columns the caller does not set."""
from __future__ import annotations

from datetime import UTC, date, datetime

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import CANARY_PREFIX
from rlsentry.probe.fill import fill_required

OWNER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def tgt(required: list[str], formats: dict[str, str]) -> Target:
    return Target(name="t", kind="table", columns=list(formats), primary_key=["id"], required=required,
                  column_formats=formats, discovered_by="openapi", confidence="confirmed")


def test_l05_created_by_gets_owner_id() -> None:
    t = tgt(["id", "owner_id", "created_by", "name"],
            {"id": "uuid", "owner_id": "uuid", "created_by": "uuid", "name": "text"})
    assert fill_required(t, OWNER, {"id", "owner_id", "name"}) == {"created_by": OWNER}


def test_l01_email_text_gets_canary() -> None:
    t = tgt(["id", "owner_id", "name", "email"], {"id": "uuid", "owner_id": "uuid", "name": "text", "email": "text"})
    got = fill_required(t, OWNER, {"id", "owner_id", "name"})
    assert got is not None and list(got) == ["email"] and got["email"].startswith(CANARY_PREFIX)


def test_every_supported_format() -> None:
    fmts = {"a": "character varying", "b": "integer", "c": "bigint", "d": "numeric", "e": "boolean",
            "f": "timestamp with time zone", "g": "date", "h": "jsonb", "i": "citext", "j": "real"}
    got = fill_required(tgt(list(fmts), fmts), OWNER, set())
    assert got is not None and list(got) == list(fmts)
    assert got["a"].startswith(CANARY_PREFIX) and got["i"].startswith(CANARY_PREFIX)
    assert (got["b"], got["c"], got["d"], got["e"], got["h"], got["j"]) == (0, 0, 0, False, {}, 0)
    assert datetime.fromisoformat(got["f"]).tzinfo is not None
    assert abs((date.fromisoformat(got["g"]) - datetime.now(UTC).date()).days) <= 1


def test_unfillable_type_means_no_row() -> None:
    t = tgt(["id", "status"], {"id": "uuid", "status": "public.order_status"})
    assert fill_required(t, OWNER, {"id"}) is None
    t2 = tgt(["id", "tags"], {"id": "uuid"})                    # required without a format
    assert fill_required(t2, OWNER, {"id"}) is None


def test_nothing_required_outside_preset() -> None:
    t = tgt(["id", "owner_id"], {"id": "uuid", "owner_id": "uuid"})
    assert fill_required(t, OWNER, {"id", "owner_id"}) == {}
    assert fill_required(tgt([], {}), OWNER, set()) == {}


def test_fresh_text_values() -> None:
    t = tgt(["x"], {"x": "text"})
    a, b = fill_required(t, OWNER, set()), fill_required(t, OWNER, set())
    assert a is not None and b is not None and a["x"] != b["x"]
