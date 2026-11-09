"""MS4 approval note 5 (c): splinter_status uses the configured exposed schemas, not "public"."""
from __future__ import annotations

from rlsentry.bench.score import score_scenario, splinter_status
from rlsentry.contracts.models import AccessMatrix, Profile
from rlsentry.contracts.whitebox import Lint
from tests.bench.helpers import gt

L01 = gt("L01")          # planted flaw on public.customers


def lint(schema: str) -> Lint:
    return Lint(name="rls_disabled_in_public", level="ERROR", categories=["SECURITY"],
                object_schema=schema, object_name="customers")


def test_lint_in_a_configured_non_public_schema_counts() -> None:
    assert splinter_status(L01, [lint("api")], ("api",)) == "reported"
    assert splinter_status(L01, [lint("api")], ("public",)) == "not_reported"
    assert splinter_status(L01, [lint("public")], ("api", "public")) == "reported"


def test_default_is_public() -> None:
    assert splinter_status(L01, [lint("public")]) == "reported"
    assert splinter_status(L01, [lint("api")]) == "not_reported"


def test_score_scenario_passes_the_schemas_through() -> None:
    res = score_scenario(L01, Profile.DEV, AccessMatrix(), [], 0.0, lints=[lint("api")], db_schemas=("api",))
    assert res.splinter == "reported"
    res2 = score_scenario(L01, Profile.DEV, AccessMatrix(), [], 0.0, lints=[lint("api")])
    assert res2.splinter == "not_reported"
