"""RLSentry: attacker-perspective authorization verification for Supabase (SPEC §1).

Python API (FR-16): `from rlsentry import run_scan` is exactly rlsentry.pipeline.run_scan, the
same entry point the CLI and the GitHub Action use. Imported lazily so that importing any
submodule (e.g. rlsentry.contracts) does not pull in the whole pipeline.
"""
from __future__ import annotations

from typing import Any

__all__ = ["run_init", "run_scan"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from rlsentry import pipeline
        return getattr(pipeline, name)
    raise AttributeError(f"module 'rlsentry' has no attribute {name!r}")
