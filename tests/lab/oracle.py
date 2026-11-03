"""Lab oracle (ADR-018): checks lab/<id>/expected.yaml against the running local lab.

This is test code, not the scanner. It may read the ground truth, use the service_role key and
write freely, but only to the local lab. It talks raw HTTP (httpx) so that a bug in rlsentry
can never hide a bug in the lab, and the other way round.

Scenario.load applies the scenario; every case that changed data re-applies it, so cases are
independent. Case semantics are those of rlsentry.contracts.ground_truth.Case; evaluation of
access and storage cases lives in tests/lab/oracle_cases.py.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS, Case, GroundTruth, SchemaEntry
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import Role
from rlsentry.contracts.safety import JWT_RE

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "lab"
ROLES = (Role.ANON, Role.USER_A, Role.USER_B)


def scenario_path(sid: str) -> Path:
    """lab/<sid>_<slug>/ found without the lab running (for test collection)."""
    found = sorted(LAB.glob(f"{sid}_*/expected.yaml"))
    assert len(found) == 1, f"expected exactly one lab/{sid}_*/expected.yaml"
    return found[0].parent


def load_gt(sid: str) -> GroundTruth:
    return GroundTruth.model_validate(yaml.safe_load((scenario_path(sid) / "expected.yaml").read_text("utf-8")))


def case_ids(sid: str) -> list[str]:
    gt = load_gt(sid)
    return [c.id for c in gt.vulnerable_cases + gt.safe_cases + gt.inconclusive_cases + gt.warning_cases]


def user_id(role: Role | None) -> str | None:
    return LAB_USERS[role]["id"] if role in LAB_USERS else None


def jwt_claims(token: str) -> dict[str, Any]:
    body = token.split(".")[1]
    return dict(json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))))


@dataclass
class Scenario:
    info: LabInfo
    sid: str
    gt: GroundTruth
    http: httpx.Client
    tokens: dict[Role, str] = field(default_factory=dict)

    # --- setup --------------------------------------------------------------------------

    @classmethod
    def load(cls, info: LabInfo, sid: str) -> Scenario:
        sc = cls(info, sid, load_gt(sid), httpx.Client(base_url=info.api_url, timeout=20.0))
        sc.reapply()
        return sc

    def reapply(self) -> None:
        labctl.apply(self.sid)
        self.tokens.clear()

    # --- identities ---------------------------------------------------------------------

    def login(self, role: Role) -> str:
        r = self.http.post("/auth/v1/token", params={"grant_type": "password"},
                           headers={"apikey": self.info.anon_key},
                           json={"email": LAB_USERS[role]["email"], "password": labctl.lab_password(role)})
        assert r.status_code == 200, f"login {role.value}: HTTP {r.status_code}"
        return str(r.json()["access_token"])

    def token(self, role: Role) -> str:
        if role is Role.ANON:
            return self.info.anon_key
        if role not in self.tokens:
            self.tokens[role] = self.login(role)
        return self.tokens[role]

    def headers(self, role: Role | None, **extra: str) -> dict[str, str]:
        """role None = service_role (ground-truth read-back only)."""
        bearer = self.info.service_role_key if role is None else self.token(role)
        return {"apikey": self.info.anon_key if role is not None else self.info.service_role_key,
                "Authorization": f"Bearer {bearer}", **extra}

    # --- schema helpers -----------------------------------------------------------------

    def entry(self, target: str) -> SchemaEntry:
        return self.gt.schema_[target]

    def path(self, target: str) -> str:
        return f"/rest/v1/rpc/{target}" if self.entry(target).kind == "rpc" else f"/rest/v1/{target}"

    def pk_col(self, target: str) -> str:
        e = self.entry(target)
        pk = e.primary_key or (self.entry(e.base).primary_key if e.base else [])
        assert len(pk) == 1, f"{target}: oracle needs a single-column primary key"
        return pk[0]

    def owner_col(self, target: str) -> str | None:
        tp = self.gt.policy.tables.get(target)
        if tp and tp.owner_column:
            return tp.owner_column
        base = self.entry(target).base
        return self.owner_col(base) if base else None

    def public_col(self, target: str) -> str | None:
        tp = self.gt.policy.tables.get(target)
        if tp and tp.public_column:
            return tp.public_column
        base = self.entry(target).base
        return self.public_col(base) if base else None

    def visible(self, role: Role | None, target: str, pks: list[str]) -> set[str]:
        """Primary keys among `pks` that `role` gets back from PostgREST (GET only)."""
        col = self.pk_col(target)
        r = self.http.get(self.path(target), headers=self.headers(role),
                          params={col: f"in.({','.join(pks)})", "select": col})
        if r.status_code != 200 or not isinstance(r.json(), list):
            return set()
        return {str(row[col]) for row in r.json() if isinstance(row, dict) and col in row}

    def all_rows(self, table: str) -> list[dict[str, Any]]:
        """Every row of a base table, read with service_role."""
        r = self.http.get(f"/rest/v1/{table}", headers=self.headers(None), params={"select": "*"})
        assert r.status_code == 200, f"service_role read {table}: HTTP {r.status_code}"
        return list(r.json())

    def frontend_text(self) -> str:
        d = scenario_path(self.sid) / "frontend"
        assert (d / "index.html").is_file() and (d / "assets" / "app.js").is_file(), "frontend missing"
        return "\n".join(p.read_text("utf-8") for p in sorted(d.rglob("*")) if p.is_file())

    # --- whole-scenario checks ----------------------------------------------------------

    def check_schema(self) -> None:
        """Every schema entry exists with its kind, columns, RLS flag, grants (lab conventions)."""
        for name, e in self.gt.schema_.items():
            if e.kind == "bucket":
                assert labctl.query(f"select count(*) from storage.buckets where id = '{name}'") == [("1",)], name
                continue
            if e.kind == "rpc":
                rows = labctl.query(
                    "select p.prosecdef, p.provolatile, p.pronargs from pg_proc p join pg_namespace n "
                    f"on n.oid = p.pronamespace where n.nspname = 'public' and p.proname = '{name}'")
                assert len(rows) == 1, f"rpc {name} must exist exactly once"
                assert rows[0] == ("t" if e.security_definer else "f", "s", "0"), f"rpc {name}: {rows[0]}"
                for who in ("anon", "authenticated"):
                    assert labctl.query(f"select has_function_privilege('{who}', 'public.{name}()', 'EXECUTE')") \
                        == [("t",)], f"{who} cannot execute {name}"
                continue
            rows = labctl.query("select c.relkind, c.relrowsecurity from pg_class c join pg_namespace n "
                                f"on n.oid = c.relnamespace where n.nspname = 'public' and c.relname = '{name}'")
            assert len(rows) == 1, f"{e.kind} {name} must exist"
            assert rows[0][0] == {"table": "r", "view": "v"}[e.kind], f"{name}: relkind {rows[0][0]}"
            if e.kind == "table":
                assert rows[0][1] == ("t" if e.rls == "enabled" else "f"), f"{name}: RLS flag {rows[0][1]}"
            cols = {c for (c,) in labctl.query("select column_name from information_schema.columns "
                                               f"where table_schema = 'public' and table_name = '{name}'")}
            assert cols == set(e.columns), f"{name}: columns {sorted(cols)} != {sorted(e.columns)}"
            for who in ("anon", "authenticated"):
                assert labctl.query(f"select has_table_privilege('{who}', 'public.{name}', "
                                    "'SELECT,INSERT,UPDATE,DELETE')") == [("t",)], f"{who} grants on {name}"

    def check_rows(self) -> None:
        """Exactly the seeded rows exist, with the planned owners and public flags."""
        by_target: dict[str, list[str]] = {}
        for name, row in self.gt.rows.items():
            by_target.setdefault(row.target, []).append(name)
        for target, names in by_target.items():
            if self.entry(target).kind == "bucket":
                for n in names:
                    row = self.gt.rows[n]
                    got = labctl.query(f"select owner_id from storage.objects where bucket_id = '{target}' "
                                       f"and name = '{row.pk}'")
                    assert got == [(user_id(row.owner) or "",)], f"object {n}: {got}"
                continue
            rows = {str(r[self.pk_col(target)]): r for r in self.all_rows(target)}
            assert set(rows) == {self.gt.rows[n].pk for n in names}, f"{target}: unexpected or missing rows"
            for n in names:
                row, got = self.gt.rows[n], rows[self.gt.rows[n].pk]
                oc, pc = self.owner_col(target), self.public_col(target)
                if oc:
                    assert got[oc] == user_id(row.owner), f"row {n}: owner {got[oc]}"
                if pc:
                    assert bool(got[pc]) is row.public, f"row {n}: public flag {got[pc]}"
        for e_name, e in self.gt.schema_.items():
            if e.kind == "table" and e_name not in by_target:
                assert self.all_rows(e_name) == [], f"{e_name} must be empty"

    def check_discovery(self) -> None:
        """OpenAPI exposure and frontend references match `in_openapi`, `in_bundle`, discovery_cases."""
        r = self.http.get("/rest/v1/", headers={"apikey": self.info.anon_key,
                                                "Authorization": f"Bearer {self.info.anon_key}"})
        paths = set(r.json().get("paths", {})) if r.status_code == 200 and isinstance(r.json(), dict) else set()
        text = self.frontend_text()
        for name, e in self.gt.schema_.items():
            if e.kind == "bucket":
                continue
            api_path = f"/rpc/{name}" if e.kind == "rpc" else f"/{name}"
            listed = api_path in paths
            assert listed is (self.gt.openapi and e.in_openapi), f"{name}: in OpenAPI = {listed}"
            ref = re.search(rf"""\.(?:from|rpc)\(\s*['"]{re.escape(name)}['"]""", text) is not None
            assert ref is e.in_bundle, f"{name}: referenced in frontend = {ref}"
        for d in self.gt.discovery_cases:
            e = self.entry(d.target)
            if d.discovered_by == "openapi":
                assert self.gt.openapi and e.in_openapi
            elif d.discovered_by == "bundle":
                assert e.in_bundle and not (self.gt.openapi and e.in_openapi)
            else:
                assert not e.in_bundle and not (self.gt.openapi and e.in_openapi)
                assert d.target in self.gt.policy.tables

    def frontend_jwt_roles(self) -> dict[str, str]:
        """role claim → token, for every JWT in the frontend."""
        return {str(jwt_claims(t).get("role")): t for t in JWT_RE.findall(self.frontend_text())}

    # --- cases --------------------------------------------------------------------------

    def case(self, case_id: str) -> Case:
        gt = self.gt
        found = [c for c in gt.vulnerable_cases + gt.safe_cases + gt.inconclusive_cases + gt.warning_cases
                 if c.id == case_id]
        assert len(found) == 1
        return found[0]

    def check_case(self, case_id: str) -> None:
        from tests.lab.oracle_cases import check_case
        check_case(self, self.case(case_id))
