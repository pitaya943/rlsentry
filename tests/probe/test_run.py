"""probe/run.py: the read part of the Probe stage (MS2). Contract: rlsentry/contracts/probe.py probe().

A small fake PostgREST (owner filters, `in.()` counts, RLS as a Python predicate) stands in for
the lab; the real lab run is tests/probe/test_lab_reads.py.
"""
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from rlsentry.contracts.models import Op, Outcome, Profile, Role, Target
from rlsentry.contracts.policy import ExpectedPolicy, RoleScopes, RowScope, TablePolicy
from rlsentry.contracts.probe import AUDIT_WRITE_REASON, Sessions
from rlsentry.probe.run import probe
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TA, TB = fake_jwt(A), fake_jwt(B)
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: TA, Role.USER_B: TB}, user_ids={Role.USER_A: A, Role.USER_B: B})
Row = tuple[str, str | None]   # (pk, owner id)
OWN: Callable[[str | None, Row], bool] = lambda uid, r: uid is not None and r[1] == uid
ALL: Callable[[str | None, Row], bool] = lambda uid, r: True
NONE: Callable[[str | None, Row], bool] = lambda uid, r: False


@dataclass
class Rel:
    rows: list[Row]
    rls: Callable[[str | None, Row], bool] = OWN
    anon_rls: Callable[[str | None, Row], bool] = NONE


@dataclass
class FakeRest:
    rels: dict[str, Rel] = field(default_factory=dict)

    def __call__(self, r: httpx.Request) -> httpx.Response:
        assert r.method in ("GET", "HEAD"), r.method
        uid = {f"Bearer {TA}": A, f"Bearer {TB}": B}.get(r.headers["authorization"])
        name = r.url.path.removeprefix("/rest/v1/").removeprefix("rpc/")
        rel = self.rels.get(name)
        if rel is None:
            return httpx.Response(404)
        see = rel.rls if uid else rel.anon_rls
        rows = [x for x in rel.rows if see(uid, x)]
        p = r.url.params
        if "owner_id" in p:
            rows = [x for x in rows if p["owner_id"] == f"eq.{x[1]}"]
        if r.method == "GET":
            return httpx.Response(200, json=[{"id": x[0]} for x in rows])
        want = {v.strip('"') for v in p["id"].removeprefix("in.(").removesuffix(")").split(",")}
        n = len([x for x in rows if x[0] in want])
        return httpx.Response(200, headers={"Content-Range": f"*/{n}" if n == 0 else f"0-{n - 1}/{n}"})


def todos(name: str = "todos", kind: str = "table", conf: str = "confirmed") -> Target:
    return Target(name=name, kind=kind, columns=["id", "owner_id", "title"] if kind == "table" else [],
                  primary_key=["id"], discovered_by="openapi" if conf == "confirmed" else "bundle", confidence=conf)


POLICY = ExpectedPolicy(tables={n: TablePolicy(owner_column="owner_id", select=RoleScopes(
    anon=RowScope.DENY, user=RowScope.OWN_ROWS_ONLY)) for n in ("todos", "get_all")})
TWO: list[Row] = [("a1", A), ("b1", B)]


def scan(rest: FakeRest, targets: list[Target], sess: Sessions = SESS, profile: Profile = Profile.AUDIT,
         policy: ExpectedPolicy = POLICY) -> tuple[dict[tuple[str, Role, Op], tuple[Outcome, int, str]],
                                                  list[tuple[str | None, Role | None, str]], Recorder]:
    rec = Recorder(rest)
    matrix, findings = run(lambda c: probe(c, URL, ANON, targets, sess, policy, profile), rec, profile)
    cells = {(c.target, c.role, c.op): (c.outcome, c.known_rows_checked, c.reason) for c in matrix.cells}
    return cells, [(f.target, f.role, f.rule) for f in findings], rec


def sel(cells: dict[tuple[str, Role, Op], tuple[Outcome, int, str]], t: str = "todos") -> list[tuple[Outcome, int]]:
    return [cells[(t, r, Op.SELECT)][:2] for r in (Role.ANON, Role.USER_A, Role.USER_B)]


def test_correct_rls_is_denied_everywhere() -> None:
    cells, findings, rec = scan(FakeRest({"todos": Rel(TWO)}), [todos()])
    assert sel(cells) == [(Outcome.DENIED, 2), (Outcome.DENIED, 1), (Outcome.DENIED, 1)]
    assert findings == [] and rec.methods() == {"GET", "HEAD"}


