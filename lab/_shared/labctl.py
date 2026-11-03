"""Lab controller (T-060): start, reset and inspect the one local Supabase lab (ADR-018).

Lab code is test infrastructure and talks only to localhost (the Supabase CLI pulls images).
Why docker exec for SQL: no psql is required on the host, and `log_statement` can only be
set by supabase_admin inside the db container.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import (
    LAB_DEFAULT_PASSWORDS,
    LAB_EXCLUDED_SERVICES,
    LAB_LOCK_FILE,
    LAB_PROJECT_DIR,
    LAB_PROJECT_ID,
    LOG_LINE_PREFIX,
    POSTGREST_ROLES,
    SQL_QUOTED_RE,
    WRITE_KEYWORD_RE,
    DbWrite,
    LabInfo,
)
from rlsentry.contracts.models import Role

_REPO = Path(__file__).resolve().parents[2]
_DB = f"supabase_db_{LAB_PROJECT_ID}"
_LOCK_STATE = threading.local()
_INFO_CACHE: list[LabInfo] = []
_PREFIX_TOKENS = {
    "%h": r"\S*",
    "%m": r"\d{4}-\d\d-\d\d \S+ \S+",
    "%p": r"\d+",
    "%u": r"(?P<user>[^@\s]*)",
    "%d": r"\S*",
    "%q": "",
}


def _prefix_regex(prefix: str) -> str:
    """Regex source derived from LOG_LINE_PREFIX so the parser cannot drift from the setting."""
    return "".join(_PREFIX_TOKENS.get(part, re.escape(part)) for part in re.split(r"(%[a-z])", prefix))


_LOG_RE = re.compile(
    "^" + _prefix_regex(LOG_LINE_PREFIX) + r"LOG:\s+"
    r"(?:statement|execute [^:]*): (?P<sql>.*)$"
)

_RESET_SQL = """
DO $$ DECLARE s text; BEGIN
  FOR s IN SELECT nspname FROM pg_namespace
           WHERE pg_get_userbyid(nspowner) = 'postgres'
             AND nspname NOT IN ('public', 'extensions', '_realtime')
             AND nspname NOT LIKE 'pg\\_%' LOOP
    EXECUTE format('DROP SCHEMA %I CASCADE', s);
  END LOOP;
END $$;
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON SCHEMA public TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres, anon, authenticated, service_role;
DO $$ DECLARE p record; BEGIN
  FOR p IN SELECT schemaname, tablename, policyname FROM pg_policies
           WHERE schemaname = 'storage' AND tablename IN ('objects', 'buckets') LOOP
    EXECUTE format('DROP POLICY %I ON %I.%I', p.policyname, p.schemaname, p.tablename);
  END LOOP;
END $$;
SET LOCAL storage.allow_delete_query = 'true';
DELETE FROM storage.objects;
DELETE FROM storage.buckets;
DELETE FROM auth.users;
ALTER ROLE authenticator RESET pgrst.openapi_mode;
"""

_LOGGING_SQL = """
ALTER SYSTEM SET log_statement = 'mod';
ALTER SYSTEM SET log_line_prefix = '__PREFIX__';
SELECT pg_reload_conf();
ALTER ROLE supabase_auth_admin RESET log_statement;
ALTER ROLE supabase_storage_admin RESET log_statement;
ALTER ROLE authenticator SET log_statement = 'all';
"""

_USER_SQL = """
INSERT INTO auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
    confirmation_token, recovery_token, email_change_token_new, email_change,
    email_change_token_current, phone_change, phone_change_token, reauthentication_token)
VALUES ('00000000-0000-0000-0000-000000000000', :'id'::uuid, 'authenticated', 'authenticated', :'email',
    extensions.crypt(:'pw', extensions.gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}', '{}', now(), now(),
    '', '', '', '', '', '', '', '')
ON CONFLICT (id) DO NOTHING;
INSERT INTO auth.identities (provider_id, user_id, identity_data, provider, last_sign_in_at,
    created_at, updated_at)
VALUES (:'id', :'id'::uuid, jsonb_build_object('sub', :'id', 'email', :'email',
    'email_verified', true), 'email', now(), now(), now())
