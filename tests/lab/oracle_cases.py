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

import httpx

from lab._shared import labctl
from rlsentry.contracts.ground_truth import Case, CaseKind
from rlsentry.contracts.lab import POSTGREST_ROLES
from rlsentry.contracts.models import Op, Outcome, Role
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
    # The role's own request must be served (200 + list) even when nothing is forbidden.
    sc.visible(c.role, c.target, [str(uuid.uuid4())])
    forbidden = [str(r[pk]) for r in rows
                 if not sc.permitted(c.target, "select", c.role, r.get(oc) if oc else None,
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
    # anon has no id: use the new owner or user_a, so NOT NULL / FK columns never make a
    # denied insert "pass" for the wrong reason (MS1 audit P1-1).
    fallback = user_id(c.new_owner) or actor or user_id(Role.USER_A)
    row: dict[str, Any] = {}
    for name, typ in _columns(c.target):
        if name == pk:
            row[name] = str(uuid.uuid4())
        elif name == oc:
            row[name] = user_id(c.new_owner) or fallback
        elif name == pc:
            row[name] = False
        elif typ == "uuid":
            row[name] = actor or fallback
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


def _rls_denied(r: httpx.Response) -> bool:
    """A refusal that comes from authorization, not from bad input: 401/403, or Postgres
    42501 (insufficient privilege / RLS WITH CHECK violation)."""
    if r.status_code in (401, 403):
        return True
    try:
        return r.json().get("code") == "42501"
    except ValueError:
        return False


def _check_status(c: Case, responses: list[httpx.Response], changed: list[bool]) -> None:
    """Allowed writes must succeed (2xx). Denied writes must be refused by authorization:
    a 401/403/42501, or (UPDATE/DELETE only) a 2xx that RLS filtered down to no change.
    Any other error (23502 NOT NULL, 22P02 bad input, 500…) is a broken case, not a denial."""
    for r, ch in zip(responses, changed, strict=True):
        if c.expect is Outcome.ALLOWED:
            assert 200 <= r.status_code < 300, f"{c.id}: allowed write got HTTP {r.status_code}"
        elif 200 <= r.status_code < 300:
            assert c.op in (Op.UPDATE, Op.DELETE) and not ch, \
                f"{c.id}: denied {c.op} returned HTTP {r.status_code}"
        else:
            assert _rls_denied(r), f"{c.id}: denied for the wrong reason: HTTP {r.status_code} {r.text[:120]}"


def _expect_write(sc: Scenario, c: Case, changed: list[bool], marker: str,
                  responses: list[httpx.Response]) -> None:
    _check_status(c, responses, changed)
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
    r = sc.http.post(sc.path(c.target), headers=sc.headers(c.role, Prefer="return=minimal"), json=row)
    _expect_write(sc, c, [sc.visible(None, table, [row[sc.pk_col(table)]]) != set()], marker, [r])


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
    before = {str(r[pk]): r for r in sc.all_rows(table)}
    assert all(before[p][col] != value for p in _pks(sc, c)), f"{c.id}: row already has the new value"
    marker = labctl.db_log_marker()
    responses = [sc.http.patch(sc.path(c.target), headers=sc.headers(c.role, Prefer="return=minimal"),
                               params={pk: f"eq.{p}"}, json={col: value}) for p in _pks(sc, c)]
    after = {str(r[pk]): r for r in sc.all_rows(table)}
    _expect_write(sc, c, [after[p][col] == value for p in _pks(sc, c)], marker, responses)


def _delete(sc: Scenario, c: Case) -> None:
    assert c.target and c.role
    table = _base(sc, c.target)
    pk = sc.pk_col(table)
    marker = labctl.db_log_marker()
    responses = [sc.http.delete(sc.path(c.target), headers=sc.headers(c.role, Prefer="return=minimal"),
                                params={pk: f"eq.{p}"}) for p in _pks(sc, c)]
    left = {str(r[pk]) for r in sc.all_rows(table)}
    _expect_write(sc, c, [p not in left for p in _pks(sc, c)], marker, responses)


# --- storage and keys ---------------------------------------------------------------------

def _storage(sc: Scenario, c: Case) -> None:
    assert c.target and c.role and c.op is Op.SELECT
    for r in c.rows:
        obj = sc.gt.rows[r].pk
        public = sc.http.head(f"/storage/v1/object/public/{c.target}/{obj}")
        authed = sc.http.head(f"/storage/v1/object/authenticated/{c.target}/{obj}", headers=sc.headers(c.role))
        for resp in (public, authed):
            assert resp.status_code < 500, f"{c.id}: storage HTTP {resp.status_code} (broken, not denied)"
        reachable = public.status_code == 200 or authed.status_code == 200
        assert reachable is (c.expect is Outcome.ALLOWED), \
            f"{c.id}: HEAD public={public.status_code} authenticated={authed.status_code}"


def _key(sc: Scenario, c: Case) -> None:
    assert c.target and c.target.startswith("jwt:"), f"{c.id}: oracle checks JWT keys only"
    role = c.target.removeprefix("jwt:")
    found = sc.frontend_jwt_roles()
    assert role in found, f"{c.id}: no JWT with role={role} in the frontend"
    keys = {"anon": sc.info.anon_key, "service_role": sc.info.service_role_key}
    assert role in keys, f"{c.id}: oracle knows only anon and service_role keys"
    lab_key = keys[role]
    assert found[role] == lab_key, f"{c.id}: frontend {role} key is not the lab's key"