def test_cross_tenant_leak_is_found() -> None:
    cells, findings, _ = scan(FakeRest({"todos": Rel(TWO, rls=ALL)}), [todos()])
    assert sel(cells) == [(Outcome.DENIED, 2), (Outcome.ALLOWED, 1), (Outcome.ALLOWED, 1)]
    assert findings == [("todos", Role.USER_A, "CROSS_TENANT_READ"), ("todos", Role.USER_B, "CROSS_TENANT_READ")]


def test_user_without_data_makes_the_other_inconclusive() -> None:
    cells, findings, _ = scan(FakeRest({"todos": Rel([("a1", A)])}), [todos()])
    assert sel(cells) == [(Outcome.DENIED, 1), (Outcome.INCONCLUSIVE, 0), (Outcome.DENIED, 1)]
    assert findings == [("todos", Role.USER_A, "INCONCLUSIVE_CELL")]


def test_missing_session_is_not_tested_and_never_denied() -> None:
    s = Sessions(tokens={Role.ANON: ANON, Role.USER_A: TA}, user_ids={Role.USER_A: A},
                 missing={Role.USER_B: "RLS_B_PW is not set"})
    cells, _, _ = scan(FakeRest({"todos": Rel(TWO)}), [todos()], sess=s)
    assert cells[("todos", Role.USER_B, Op.SELECT)] == (Outcome.NOT_TESTED, 0, "RLS_B_PW is not set")
    assert cells[("todos", Role.USER_A, Op.SELECT)][0] is Outcome.INCONCLUSIVE


def test_audit_write_cells_not_tested_and_only_reads_sent() -> None:
    # audit is read-only in every milestone (NFR-01); dev/ci write probing is covered by
    # tests/probe/test_run_writes.py (fast fake) and tests/lab/test_scan_writes.py (MS3).
    cells, _, rec = scan(FakeRest({"todos": Rel(TWO)}), [todos()], profile=Profile.AUDIT)
    writes = [v for k, v in cells.items() if k[2] is not Op.SELECT]
    assert len(writes) == 9 and set(writes) == {(Outcome.NOT_TESTED, 0, AUDIT_WRITE_REASON)}
    assert rec.methods() <= {"GET", "HEAD"}


def test_table_without_owner_column_is_review_not_vulnerable() -> None:
    t = Target(name="misc", kind="table", columns=["id", "body"], primary_key=["id"],
               discovered_by="openapi", confidence="confirmed")
    cells, findings, rec = scan(FakeRest({"misc": Rel([("m1", A)], rls=ALL, anon_rls=ALL)}), [t])
    assert [o for o, _ in sel(cells, "misc")] == [Outcome.INCONCLUSIVE] * 3
    assert findings == [("misc", Role.ANON, "INCONCLUSIVE_CELL"), ("misc", Role.USER_A, "NO_OWNER_COLUMN"),
                        ("misc", Role.USER_B, "NO_OWNER_COLUMN")]
    assert "HEAD" not in rec.methods()


def test_inferred_rpc_leak() -> None:
    rest = FakeRest({"get_all": Rel(TWO, rls=ALL, anon_rls=ALL)})
    cells, findings, _ = scan(rest, [todos("get_all", "rpc", "inferred")])
    assert sel(cells, "get_all") == [(Outcome.ALLOWED, 2), (Outcome.ALLOWED, 1), (Outcome.ALLOWED, 1)]
    assert findings == [("get_all", r, "SECURITY_DEFINER_RPC_DATA") for r in (Role.ANON, Role.USER_A, Role.USER_B)] \
        + [("get_all", None, "INFERRED_TARGET")]


def test_cell_order() -> None:
    rest = FakeRest({"todos": Rel(TWO), "get_all": Rel(TWO)})
    rec = Recorder(rest)
    matrix, _ = run(lambda c: probe(c, URL, ANON, [todos(), todos("get_all", "rpc")], SESS, POLICY, Profile.AUDIT), rec)
    keys = [(c.target, c.role, c.op) for c in matrix.cells]
    assert len(keys) == 24 and keys[:3] == [("todos", r, Op.SELECT) for r in (Role.ANON, Role.USER_A, Role.USER_B)]
    assert keys[3] == ("todos", Role.ANON, Op.INSERT) and keys[12][0] == "get_all"
