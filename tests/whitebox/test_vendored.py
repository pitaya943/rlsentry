"""The vendored splinter SQL is exactly the pinned release (SPEC §5 M4「固定版本」; ADR-032)."""
from __future__ import annotations

import hashlib
from importlib import resources

import pytest

from rlsentry.contracts.whitebox import SPLINTER_SHA256, SPLINTER_SQL_RESOURCE
from rlsentry.whitebox import splinter


def test_vendored_file_matches_pinned_hash() -> None:
    pkg, name = SPLINTER_SQL_RESOURCE
    data = resources.files(pkg).joinpath(name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == SPLINTER_SHA256


def test_load_returns_the_pinned_script() -> None:
    sql = splinter.load_splinter_sql()
    assert hashlib.sha256(sql.encode("utf-8")).hexdigest() == SPLINTER_SHA256
    assert "pgrst.db_schemas" in sql and "rls_disabled_in_public" in sql


def test_load_refuses_a_modified_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(splinter, "SPLINTER_SHA256", "0" * 64, raising=False)
    import rlsentry.contracts.whitebox as wc
    monkeypatch.setattr(wc, "SPLINTER_SHA256", "0" * 64)
    with pytest.raises(RuntimeError):
        splinter.load_splinter_sql()


def test_parse_lint_handles_text_and_structured_columns() -> None:
    row = {"name": "rls_disabled_in_public", "level": "ERROR", "categories": "{SECURITY}",
           "detail": "Table `public.customers` …", "cache_key": "k",
           "metadata": '{"name": "customers", "type": "table", "schema": "public"}'}
    a = splinter.parse_lint(row)
    b = splinter.parse_lint({**row, "categories": ["SECURITY"],
                             "metadata": {"name": "customers", "type": "table", "schema": "public"}})
    assert a == b
    assert (a.object_schema, a.object_name, a.object_type, a.categories) == \
        ("public", "customers", "table", ["SECURITY"])
    c = splinter.parse_lint({"name": "x", "level": "WARN", "categories": [], "metadata": None})
    assert c.object_name is None and c.detail == ""


def test_run_splinter_validates_schemas_before_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise AssertionError("must not connect")
    monkeypatch.setattr(splinter, "open_readonly", boom, raising=False)
    for bad in ((), ("public; drop table x",), ("public", "a'b")):
        with pytest.raises(ValueError):
            splinter.run_splinter("postgresql://127.0.0.1:1/x", bad)
