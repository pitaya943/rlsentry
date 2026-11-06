"""action/action.yml: the GitHub Action (FR-13; ADR-044). Contract: rlsentry/contracts/report.py
ACTION_* and its docstring. Static checks only: the action runs on GitHub, not here."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from rlsentry.contracts.report import ACTION_INPUTS, ACTION_PATH

ROOT = Path(__file__).resolve().parents[2]


def action() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / ACTION_PATH).read_text("utf-8"))
    assert isinstance(data, dict)
    return data


def steps() -> list[dict[str, Any]]:
    runs = action()["runs"]
    assert runs["using"] == "composite"
    return list(runs["steps"])


def test_inputs_and_defaults() -> None:
    inputs = action()["inputs"]
    assert set(inputs) == set(ACTION_INPUTS)
    for name, default in ACTION_INPUTS.items():
        assert str(inputs[name].get("default", "")) == (default or ""), name
        assert inputs[name].get("description")
    assert action().get("name") and action().get("description")


def test_inputs_never_interpolated_into_shell_scripts() -> None:
    for s in steps():
        if "run" in s:
            assert "${{" not in s["run"], f"script injection risk in: {s['run']!r}"
            assert s.get("shell") == "bash"


def test_scan_step_runs_rlsentry_scan_with_profile_and_sarif() -> None:
    scan = [s for s in steps() if "run" in s and "rlsentry scan" in s["run"]]
    assert len(scan) == 1
    run, env = scan[0]["run"], scan[0].get("env", {})
    assert "--profile" in run and "--config" in run and "--out" in run and "--format json,sarif" in run
    assert "--i-own-this-target" not in run                 # authorization lives in the config
    for name in ("config", "profile", "out", "supabase-url"):
        assert any(f"inputs.{name}" in str(v) for v in env.values()), name


def test_installs_python_and_the_package_from_the_action_path() -> None:
    uses = [s.get("uses", "") for s in steps()]
    assert any(u.startswith("actions/setup-python@") for u in uses)
    setup = next(s for s in steps() if s.get("uses", "").startswith("actions/setup-python@"))
    assert str(setup["with"]["python-version"]) == "3.12"
    install = [s for s in steps() if "run" in s and "pip install" in s["run"]]
    assert install and "GITHUB_ACTION_PATH" in install[0]["run"]


def test_sarif_upload_runs_even_when_the_scan_fails() -> None:
    up = [s for s in steps() if s.get("uses", "").startswith("github/codeql-action/upload-sarif@")]
    assert len(up) == 1
    cond = str(up[0].get("if", ""))
    assert "always()" in cond and "inputs.upload-sarif" in cond
    assert re.search(r"rlsentry-report\.sarif", str(up[0]["with"]["sarif_file"]))
