"""probe.run.pick_text_column (ADR-034 補記): the marker column must be a text column when types
are known (L05: created_by is uuid, name is text). Pure."""
from __future__ import annotations

from rlsentry.contracts.models import Target
from rlsentry.probe.run import pick_text_column


def tgt(cols: list[str], formats: dict[str, str] | None = None) -> Target:
    return Target(name="t", kind="table", columns=cols, primary_key=["id"], column_formats=formats or {},
                  discovered_by="openapi", confidence="confirmed")


def test_l05_skips_uuid_column() -> None:
    t = tgt(["id", "owner_id", "created_by", "name"],
            {"id": "uuid", "owner_id": "uuid", "created_by": "uuid", "name": "text"})
    assert pick_text_column(t, "owner_id", None) == "name"


def test_without_types_keeps_ms3_behaviour() -> None:
    assert pick_text_column(tgt(["id", "owner_id", "created_by", "name"]), "owner_id", None) == "created_by"


def test_skips_public_and_non_text_and_accepts_varchar() -> None:
    t = tgt(["id", "is_public", "n", "title"], {"n": "integer", "title": "character varying"})
    assert pick_text_column(t, None, "is_public") == "title"


def test_untyped_column_is_eligible_when_others_are_typed() -> None:
    t = tgt(["id", "owner_id", "count", "memo"], {"count": "bigint"})
    assert pick_text_column(t, "owner_id", None) == "memo"


def test_none_when_no_text_column() -> None:
    t = tgt(["id", "owner_id", "amount", "at"], {"amount": "numeric", "at": "timestamp with time zone"})
    assert pick_text_column(t, "owner_id", None) is None
    assert pick_text_column(tgt(["id", "owner_id"]), "owner_id", None) is None
