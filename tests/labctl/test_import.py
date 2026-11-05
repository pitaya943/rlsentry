"""labctl imports without fcntl (Windows) and only lock() needs it (MS2 approval note 5).
Contract: rlsentry/contracts/lab.py LabCtl.lock. No Docker needed."""
from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType

import pytest

import lab._shared.labctl as labctl_module


@pytest.fixture
def labctl_without_fcntl(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    # sys.modules[name] = None makes `import name` raise ImportError, as on Windows.
    monkeypatch.setitem(sys.modules, "fcntl", None)
    try:
        yield importlib.reload(labctl_module)
    finally:
        monkeypatch.undo()
        importlib.reload(labctl_module)


def test_module_imports_without_fcntl(labctl_without_fcntl: ModuleType) -> None:
    assert labctl_without_fcntl.write_command('UPDATE "public"."t" SET "a" = $1') == "UPDATE"


def test_lock_is_the_only_part_that_needs_fcntl(labctl_without_fcntl: ModuleType) -> None:
    with pytest.raises(ImportError), labctl_without_fcntl.lock():
        pass


def test_lock_still_works_where_fcntl_exists() -> None:
    with labctl_module.lock(), labctl_module.lock():   # re-entrant, as before
        pass
