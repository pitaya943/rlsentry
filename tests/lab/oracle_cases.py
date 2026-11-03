"""Case evaluation for the lab oracle (ADR-018). See rlsentry.contracts.ground_truth.Case.

- select with rows: allowed ⇔ the role gets back every listed pk; denied ⇔ none of them, while
  service_role confirms they exist. RPCs are called with GET (lab convention).
- insert/update/delete: performed with `Prefer: return=minimal`, judged by reading the final
  state with service_role (did the canary appear / the column change / the row vanish). Any
  change re-applies the scenario afterwards.
- inconclusive: no row that the policy forbids for the role is knowable — every such row is
  invisible to anon, user_a and user_b alike (or none exists); RPCs return no seeded pk.
- storage (P2): HEAD only, public and authenticated object URLs.
- key: a JWT with that role claim is in the frontend and equals the lab's key of that role.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from lab._shared import labctl
from rlsentry.contracts.ground_truth import Case, CaseKind
from rlsentry.contracts.lab import POSTGREST_ROLES
from rlsentry.contracts.models import Op, Outcome, Role
from rlsentry.policy.resolve import resolve_expected
from rlsentry.policy.visibility import row_permitted
from tests.lab.oracle import ROLES, Scenario, user_id

CANARY = "rlsentry-canary"


def check_case(sc: Scenario, c: Case) -> None:
    if c.kind is CaseKind.KEY:
        return _key(sc, c)
    if c.kind is CaseKind.STORAGE:
        return _storage(sc, c)
    if c.expect is Outcome.INCONCLUSIVE:
        return _inconclusive(sc, c)
    if c.precondition:
        _precondition(sc, c)
    run = {Op.SELECT: _select, Op.INSERT: _insert, Op.UPDATE: _update, Op.DELETE: _delete}
    assert c.op in run, c.id
    try:
        run[c.op](sc, c)
    finally:
        if c.precondition:
            sc.reapply()


# --- reads --------------------------------------------------------------------------------

def _pks(sc: Scenario, c: Case) -> list[str]:
    assert c.rows, f"{c.id}: case needs rows"
    return [sc.gt.rows[r].pk for r in c.rows]


def _select(sc: Scenario, c: Case) -> None:
    assert c.target and c.role
    pks = _pks(sc, c)
    seen = sc.visible(c.role, c.target, pks)
    if c.expect is Outcome.ALLOWED:
        assert seen == set(pks), f"{c.id}: {c.role.value} sees {len(seen)}/{len(pks)} rows, expected all"
    else:
        assert seen == set(), f"{c.id}: {c.role.value} sees {len(seen)} rows, expected none"
        base = {sc.gt.rows[r].target for r in c.rows}
        exists = set().union(*(sc.visible(None, b, pks) for b in base))
        assert exists == set(pks), f"{c.id}: denied rows must exist (service_role sees {len(exists)})"


def _inconclusive(sc: Scenario, c: Case) -> None:
    assert c.target and c.role and c.op is Op.SELECT
    e = sc.entry(c.target)
    seeded = {r.pk for r in sc.gt.rows.values()}
    if e.kind == "rpc":
        r = sc.http.get(sc.path(c.target), headers=sc.headers(c.role))
        assert r.status_code == 200, f"{c.id}: rpc not callable (HTTP {r.status_code})"
        assert not any(pk in r.text for pk in seeded), f"{c.id}: rpc returns a seeded row"
        return
    table = e.base or c.target
    pk, oc, pc = sc.pk_col(table), sc.owner_col(table), sc.public_col(table)
    rows = sc.all_rows(table)
    cols = tuple(rows[0]) if rows else ()
    want = resolve_expected(sc.gt.policy, c.target, Op.SELECT, c.role, cols)
    forbidden = [str(r[pk]) for r in rows
                 if not row_permitted(want.scope, user_id(c.role), r.get(oc) if oc else None,
                                      bool(r.get(pc)) if pc else False)]
    if not forbidden:
        return
    for who in ROLES:
        assert sc.visible(who, c.target, forbidden) == set(), \
            f"{c.id}: a row forbidden to {c.role.value} is visible to {who.value}"


def _precondition(sc: Scenario, c: Case) -> None:
    assert c.precondition == "user_metadata.role=admin" and c.role in (Role.USER_A, Role.USER_B), c.id
    r = sc.http.put("/auth/v1/user", headers=sc.headers(c.role), json={"data": {"role": "admin"}})
    assert r.status_code == 200, f"{c.id}: user_metadata update HTTP {r.status_code}"
    sc.tokens[c.role] = sc.login(c.role)       # new JWT carries the new user_metadata


# --- writes -------------------------------------------------------------------------------

def _columns(table: str) -> list[tuple[str, str]]:
    return [(n, t) for n, t in labctl.query(
        "select column_name, data_type from information_schema.columns where table_schema = 'public' "
        f"and table_name = '{table}' order by ordinal_position")]


def _base(sc: Scenario, target: str) -> str:
    return sc.entry(target).base or target


def _canary_row(sc: Scenario, c: Case) -> dict[str, Any]:
    assert c.target and c.role
    table = _base(sc, c.target)
    pk, oc, pc = sc.pk_col(table), sc.owner_col(table), sc.public_col(table)
    actor = user_id(c.role)
    row: dict[str, Any] = {}
    for name, typ in _columns(c.target):
        if name == pk:
            row[name] = str(uuid.uuid4())
        elif name == oc:
            row[name] = user_id(c.new_owner) or actor
        elif name == pc:
            row[name] = False
        elif typ == "uuid":
            row[name] = actor or user_id(c.new_owner)
        elif typ == "boolean":
            row[name] = False
        elif typ in ("integer", "bigint", "smallint", "numeric", "real", "double precision"):
            row[name] = 0
        elif typ.startswith("timestamp") or typ == "date":
            row[name] = datetime.now(UTC).isoformat()
        elif typ in ("json", "jsonb"):
            row[name] = {}
        else:
            row[name] = CANARY
    return {k: v for k, v in row.items() if v is not None}


def _expect_write(sc: Scenario, c: Case, changed: list[bool], marker: str) -> None:
    if any(changed):
        writers = {w.role for w in labctl.db_writes_since(marker)}
        sc.reapply()
        assert writers & POSTGREST_ROLES, f"{c.id}: write not attributed to a PostgREST role in the DB log"
    if c.expect is Outcome.ALLOWED:
        assert all(changed), f"{c.id}: {c.op} by {c.role} had no effect on {changed.count(False)} row(s)"
    else:
        assert not any(changed), f"{c.id}: {c.op} by {c.role} changed {changed.count(True)} row(s)"


def _insert(sc: Scenario, c: Case) -> None:
    assert c.target and c.role
    row = _canary_row(sc, c)
    table = _base(sc, c.target)
    marker = labctl.db_log_marker()
    sc.http.post(sc.path(c.target), headers=sc.headers(c.role, Prefer="return=minimal"), json=row)
    _expect_write(sc, c, [sc.visible(None, table, [row[sc.pk_col(table)]]) != set()], marker)


def _mutable_column(sc: Scenario, table: str) -> str:
    skip = {sc.pk_col(table), sc.owner_col(table), sc.public_col(table)}
    for name, typ in _columns(table):
        if name not in skip and typ in ("text", "character varying"):
            return name
    raise AssertionError(f"{table}: no text column to update")


def _update(sc: Scenario, c: Case) -> None:
    assert c.target and c.role
    table = _base(sc, c.target)
    pk = sc.pk_col(table)
    if c.new_owner:
        col, value = sc.owner_col(table), user_id(c.new_owner)
        assert col
    else:
        col, value = _mutable_column(sc, table), f"{CANARY}-{uuid.uuid4().hex[:8]}"
    marker = labctl.db_log_marker()
    for p in _pks(sc, c):
        sc.http.patch(sc.path(c.target), headers=sc.headers(c.role, Prefer="return=minimal"),
                      params={pk: f"eq.{p}"}, json={col: value})
    after = {str(r[pk]): r for r in sc.all_rows(table)}
    _expect_write(sc, c, [after[p][col] == value for p in _pks(sc, c)], marker)


def _delete(sc: Scenario, c: Case) -> None:
    assert c.target and c.role
    table = _base(sc, c.target)
    pk = sc.pk_col(table)
    marker = labctl.db_log_marker()
    for p in _pks(sc, c):
        sc.http.delete(sc.path(c.target), headers=sc.headers(c.role, Prefer="return=minimal"),
                       params={pk: f"eq.{p}"})
    left = {str(r[pk]) for r in sc.all_rows(table)}
    _expect_write(sc, c, [p not in left for p in _pks(sc, c)], marker)


# --- storage and keys ---------------------------------------------------------------------

def _storage(sc: Scenario, c: Case) -> None:
    assert c.target and c.role and c.op is Op.SELECT
    for r in c.rows:
        obj = sc.gt.rows[r].pk
        public = sc.http.head(f"/storage/v1/object/public/{c.target}/{obj}")
        authed = sc.http.head(f"/storage/v1/object/authenticated/{c.target}/{obj}", headers=sc.headers(c.role))
        reachable = public.status_code == 200 or authed.status_code == 200
        assert reachable is (c.expect is Outcome.ALLOWED), \
            f"{c.id}: HEAD public={public.status_code} authenticated={authed.status_code}"


def _key(sc: Scenario, c: Case) -> None:
    assert c.target and c.target.startswith("jwt:"), f"{c.id}: oracle checks JWT keys only"
    role = c.target.removeprefix("jwt:")
    found = sc.frontend_jwt_roles()
    assert role in found, f"{c.id}: no JWT with role={role} in the frontend"
    lab_key = {"anon": sc.info.anon_key, "service_role": sc.info.service_role_key}[role]
    assert found[role] == lab_key, f"{c.id}: frontend {role} key is not the lab's key"
