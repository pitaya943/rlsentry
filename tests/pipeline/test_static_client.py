"""ADR-020 #6 (a): SafeClient is constructed in exactly one place, rlsentry/pipeline.py, after
authorize(). Any other module building its own client could send requests without authorization."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "rlsentry"


def constructions() -> list[str]:
    found: list[str] = []
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                if name in ("SafeClient", "AsyncClient", "Client"):
                    found.append(f"{path.relative_to(PKG.parent).as_posix()}:{name}")
    return found


@pytest.mark.safety
def test_safeclient_is_built_only_in_the_pipeline() -> None:
    found = constructions()
    assert sorted({f for f in found if f.endswith(":SafeClient")}) == ["rlsentry/pipeline.py:SafeClient"]
    # the raw httpx client exists only inside the SafeClient implementation
    assert [f for f in found if not f.endswith(":SafeClient")] == ["rlsentry/safety/http.py:AsyncClient"]
