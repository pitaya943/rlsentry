"""Shared builders for the pure bench tests (no lab needed)."""
from __future__ import annotations

from pathlib import Path

import yaml

from rlsentry.contracts.ground_truth import GroundTruth
from rlsentry.contracts.models import (
    AccessMatrix,
    Evidence,
    Finding,
    Op,
    Outcome,
    ProbeResult,
    Role,
    finding_id,
)
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.whitebox import Lint

LAB = Path(__file__).resolve().parents[2] / "lab"


def gt(sid: str, **update: object) -> GroundTruth:
    (path,) = sorted(LAB.glob(f"{sid}_*/expected.yaml"))
    data = yaml.safe_load(path.read_text("utf-8"))
    data.update(update)
    return GroundTruth.model_validate(data)


def cell(target: str, role: Role, op: Op, outcome: Outcome) -> ProbeResult:
    return ProbeResult(target=target, role=role, op=op, outcome=outcome, known_rows_checked=1, reason="r",
                       evidence_curl="curl -I http://127.0.0.1:54321/rest/v1/t")


def matrix(*cells: ProbeResult) -> AccessMatrix:
    return AccessMatrix(cells=list(cells))


def fnd(target: str | None, role: Role | None, op: Op | None, rule: str,
        evidence: Evidence | None = None, correlation: str | None = None) -> Finding:
    spec = RULES[rule]
    return Finding(id=finding_id(target, role, op, rule), rule=rule, evidence=evidence or spec.evidence,
                   severity=spec.severity, target=target, role=role, op=op, correlation=correlation)


def lint(name: str, obj: str | None, cat: str = "SECURITY") -> Lint:
    return Lint(name=name, level="ERROR", categories=[cat], object_schema="public", object_name=obj)
