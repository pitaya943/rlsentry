"""The scanner must never see ground truth (ADR-014; auditor finding O2)."""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "rlsentry"


def test_only_bench_imports_ground_truth() -> None:
    offenders = []
    for py in PKG.rglob("*.py"):
        rel = py.relative_to(PKG).parts
        if rel[0] in ("bench", "contracts"):
            continue
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or "", *(a.name for a in node.names)] if isinstance(node, ast.ImportFrom) else []
            if any(n.endswith("ground_truth") for n in names):
                offenders.append(str(py.relative_to(PKG)))
    assert offenders == []
