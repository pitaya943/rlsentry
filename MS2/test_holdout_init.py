"""MS2 holdout: FR-15 draft policy, candidate priority and round trip."""
from rlsentry.contracts.models import Op, Role, Target
from rlsentry.contracts.policy import RowScope
from rlsentry.policy.init import draft_policy
from rlsentry.policy.load import load_config
from rlsentry.policy.resolve import resolve_expected


def test_candidate_priority_and_round_trip() -> None:
    t = Target(name="docs", kind="table", columns=["created_by", "owner_id", "user_id", "is_published", "is_public"],
               primary_key=["doc_id"], discovered_by="openapi", confidence="confirmed")
    cfg = load_config("target: https://example.invalid\n" + draft_policy([t]))
    tp = cfg.tables["docs"]
    assert (tp.owner_column, tp.public_column, tp.primary_key) == ("user_id", "is_public", ["doc_id"])
    assert resolve_expected(cfg.policy, "docs", Op.INSERT, Role.USER_B).scope is RowScope.OWN_ROWS_ONLY
    assert resolve_expected(cfg.policy, "docs", Op.SELECT, Role.ANON).scope is RowScope.PUBLIC_ROWS_ONLY
