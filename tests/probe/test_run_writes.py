"""probe/run.py write path (SPEC §5 M3 writes; FR-09; ADR-029), driven by a stateful fake
PostgREST so run.py can be exercised without the lab (the real run is tests/lab/test_scan_writes.py).

The fake models, per table, RLS as Python predicates: SELECT visibility, INSERT WITH CHECK,
UPDATE/DELETE USING and UPDATE WITH CHECK. A 2xx UPDATE/DELETE that USING filters to zero rows
leaves the row unchanged (the "2xx is not a write" case). It tracks every row so the test can
assert the scanner cleaned up every canary it created.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from rlsentry.contracts.models import Op, Outcome, Profile, Role, Target
from rlsentry.contracts.policy import ExpectedPolicy, RoleScopes, RowScope, TablePolicy
from rlsentry.contracts.probe import AUDIT_WRITE_REASON, CANARY_PREFIX, Sessions
from rlsentry.probe.run import probe
from tests.fakes import ANON, URL, Recorder, fake_jwt, run

A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TA, TB = fake_jwt(A), fake_jwt(B)
UID = {f"Bearer {TA}": A, f"Bearer {TB}": B}
SESS = Sessions(tokens={Role.ANON: ANON, Role.USER_A: TA, Role.USER_B: TB}, user_ids={Role.USER_A: A, Role.USER_B: B})

Pred = Callable[[str | None, str | None], bool]
OWN: Pred = lambda uid, owner: uid is not None and uid == owner
ANY: Pred = lambda uid, owner: True


@dataclass
class Table:
    """owner_col 'owner_id', text col 'body'. Predicates take (actor_uid, owner_being_checked)."""
    rows: dict[str, dict] = field(default_factory=dict)   # pk -> row dict
    select_vis: Pred = OWN          # SELECT USING
    insert_check: Pred = OWN        # INSERT WITH CHECK (owner = new owner)
    update_using: Pred = OWN        # UPDATE USING (current owner)
    update_check: Pred = OWN        # UPDATE WITH CHECK (new owner)
    delete_using: Pred = OWN        # DELETE USING


@dataclass
class FakeRest:
    tables: dict[str, Table]

    def __call__(self, r: httpx.Request) -> httpx.Response:
        uid = UID.get(r.headers.get("authorization", ""))
        name = r.url.path.removeprefix("/rest/v1/").removeprefix("rpc/")
        t = self.tables.get(name)
        if t is None:
            return httpx.Response(404)
        p = r.url.params
        if r.method == "POST":
            body = json.loads(r.content)
            if not t.insert_check(uid, body.get("owner_id")):
                return httpx.Response(403, json={"code": "42501"})
            t.rows[body["id"]] = dict(body)
            return httpx.Response(201, headers={"Content-Range": "*/1"})
        if r.method == "PATCH":
            body = json.loads(r.content)
            pk = p["id"].removeprefix("eq.")
            row = t.rows.get(pk)
            if row and t.update_using(uid, row.get("owner_id")):
                new = {**row, **body}
                if t.update_check(uid, new.get("owner_id")):
                    t.rows[pk] = new               # applied
            return httpx.Response(200, headers={"Content-Range": "*/0"})   # minimal: no body
        if r.method == "DELETE":
            pk = p["id"].removeprefix("eq.")
            row = t.rows.get(pk)
            if row and t.delete_using(uid, row.get("owner_id")):
                del t.rows[pk]
            return httpx.Response(200, headers={"Content-Range": "*/0"})
        # GET / HEAD: rows visible to uid, then eq / in filters
        rows = [x for pk, x in t.rows.items() if t.select_vis(uid, x.get("owner_id"))]
        rows = [x for x in rows if _match(x, p)]
        if r.method == "GET":
            return httpx.Response(200, json=[{"id": x["id"]} for x in rows])
        n = len(rows)
        return httpx.Response(200, headers={"Content-Range": f"*/{n}" if n == 0 else f"0-{n - 1}/{n}"})


def _match(row: dict, p: httpx.QueryParams) -> bool:
    for key in p:
        if key in ("select", "limit"):
            continue
        val = p[key]
        if val.startswith("eq."):
            if str(row.get(key)) != val[3:]:
                return False
        elif val.startswith("in.("):
            want = {v.strip('"') for v in val[4:-1].split(",")}
            if str(row.get(key)) not in want:
                return False
    return True


def tgt(name: str) -> Target:
    return Target(name=name, kind="table", columns=["id", "owner_id", "body"],
                  primary_key=["id"], discovered_by="openapi", confidence="confirmed")


def policy(*names: str) -> ExpectedPolicy:
    rs = RoleScopes(anon=RowScope.DENY, user=RowScope.OWN_ROWS_ONLY)
    return ExpectedPolicy(tables={n: TablePolicy(owner_column="owner_id",
                                                 select=rs, insert=rs, update=rs, delete=rs) for n in names})


def scan(fake: FakeRest, targets: list[Target], profile: Profile = Profile.DEV):
    rec = Recorder(fake)
    matrix, findings = run(lambda c: probe(c, URL, ANON, targets, SESS, policy(*[t.name for t in targets]), profile),
                           rec, profile)
    cells = {(c.target, c.role, c.op): c for c in matrix.cells}
    rules = {(f.target, f.role, f.op, f.rule) for f in findings}
    return cells, rules, findings, rec, fake


def canary_rows(fake: FakeRest) -> list[str]:
    return [pk for t in fake.tables.values() for pk, row in t.rows.items()
            if any(isinstance(v, str) and v.startswith(CANARY_PREFIX) for v in row.values())]


def test_vulnerable_table_writes_are_confirmed_and_cleaned_up() -> None:
    vuln = Table(select_vis=ANY, insert_check=ANY, update_using=ANY, update_check=ANY, delete_using=ANY)
    cells, rules, findings, _rec, fake = scan(FakeRest({"t": vuln}), [tgt("t")])
    # anon write → ANON_WRITE; user cross-tenant write → CROSS_TENANT_WRITE; all ALLOWED.
    assert cells[("t", Role.ANON, Op.INSERT)].outcome is Outcome.ALLOWED
    assert ("t", Role.ANON, Op.INSERT, "ANON_WRITE") in rules
    assert cells[("t", Role.USER_A, Op.UPDATE)].outcome is Outcome.ALLOWED
    assert ("t", Role.USER_A, Op.UPDATE, "CROSS_TENANT_WRITE") in rules
    assert cells[("t", Role.USER_B, Op.DELETE)].outcome is Outcome.ALLOWED
    # cleanup removed every canary; no CLEANUP_FAILED.
    assert canary_rows(fake) == []
    assert not any(f.rule == "CLEANUP_FAILED" for f in findings)


def test_safe_table_writes_denied_no_false_positive_and_cleaned_up() -> None:
    cells, rules, _findings, _rec, fake = scan(FakeRest({"t": Table()}), [tgt("t")])
    for role in (Role.ANON, Role.USER_A, Role.USER_B):
        for op in (Op.INSERT, Op.UPDATE, Op.DELETE):
            assert cells[("t", role, op)].outcome is not Outcome.ALLOWED
    assert not any(rule in ("ANON_WRITE", "CROSS_TENANT_WRITE") for (_t, _r, _o, rule) in rules)
    assert canary_rows(fake) == []


def test_audit_sends_no_write_and_marks_not_tested() -> None:
    cells, _rules, _f, rec, _fake = scan(FakeRest({"t": Table(select_vis=ANY)}), [tgt("t")], Profile.AUDIT)
    writes = [c for k, c in cells.items() if k[2] is not Op.SELECT]
    assert len(writes) == 9 and {c.outcome for c in writes} == {Outcome.NOT_TESTED}
    assert {c.reason for c in writes} == {AUDIT_WRITE_REASON}
    assert rec.methods() <= {"GET", "HEAD"}
