"""Lab L03 against lab/L03_*/expected.yaml (ADR-018). Needs Docker; see tests/lab/conftest.py."""
import pytest

from tests.lab.oracle import Scenario, case_ids

SID = "L03"


def test_schema(scenario: Scenario) -> None:
    scenario.check_schema()


def test_rows(scenario: Scenario) -> None:
    scenario.check_rows()


def test_discovery(scenario: Scenario) -> None:
    scenario.check_discovery()


@pytest.mark.parametrize("case_id", case_ids(SID))
def test_case(scenario: Scenario, case_id: str) -> None:
    scenario.check_case(case_id)
