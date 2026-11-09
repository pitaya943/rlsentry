"""policy/init.py (FR-15 `rlsentry init`). Contract: rlsentry/contracts/policy.py draft_policy."""
import yaml

from rlsentry.contracts.models import Op, Role, Target
from rlsentry.contracts.policy import RowScope
from rlsentry.policy.init import draft_policy
from rlsentry.policy.load import load_config
from rlsentry.policy.resolve import resolve_expected


def t(name: str, cols: list[str], kind: str = "table", pk: list[str] | None = None) -> Target:
    return Target(name=name, kind=kind, columns=cols, primary_key=pk or [], discovered_by="openapi",
                  confidence="confirmed")


TARGETS = [t("posts", ["id", "author_id", "is_published", "body"], pk=["id"]),
           t("notes", ["id", "user_id", "text"], pk=["id"]),
           t("misc", ["id", "body"]), t("get_stats", [], kind="rpc"), t("flags", ["id", "is_public"])]


def scopes(text: str, name: str, op: Op) -> tuple[RowScope, RowScope]:
    cfg = load_config("target: http://127.0.0.1:54321\n" + text)
    return (resolve_expected(cfg.policy, name, op, Role.ANON).scope,
            resolve_expected(cfg.policy, name, op, Role.USER_A).scope)


def test_round_trips_through_load_config() -> None:
    text = draft_policy(TARGETS)
    cfg = load_config("target: http://127.0.0.1:54321\n" + text)
    assert list(cfg.tables) == ["flags", "get_stats", "misc", "notes", "posts"]
    assert cfg.tables["posts"].owner_column == "author_id" and cfg.tables["posts"].public_column == "is_published"
    assert cfg.tables["posts"].primary_key == ["id"] and cfg.tables["misc"].primary_key is None


def test_scopes() -> None:
    text = draft_policy(TARGETS)
    assert scopes(text, "posts", Op.SELECT) == (RowScope.PUBLIC_ROWS_ONLY, RowScope.PUBLIC_OR_OWN_ROWS)
    assert scopes(text, "notes", Op.SELECT) == (RowScope.DENY, RowScope.OWN_ROWS_ONLY)
    assert scopes(text, "flags", Op.SELECT) == (RowScope.PUBLIC_ROWS_ONLY, RowScope.PUBLIC_ROWS_ONLY)
    assert scopes(text, "misc", Op.SELECT) == (RowScope.DENY, RowScope.DENY)
    assert scopes(text, "notes", Op.UPDATE) == (RowScope.DENY, RowScope.OWN_ROWS_ONLY)
    assert scopes(text, "misc", Op.DELETE) == (RowScope.DENY, RowScope.DENY)


def test_rpc_select_only() -> None:
    entry = yaml.safe_load(draft_policy(TARGETS))["tables"]["get_stats"]
    assert entry == {"select": {"anon": "deny", "user": "deny"}}


def test_comment_for_tables_without_owner_column() -> None:
    lines = [ln for ln in draft_policy(TARGETS).splitlines() if ln.lstrip().startswith("#")]
    assert len(lines) >= 3   # misc, flags, get_stats have no owner column


def test_empty_deterministic_and_deduplicated() -> None:
    assert draft_policy([]) == "tables: {}\n"
    assert draft_policy(TARGETS) == draft_policy(list(reversed(TARGETS)))
    assert draft_policy(TARGETS + [t("notes", ["id"])]) == draft_policy(TARGETS)