ON CONFLICT DO NOTHING;
"""


def _run(cmd: list[str], *, cwd: Path | None = None, stdin: str | None = None,
         check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"cannot run {cmd[0]}: {exc}") from exc
    if check and proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
        raise RuntimeError(f"{' '.join(cmd[:3])} failed (exit {proc.returncode}):\n{tail}")
    return proc


def _psql(sql: str, *, user: str = "postgres", args: tuple[str, ...] = (),
          variables: dict[str, str] | None = None, env: tuple[str, ...] = ()) -> str:
    cmd = ["docker", "exec", "-i", *(a for e in env for a in ("-e", e)), _DB, "psql", "-U", user, "-d", "postgres", "-X", "-q",
           "-v", "ON_ERROR_STOP=1", "-At", *args]
    for k, v in (variables or {}).items():
        cmd += ["-v", f"{k}={v}"]
    return _run(cmd, stdin=sql).stdout


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return _run(["supabase", *args], cwd=_REPO / LAB_PROJECT_DIR)


def _running() -> bool:
    proc = _run(["docker", "ps", "--format", "{{.Names}}"], check=False)
    names = set(proc.stdout.split())
    return all(f"supabase_{s}_{LAB_PROJECT_ID}" in names for s in ("db", "kong", "auth", "rest"))


def _info() -> LabInfo:
    data = json.loads(_cli("status", "-o", "json").stdout)
    return LabInfo(api_url=data["API_URL"], db_url=data["DB_URL"], anon_key=data["ANON_KEY"],
                   service_role_key=data["SERVICE_ROLE_KEY"])


def _info_cached() -> LabInfo:
    if not _INFO_CACHE:
        _INFO_CACHE.append(_info())
    return _INFO_CACHE[0]


def lab_password(role: Role) -> str:
    """Password of a lab account: env override first so CI can rotate it."""
    return os.environ.get(LAB_USERS[role]["password_env"]) or LAB_DEFAULT_PASSWORDS[role]


def _create_users() -> None:
    for role, user in LAB_USERS.items():
        _psql(_USER_SQL, variables={"id": user["id"], "email": user["email"],
                                    "pw": lab_password(role)})


def _users_ok() -> bool:
    want = ",".join(f"'{u['id']}'" for u in LAB_USERS.values())
    got = query(f"select count(*) from auth.users where id in ({want})")
    return got == [(str(len(LAB_USERS)),)]


def ensure_up() -> LabInfo:
    """Start the lab if needed and make logging and test accounts correct; idempotent."""
    with lock():
        if not _running():
            _INFO_CACHE.clear()
            _cli("start", "-x", ",".join(LAB_EXCLUDED_SERVICES))
        pending = _psql(
            "SELECT count(*) FROM pg_roles r WHERE (r.rolname IN ('supabase_auth_admin', "
            "'supabase_storage_admin') AND EXISTS (SELECT 1 FROM pg_db_role_setting s WHERE "
            "s.setrole = r.oid AND s.setconfig::text LIKE '%log_statement%')) OR "
            "(r.rolname = 'authenticator' AND NOT EXISTS (SELECT 1 FROM pg_db_role_setting s "
            "WHERE s.setrole = r.oid AND s.setconfig::text LIKE '%log_statement=all%'))",
            user="supabase_admin")
        _psql(_LOGGING_SQL.replace("__PREFIX__", LOG_LINE_PREFIX), user="supabase_admin")
        if pending.strip() != "0":  # pooled sessions keep the old per-role setting until reconnect
            _psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename IN "
                  "('supabase_auth_admin', 'supabase_storage_admin', 'authenticator')",
                  user="supabase_admin")
            time.sleep(1.5)
            _wait_services(_info_cached(), time.monotonic() + 15)
        if not _users_ok():
            _create_users()
        return _info_cached()


def scenario_dir(scenario: str) -> Path:
    """The single lab/<scenario>_<slug>/ directory, else ValueError."""
    matches = sorted(p for p in (_REPO / "lab").glob(f"{scenario}_*") if p.is_dir())
    if len(matches) != 1:
        raise ValueError(f"scenario {scenario!r}: expected exactly one lab/{scenario}_*/, "
                         f"got {len(matches)}")
    return matches[0]


def _wait_postgrest(info: LabInfo, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{info.api_url}/rest/v1/", headers={"apikey": info.anon_key}, timeout=2)
            if r.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("PostgREST did not serve the new schema within 10 s")


def _wait_services(info: LabInfo, deadline: float) -> None:
    """Poll until PostgREST answers and GoTrue accepts a lab login (no 5xx)."""
    user = next(iter(LAB_USERS.items()))
    while time.monotonic() < deadline:
        try:
            h = {"apikey": info.anon_key}
            rest = httpx.get(f"{info.api_url}/rest/v1/", headers=h, timeout=2)
            auth = httpx.post(f"{info.api_url}/auth/v1/token?grant_type=password", headers=h,
                              json={"email": user[1]["email"], "password": lab_password(user[0])},
                              timeout=3)
            if rest.status_code < 500 and auth.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError("GoTrue/PostgREST did not recover within 15 s after reconnecting")


def _upload_storage(root: Path) -> None:
    """Upload storage/<bucket>/<path> files through the local Storage API (service_role, upsert).

    Why the API and not SQL: real objects exist in the file backend, so public URLs and HEAD
    probes behave like production (ADR-018 #6)."""
    if not root.is_dir():
        return
    info = _info_cached()
    headers = {"apikey": info.service_role_key, "Authorization": f"Bearer {info.service_role_key}",
               "x-upsert": "true", "Content-Type": "application/octet-stream"}
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        bucket, _, path = f.relative_to(root).as_posix().partition("/")
        r = httpx.post(f"{info.api_url}/storage/v1/object/{bucket}/{path}", headers=headers,
                       content=f.read_bytes(), timeout=30)
        if r.status_code >= 300:
            raise RuntimeError(f"storage upload {bucket}/{path} failed: HTTP {r.status_code} {r.text[:200]}")


def apply(scenario: str) -> None:
    """Replace whatever scenario is loaded with `scenario` (see contract for the steps)."""
    d = scenario_dir(scenario)
    with lock():
        _psql("BEGIN;" + _RESET_SQL + "COMMIT;")
        _create_users()
        _psql("BEGIN;\n" + (d / "migration.sql").read_text() + "\nCOMMIT;")
        _upload_storage(d / "storage")
        _psql("BEGIN;\n" + (d / "seed.sql").read_text() + "\nCOMMIT;")
        _psql("NOTIFY pgrst, 'reload schema'; NOTIFY pgrst, 'reload config';")
        deadline = time.monotonic() + 10
        time.sleep(0.3)
        _wait_postgrest(_info_cached(), deadline)


def query(sql: str) -> list[tuple[str, ...]]:
    """Run one read-only statement as postgres; rows as text tuples (NULL -> '')."""
    out = _psql(sql, args=("-F", "\x1f"), env=("PGOPTIONS=-c default_transaction_read_only=on",))
    return [tuple(line.split("\x1f")) for line in out.splitlines() if line != ""]


def execute(sql: str) -> None:
    """Run `sql` as postgres in one transaction, then reload PostgREST's schema and wait for it.

    Why: mutation tests (ADR-022 #3) break a loaded scenario on purpose; -1 with ON_ERROR_STOP
    leaves nothing behind on error."""
    with lock():
        _psql(sql, args=("-1", "-f", "-"))
        _psql("NOTIFY pgrst, 'reload schema';")
        deadline = time.monotonic() + 10
        time.sleep(0.3)
        _wait_postgrest(_info_cached(), deadline)


def write_command(sql: str) -> str | None:
    """Pure classification of one logged statement (ADR-019, ADR-024).

    Why one pass: quoted parts are neutralised left to right, so an apostrophe inside an
    identifier or a dollar-quoted body cannot open a fake literal that hides a write."""
    def neutral(m: re.Match[str]) -> str:
        return '"x"' if m.group(0).startswith('"') else "''"

    found = WRITE_KEYWORD_RE.search(SQL_QUOTED_RE.sub(neutral, sql))
    return found.group(0).split()[0].upper() if found else None


def db_log_marker() -> str:
    """Timestamp usable with `docker logs --since` (UTC, microseconds)."""
    time.sleep(0.05)
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _command_of(sql: str) -> str:
    """write_command, else the statement's first keyword (DDL logged by log_statement = mod)."""
    cmd = write_command(sql)
    if cmd:
        return cmd
    first = re.search(r"[A-Za-z]+", SQL_QUOTED_RE.sub("''", sql))
    return first.group(0).upper() if first else "UNKNOWN"


def _read_log_until(marker: str, sentinel: str) -> list[list[str]] | None:
    """Statement records before the sentinel record, or None while it has not appeared yet."""
    proc = _run(["docker", "logs", "--since", marker, _DB], check=False)
    sentinel_re = re.compile(r"LOG:\s+" + re.escape(sentinel) + r"\s*$")
    entries: list[list[str]] = []
    for line in (proc.stdout + proc.stderr).splitlines():
        if sentinel_re.search(line):
            return entries
        m = _LOG_RE.match(line)
        if m:
            entries.append([m.group("user"), m.group("sql")])
        elif line.startswith(("\t", " ")) and entries:
            entries[-1][1] += " " + line.strip()
        elif entries:
            entries.append(["", ""])  # another log record ends the previous statement
    return None


def db_writes_since(marker: str) -> list[DbWrite]:
    """Writes logged after `marker`; only role and command kept (ADR-019).

    Why a sentinel: the server log is asynchronous, so a fixed sleep cannot prove it is
    complete. We emit a unique RAISE LOG record and read until it shows up (MS2 audit F6).
    Why keyword matching: PostgREST wraps writes in a CTE that Postgres classifies as SELECT, so
    authenticator logs everything and we keep statements where write_command finds a write.
    Other roles only log what log_statement = mod selects, so all of theirs are writes or DDL."""
    sentinel = f"rlsentry-flush-{uuid.uuid4()}"
    _psql(f"DO $$BEGIN RAISE LOG '{sentinel}'; END$$;")
    deadline = time.monotonic() + 10
    entries = _read_log_until(marker, sentinel)
    while entries is None:
        if time.monotonic() >= deadline:
            raise RuntimeError("Postgres log flush sentinel did not appear within 10 s")
        time.sleep(0.1)
        entries = _read_log_until(marker, sentinel)
    return [DbWrite(role=u, command=_command_of(q)) for u, q in entries
            if u and q and (u not in POSTGREST_ROLES or write_command(q) is not None)]


@contextmanager
def _lock_cm() -> Iterator[None]:
    depth = getattr(_LOCK_STATE, "depth", 0)
    if depth:
        _LOCK_STATE.depth = depth + 1
        try:
            yield
        finally:
            _LOCK_STATE.depth -= 1
        return
    with open(LAB_LOCK_FILE, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        _LOCK_STATE.depth = 1
        try:
            yield
        finally:
            _LOCK_STATE.depth = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


def lock() -> AbstractContextManager[None]:
    """Exclusive, process-reentrant lab lock."""
    return _lock_cm()
