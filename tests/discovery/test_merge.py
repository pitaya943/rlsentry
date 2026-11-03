"""discovery/merge.py. Contract: rlsentry/contracts/discovery.py (merge_targets); ADR-023 #2."""
from rlsentry.contracts.models import Target
from rlsentry.contracts.policy import ExpectedPolicy, TablePolicy
from rlsentry.discovery.merge import merge_targets


def oa(name: str, kind: str = "table", pk: list[str] | None = None) -> Target:
    return Target(name=name, kind=kind, columns=["id"] if kind == "table" else [], primary_key=pk or [],
                  discovered_by="openapi", confidence="confirmed")


def bd(name: str, kind: str = "table") -> Target:
    return Target(name=name, kind=kind, discovered_by="bundle", confidence="inferred")


def pol(**tables: TablePolicy) -> ExpectedPolicy:
    return ExpectedPolicy(tables=tables)


def test_openapi_unavailable_l12_shape() -> None:
    got = merge_targets(None, [bd("diary_entries")],
                        pol(diary_entries=TablePolicy(primary_key=["id"]), audit_log=TablePolicy(primary_key=["id"])))
    assert got == [
        Target(name="audit_log", kind="table", primary_key=["id"], discovered_by="policy", confidence="unknown"),
        Target(name="diary_entries", kind="table", primary_key=["id"], discovered_by="bundle", confidence="inferred"),
    ]


def test_bundle_names_missing_from_openapi_are_added() -> None:
    got = merge_targets([oa("notes", pk=["id"])], [bd("notes"), bd("private_only")], pol())
    assert [(x.name, x.confidence) for x in got] == [("notes", "confirmed"), ("private_only", "inferred")]


def test_openapi_primary_key_wins_policy_fills_rpc() -> None:
    got = merge_targets([oa("t", pk=["id"]), oa("get_all", "rpc")], [],
                        pol(t=TablePolicy(primary_key=["other"]), get_all=TablePolicy(primary_key=["id"])))
    assert {x.name: x.primary_key for x in got} == {"get_all": ["id"], "t": ["id"]}


def test_policy_table_found_elsewhere_is_not_duplicated() -> None:
    got = merge_targets([oa("a")], [bd("b")], pol(a=TablePolicy(), b=TablePolicy()))
    assert [(x.name, x.discovered_by) for x in got] == [("a", "openapi"), ("b", "bundle")]


def test_same_name_table_and_rpc_both_kept_and_sorted() -> None:
    got = merge_targets([oa("z"), oa("x", "rpc")], [bd("x")], pol())
    assert [(x.name, x.kind) for x in got] == [("x", "rpc"), ("z", "table")]


def test_inputs_not_mutated() -> None:
    o, b = [oa("t")], [bd("u")]
    merge_targets(o, b, pol(t=TablePolicy(primary_key=["id"]), u=TablePolicy(primary_key=["id"])))
    assert o == [oa("t")] and b == [bd("u")]
