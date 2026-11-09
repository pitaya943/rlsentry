"""All 16 SPEC §8 scenarios have ground truth with the expected shape (T-024)."""
from pathlib import Path

import yaml

from rlsentry.contracts.ground_truth import SCENARIO_IDS, CaseKind, GroundTruth

LAB = Path(__file__).resolve().parents[2] / "lab"


def _all() -> dict[str, GroundTruth]:
    out = {}
    for p in sorted(LAB.glob("*/expected.yaml")):
        g = GroundTruth.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        out[g.scenario] = g
    return out


def test_every_scenario_exactly_once() -> None:
    dirs = sorted(p.parent.name.split("_")[0] for p in LAB.glob("*/expected.yaml"))
    assert dirs == sorted(SCENARIO_IDS)


def test_vulnerable_scenarios_plant_something_and_controls_plant_nothing() -> None:
    g = _all()
    for sid in SCENARIO_IDS:
        if sid.startswith("C"):
            assert not g[sid].vulnerable_cases and g[sid].safe_cases, sid
        elif sid != "L10":                       # L10 only yields a sensitive-column hint
            assert g[sid].vulnerable_cases, sid
    assert [c.rule for c in g["L10"].warning_cases] == ["SENSITIVE_COLUMN_PUBLIC"]


def test_spec_section_8_specifics() -> None:
    g = _all()
    assert {c.rule for c in g["L07"].vulnerable_cases} == {"SECURITY_DEFINER_RPC_DATA"}
    assert [c.rule for c in g["L07"].warning_cases] == ["SECURITY_DEFINER_EXECUTABLE"]
    assert [(c.kind, c.key_kind) for c in g["L08"].vulnerable_cases] == [(CaseKind.KEY, "secret")]
    assert any(c.kind is CaseKind.KEY and c.key_kind == "publishable" for c in g["L08"].safe_cases)
    assert g["L11"].priority == "P2"
    assert not g["L12"].openapi
    assert ("diary_entries", "inferred") in {(d.target, d.confidence) for d in g["L12"].discovery_cases}
    assert g["C03"].inconclusive_cases and g["C04"].inconclusive_cases   # SPEC §8 C01–C04 row
    assert all(x.splinter_expected != "measure" for x in g.values())     # measured at MS4 (ADR-035)


def test_p0_case_counts() -> None:
    g = [x for x in _all().values() if x.priority == "P0"]
    vuln = sum(len(x.vulnerable_cases) for x in g)
    safe = sum(len(x.safe_cases) for x in g)
    # With n cases one miss moves recall by 1/n; ≥ 20 keeps one miss under the 5 % budget.
    assert vuln >= 20 and safe >= 20, (vuln, safe)
