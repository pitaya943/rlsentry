"""parse_openapi: required columns and column formats (ADR-034; MS3 approval note 1). Pure.
Shapes taken from the lab's real PostgREST document (L05 projects)."""
from __future__ import annotations

from typing import Any

from rlsentry.discovery.openapi import parse_openapi

PK = {"format": "uuid", "type": "string", "description": "Note:\nThis is a Primary Key.<pk/>"}


def doc(definition: Any) -> dict[str, Any]:
    return {"swagger": "2.0", "paths": {"/": {}, "/projects": {"get": {}}, "/rpc/fn": {"get": {}}},
            "definitions": {"projects": definition}}


L05 = {"required": ["id", "owner_id", "created_by", "name"],
       "properties": {"id": PK, "owner_id": {"format": "uuid", "type": "string"},
                      "created_by": {"format": "uuid", "type": "string"},
                      "name": {"format": "text", "type": "string"},
                      "note": {"format": "text", "type": "string"},
                      "n": {"format": "integer", "type": "integer"}},
       "type": "object"}


def projects(d: dict[str, Any]) -> Any:
    return next(t for t in parse_openapi(d) if t.name == "projects")


def test_required_and_formats_from_lab_shape() -> None:
    t = projects(doc(L05))
    assert t.required == ["id", "owner_id", "created_by", "name"]
    assert t.column_formats == {"id": "uuid", "owner_id": "uuid", "created_by": "uuid", "name": "text",
                                "note": "text", "n": "integer"}
    assert t.primary_key == ["id"] and t.columns == ["id", "owner_id", "created_by", "name", "note", "n"]


def test_required_keeps_only_known_string_columns() -> None:
    t = projects(doc({**L05, "required": ["name", "ghost", 3, "id"]}))
    assert t.required == ["name", "id"]


def test_odd_values_are_ignored_not_raised() -> None:
    t = projects(doc({"required": "id", "properties": {"id": {"format": 7}, "x": "junk", "y": {}}}))
    assert t.required == [] and t.column_formats == {}
    assert t.columns == ["id", "x", "y"]


def test_rpc_has_no_types() -> None:
    fn = next(t for t in parse_openapi(doc(L05)) if t.name == "fn")
    assert fn.kind == "rpc" and fn.required == [] and fn.column_formats == {}
