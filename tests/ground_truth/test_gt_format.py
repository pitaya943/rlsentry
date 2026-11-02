"""Ground-truth format (T-012) and every lab/*/expected.yaml against it. SPEC §8, ADR-009."""
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from rlsentry.contracts.ground_truth import SCENARIO_IDS, GroundTruth, row_pk

LAB = Path(__file__).resolve().parents[2] / "lab"
FILES = sorted(LAB.glob("*/expected.yaml"))


def _minimal(**over: object) -> dict:
    gt: dict = {
        "scenario": "L04", "title": "t", "plant": "p",
        "schema": {"notes": {"kind": "table", "columns": ["id", "owner_id"], "primary_key": ["id"]}},
        "rows": {"note_a1": {"target": "notes", "pk": row_pk("L04", 1), "owner": "user_a"}},
        "policy": {"tables": {"notes": {"owner_column": "owner_id"}}},
        "vulnerable_cases": [{"id": "L04-V1", "target": "notes", "op": "select", "role": "user_b",
                              "rows": ["note_a1"], "expect": "allowed",
                              "rule": "CROSS_TENANT_READ", "severity": "medium"}],
        "safe_cases": [{"id": "L04-S1", "target": "notes", "op": "select", "role": "anon",
                        "rows": ["note_a1"], "expect": "denied"}],
    }
    gt.update(over)
    return gt


def test_minimal_ground_truth_is_valid() -> None:
    gt = GroundTruth.model_validate(_minimal())
    assert gt.vulnerable_cases[0].cell == ("access", "notes", "select", "user_b")
    assert gt.splinter_expected == "measure"


@pytest.mark.parametrize("over", [
    {"scenario": "L13"},
    {"safe_cases": [{"id": "L04-S1", "target": "notes", "op": "select", "role": "user_b",
                     "rows": ["note_a1"], "expect": "denied"}]},                    # cell clash
    {"safe_cases": [{"id": "L04-S1", "target": "nope", "op": "select", "role": "anon",
                     "rows": [], "expect": "denied"}]},                             # unknown target
    {"safe_cases": [{"id": "L04-S1", "target": "notes", "op": "select", "role": "anon",
                     "rows": ["ghost"], "expect": "denied"}]},                      # unknown row
    {"safe_cases": [{"id": "L04-S1", "target": "notes", "op": "update", "role": "anon",
                     "rows": ["note_a1"], "expect": "denied"}]},                    # write in audit
    {"vulnerable_cases": [{"id": "L04-V1", "target": "notes", "op": "select", "role": "user_b",
                           "rows": ["note_a1"], "expect": "allowed", "rule": "INCONCLUSIVE_CELL",
                           "severity": "review"}]},                                 # not a vuln rule
    {"rows": {"note_a1": {"target": "notes", "pk": "1", "owner": "user_a"}}},       # pk format
    {"inconclusive_cases": [{"id": "X-I1", "target": "notes", "op": "select", "role": "user_a",
                             "expect": "inconclusive"}]},                           # id prefix
    {"warning_cases": [{"id": "L04-W1", "target": "notes", "op": "select", "role": "anon",
                        "expect": "allowed", "rule": "SENSITIVE_COLUMN_PUBLIC",
                        "severity": "review"}]},                                    # confirmed warning
    {"surprise": 1},
])
def test_structural_errors_are_rejected(over: dict) -> None:
    with pytest.raises(ValidationError):
        GroundTruth.model_validate(_minimal(**over))


def test_key_cases_have_no_cell_fields() -> None:
    ok = {"id": "L04-V2", "kind": "key", "target": "jwt:service_role", "key_kind": "secret",
          "rule": "SECRET_KEY_IN_BUNDLE", "severity": "critical"}
    GroundTruth.model_validate(_minimal(vulnerable_cases=_minimal()["vulnerable_cases"] + [ok]))
    with pytest.raises(ValidationError):
        GroundTruth.model_validate(_minimal(vulnerable_cases=[{**ok, "role": "anon"}]))
    with pytest.raises(ValidationError):
        GroundTruth.model_validate(_minimal(vulnerable_cases=[{**ok, "target": "notes"}]))


def test_row_pk_format() -> None:
    assert row_pk("L04", 1) == "5ce01004-0000-4000-8000-000000000001"
    assert row_pk("C02", 12) == "5ce0c002-0000-4000-8000-000000000012"
    assert len(SCENARIO_IDS) == 16


@pytest.mark.parametrize("path", FILES, ids=[p.parent.name for p in FILES])
def test_lab_expected_yaml_is_valid(path: Path) -> None:
    gt = GroundTruth.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert path.parent.name.startswith(gt.scenario + "_")
    pks = [r.pk for r in gt.rows.values()]
    assert len(pks) == len(set(pks))


def test_bench_report_has_spec_section_9_keys() -> None:
    from rlsentry.contracts.ground_truth import BenchReport
    keys = set(BenchReport.model_fields)
    assert {"tp", "fp", "fn", "tn", "recall", "precision", "fpr", "coverage", "runtime", "scenarios"} <= keys
    assert {"fp_safe", "safe_decided_ratio", "inconclusive_ratio"} <= keys
