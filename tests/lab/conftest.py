"""Fixtures for lab verification tests (ADR-018).

These tests need Docker and the local Supabase lab; they fail (never skip) when it is missing,
because a lab that cannot be checked must not look verified. Start Docker first (CLAUDE.md).
One pytest process holds the lab lock for its whole session, so parallel runs serialize.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from lab._shared import labctl
from rlsentry.contracts.lab import LabInfo
from tests.lab.oracle import Scenario


@pytest.fixture(scope="session")
def lab_info() -> Iterator[LabInfo]:
    with labctl.lock():
        yield labctl.ensure_up()


@pytest.fixture(scope="module")
def scenario(lab_info: LabInfo, request: pytest.FixtureRequest) -> Scenario:
    """The scenario named by the test module's SID, freshly applied."""
    return Scenario.load(lab_info, request.module.SID)
