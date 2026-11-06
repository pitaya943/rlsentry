"""An in-memory Supabase (frontend + PostgREST + GoTrue subset) behind httpx.MockTransport.

Used by the pipeline and CLI unit tests: run_scan talks to it through the real SafeClient, so
the write gate, the User-Agent and the S4 endpoint rule are exercised with no network. RLS is a
Python predicate per table: "own" (owner_id = auth.uid()), "all" (any signed-in user), plus an
optional anon read. Only the request shapes RLSentry sends are implemented.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

import httpx

from rlsentry.contracts.models import Role
from rlsentry.contracts.policy import RoleScopes, RowScope, TablePolicy, TestUser

API = "http://127.0.0.1:54321"      # local: dev/ci may write here (lab-like)
REMOTE = "http://api.test"         # remote: the gate refuses dev writes here
APP = "http://app.test"
A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ACCOUNTS = {"a@test.dev": ("pw-a", A), "b@test.dev": ("pw-b", B)}
ENV = {"RLS_A_PW": "pw-a", "RLS_B_PW": "pw-b", "SB_ANON": "", "DB": ""}
USERS = [TestUser(name=Role.USER_A, email="a@test.dev", password_env="RLS_A_PW"),
         TestUser(name=Role.USER_B, email="b@test.dev", password_env="RLS_B_PW")]
OWNER_ONLY = TablePolicy(owner_column="owner_id",
                         select=RoleScopes(anon=RowScope.DENY, user=RowScope.OWN_ROWS_ONLY))


def jwt(payload: dict[str, object]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return "eyJhbGciOiJIUzI1NiJ9." + body + ".c2lnbmF0dXJlLW5vdC12ZXJpZmllZA"


ANON_KEY = jwt({"role": "anon", "ref": "abcdefghijklmnopqrst"})
SERVICE_KEY = jwt({"role": "service_role", "ref": "abcdefghijklmnopqrst"})
ENV["SB_ANON"] = ANON_KEY


@dataclass
class Table:
    rows: list[dict[str, object]]
    rls: str = "own"            # own | all
    anon_read: bool = False
    insert_own: bool = True     # users may insert rows they own
    admin_metadata: bool = False   # L03: user_metadata.role = admin sees every row
    delete_own: bool = True        # owners may delete their rows (False: cleanup fails)
    shared: frozenset[str] = frozenset()   # row ids every signed-in user can already see


@dataclass
class FakeSupabase:
    tables: dict[str, Table] = field(default_factory=dict)
    api: str = API              # where this fake answers as Supabase
    bundle_url: str = API       # the Supabase URL baked into the frontend bundle
    bundle_keys: tuple[str, ...] = (ANON_KEY,)
    requests: list[httpx.Request] = field(default_factory=list)
    metadata_role: dict[str, object] = field(default_factory=dict)   # uid -> role claim
    put_metadata_status: int = 200
    restore_status: int | None = None     # status for PUTs clearing the role (None: as above)
    fail_when: Callable[[httpx.Request], bool] | None = None   # raise ReadTimeout for these

    # --- helpers for assertions -------------------------------------------------------------
    def hosts(self) -> set[str]:
        return {r.url.host for r in self.requests}

    def to(self, base: str) -> list[httpx.Request]:
        u = urlsplit(base)
        return [r for r in self.requests if r.url.host == u.hostname and (r.url.port or 80) == (u.port or 80)]

    def methods(self, base: str | None = None) -> set[str]:
        return {r.method for r in self.to(base or self.api)}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    # --- request handling ---------------------------------------------------------------------
    def __call__(self, r: httpx.Request) -> httpx.Response:
        self.requests.append(r)
        if self.fail_when is not None and self.fail_when(r):
            raise httpx.ReadTimeout("simulated timeout", request=r)
        if r.url.host == urlsplit(APP).hostname:
            return self._frontend(r)
        api = urlsplit(self.api)
        if r.url.host != api.hostname or (r.url.port or 80) != (api.port or 80):
            return httpx.Response(404)
        path = r.url.path
        if path == "/auth/v1/token" and r.method == "POST":
            body = json.loads(r.content)
            pw_uid = ACCOUNTS.get(body.get("email"))
            if not pw_uid or pw_uid[0] != body.get("password"):
                return httpx.Response(400, json={"error": "invalid_grant"})
            uid = pw_uid[1]
            claims: dict[str, object] = {"sub": uid, "role": "authenticated",
                                         "user_metadata": {"role": self.metadata_role.get(uid)}}
            return httpx.Response(200, json={"access_token": jwt(claims)})
        who, meta_admin = self._who(r)
        if path == "/auth/v1/user" and r.method == "PUT":
            if who is None:
                return httpx.Response(401)
            role = json.loads(r.content)["data"]["role"]
            status = self.put_metadata_status
            if role is None and self.restore_status is not None:
                status = self.restore_status
            if status == 200:
                self.metadata_role[who] = role
            return httpx.Response(status)
        if path == "/rest/v1/":
            return httpx.Response(200, json=self._openapi())
        name = path.removeprefix("/rest/v1/")
        t = self.tables.get(name)
        if t is None:
            return httpx.Response(404)
        params = parse_qsl(r.url.query.decode(), keep_blank_values=True)
        if r.method in ("GET", "HEAD"):
            rows = [x for x in t.rows if self._sees(t, who, meta_admin, x) and self._match(x, params)]
            limit = dict(params).get("limit")
            if limit is not None:
                rows = rows[: int(limit)]
            if r.method == "HEAD":
                n = len(rows)
                return httpx.Response(200, headers={"Content-Range": f"*/{n}" if n == 0 else f"0-{n - 1}/{n}"})
            sel = dict(params).get("select", "*").split(",")
            return httpx.Response(200, json=[{k: x[k] for k in sel if k in x} for x in rows])
        if who is None:
            return httpx.Response(401, json={"code": "42501"})
        if r.method == "POST":
            row = json.loads(r.content)
            if not (t.insert_own and row.get("owner_id") == who):
                return httpx.Response(403, json={"code": "42501"})
            t.rows.append(row)
            return httpx.Response(201)
        hit = [x for x in t.rows if x.get("owner_id") == who and self._match(x, params)]
        if r.method == "PATCH":
            change = json.loads(r.content)
            if any({**x, **change}.get("owner_id") != who for x in hit):
                return httpx.Response(403, json={"code": "42501"})   # WITH CHECK (owner_id = uid)
            for x in hit:
                x.update(change)
            return httpx.Response(204)
        if r.method == "DELETE":
            for x in hit if t.delete_own else []:
                t.rows.remove(x)
            return httpx.Response(204)
        return httpx.Response(405)

    def _who(self, r: httpx.Request) -> tuple[str | None, bool]:
        auth = r.headers.get("authorization", "")
        tok = auth.removeprefix("Bearer ")
        try:
            payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
        except (ValueError, IndexError):      # anything unparsable is anon
            return None, False
        if not isinstance(payload, dict) or payload.get("role") != "authenticated":
            return None, False
        meta = payload.get("user_metadata") or {}
        return str(payload["sub"]), meta.get("role") == "admin"

    @staticmethod
    def _sees(t: Table, uid: str | None, admin: bool, row: dict[str, object]) -> bool:
        if uid is None:
            return t.anon_read
        return (t.rls == "all" or (admin and t.admin_metadata) or row.get("owner_id") == uid
                or str(row.get("id")) in t.shared)

    @staticmethod
    def _match(row: dict[str, object], params: list[tuple[str, str]]) -> bool:
        for k, v in params:
            if k in ("select", "limit"):
                continue
            val = row.get(k)
            if v.startswith("eq."):
                if str(val) != v[3:]:
                    return False
            elif v.startswith("in.("):
                want = {x.strip().strip('"') for x in v[4:-1].split(",")}
                if str(val) not in want:
                    return False
            elif v in ("is.true", "is.false") and bool(val) != (v == "is.true"):
                return False
        return True

    def _openapi(self) -> dict[str, object]:
        props = {"id": {"type": "string", "format": "uuid", "description": "Note:\nThis is a Primary Key.<pk/>"},
                 "owner_id": {"type": "string", "format": "uuid"},
                 "title": {"type": "string", "format": "text"}}
        return {"swagger": "2.0", "paths": {"/": {}, **{f"/{n}": {"get": {}} for n in self.tables}},
                "definitions": {n: {"required": ["id", "owner_id"], "properties": props} for n in self.tables}}

    def _frontend(self, r: httpx.Request) -> httpx.Response:
        if r.url.path == "/":
            html = '<!doctype html><html><head><script type="module" src="/assets/app.js"></script></head></html>'
            return httpx.Response(200, text=html, headers={"Content-Type": "text/html"})
        if r.url.path == "/assets/app.js":
            calls = ";".join(f'const c{i}=createClient("{self.bundle_url}","{k}")'
                             for i, k in enumerate(self.bundle_keys))
            return httpx.Response(200, text=calls, headers={"Content-Type": "application/javascript"})
        return httpx.Response(404)


def notes_table(rls: str = "own") -> Table:
    """L04-like: one row each for user_a and user_b."""
    return Table(rows=[{"id": "11111111-0000-4000-8000-00000000000a", "owner_id": A, "title": "a"},
                       {"id": "22222222-0000-4000-8000-00000000000b", "owner_id": B, "title": "b"}],
                 rls=rls)
