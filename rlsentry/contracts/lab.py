"""Lab tooling contract (SPEC §8 Lab Benchmark; ADR-018). Owned by the architect.

The lab is ONE local Supabase project (lab/_shared/supabase/) that every scenario is loaded
into in turn: `apply("L04")` wipes the previous scenario and loads lab/L04_*/migration.sql and
seed.sql. Implemented by lab-dev in lab/_shared/labctl.py with exactly these names; the
architect's lab verification tests (tests/lab/) and later bench/ (MS4) call it.

Lab code is test infrastructure, not product code: it may write freely, but only to the
local lab (localhost). It never contacts any other host.
"""
from __future__ import annotations

import re
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from rlsentry.contracts.models import Role

LAB_PROJECT_DIR = Path("lab/_shared")
"""Supabase CLI workdir (relative to the repo root); config in lab/_shared/supabase/config.toml."""

LAB_PROJECT_ID = "rlsentry-lab"
"""`project_id` in config.toml; Docker containers are named supabase_<service>_rlsentry-lab."""

LAB_EXCLUDED_SERVICES: tuple[str, ...] = (
    "studio", "imgproxy", "realtime", "edge-runtime", "logflare", "vector", "supavisor",
    "mailpit", "postgres-meta",
)
"""Passed to `supabase start -x`: the lab needs only db, kong, auth (GoTrue), rest (PostgREST)
and storage. Fewer containers = faster start and less disk in cloud VMs."""

LAB_DEFAULT_PASSWORDS: dict[Role, str] = {
    Role.USER_A: "lab-user-a-password",
    Role.USER_B: "lab-user-b-password",
}
"""Fallback lab passwords when the LAB_USERS password_env variable is unset. Lab-only
accounts on localhost; never used anywhere else."""

LAB_LOCK_FILE = Path("/tmp/rlsentry-lab.lock")
"""fcntl lock serializing every process that applies a scenario or tests against the lab
(parallel tickets share the one lab)."""

LOG_LINE_PREFIX = "%h %m [%p] %q%u@%d "
"""log_line_prefix that ensure_up sets explicitly (Supabase's current default); db_writes_since
parses the database user out of it, so it must never silently change (MS1 audit P2-1)."""

POSTGREST_ROLES: frozenset[str] = frozenset({"anon", "authenticated", "authenticator"})
"""ADR-014 #2 (human-confirmed): NFR-01 counts only writes executed by these roles; GoTrue's
writes to auth.* (supabase_auth_admin) are listed separately and not counted."""


class LabInfo(BaseModel):
    """Connection details of the running lab (from `supabase status -o json`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_url: str            # http://127.0.0.1:54321
    db_url: str             # postgresql://postgres:postgres@127.0.0.1:54322/postgres
    anon_key: str           # legacy JWT, role=anon
    service_role_key: str   # legacy JWT, role=service_role (lab setup and tests only)


class DbWrite(BaseModel):
    """One data-modifying statement found in the Postgres log. Values are never kept (NFR-03):
    only who ran it and the command tag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str       # database user from log_line_prefix, e.g. "authenticator"
    command: str    # upper-case; see WRITE_COMMANDS

WRITE_COMMANDS: tuple[str, ...] = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE", "COPY")

WRITE_KEYWORD_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+[\"\w]|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|COPY\s+[\"\w(])",
    re.IGNORECASE)
"""ADR-019: a logged statement is a write iff this matches anywhere in its text. PostgREST
sends writes as `WITH pgrst_source AS (INSERT INTO …) SELECT …`, which Postgres classifies as
SELECT, so neither log_statement = mod nor pgaudit's session mode logs them. ADR-024: "its text"
means the statement as normalised by write_command (quoted parts neutralised, SQL_QUOTED_RE).
DbWrite.command is
the first word of the first match, upper-case (INSERT, UPDATE, …); for DDL logged by
log_statement = mod without such a keyword, it is the statement's first keyword (CREATE, …)."""

SQL_QUOTED_RE = re.compile(r"""'(?:[^']|'')*'|"(?:[^"]|"")*"|\$((?:[A-Za-z_]\w*)?)\$.*?\$\1\$""",
                           re.DOTALL)
"""Quoted parts of a logged statement, matched left to right (ADR-024, 補記 after the MS2 audit
F1/F2): a single-quoted string literal ('' escapes a quote), a double-quoted identifier (""
escapes), or a dollar-quoted string ($$…$$ or $tag$…$tag$). Scanning them in one pass is what
makes an apostrophe inside an identifier ("o'x") or a dollar-quoted body unable to open a fake
literal that would swallow a following write keyword. E'…' backslash escapes and -- comments
are not handled: PostgREST logs neither, and logged continuation lines are joined, so a comment
has no end.

PostgREST's OpenAPI query contains has_table_privilege(c.oid, 'SELECT, INSERT, UPDATE, DELETE,
TRUNCATE, …'); without this step authenticator would log a TRUNCATE on every `GET /rest/v1/`."""

SQL_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
"""First version of ADR-024 (single-quoted literals only). Superseded by SQL_QUOTED_RE and
write_command after the MS2 audit (F2); kept only so code accepted before T-113 still imports."""


class LabCtl(Protocol):
    """Module-level functions of lab/_shared/labctl.py (shown as a Protocol for typing)."""

    def ensure_up(self) -> LabInfo:
        """Start the lab if it is not running (`supabase start -x <LAB_EXCLUDED_SERVICES>` in
        LAB_PROJECT_DIR), otherwise reuse it. Idempotent. Ensures, as supabase_admin,
        `log_statement = 'mod'` (SPEC §8) with log_line_prefix = LOG_LINE_PREFIX (set explicitly), plus
        the role-level `ALTER ROLE authenticator SET log_statement = 'all'` (ADR-019; PostgREST
        is then reconnected so its pooled connections pick the setting up), so
        db_writes_since can attribute every write, and that every LAB_USERS account exists
        and can log in (created as in apply step 2 if missing). Raises RuntimeError with the CLI's last
        output lines when Docker or the CLI fails."""
        ...

    def apply(self, scenario: str) -> None:
        """Load scenario `scenario` (e.g. "L04") into the running lab, replacing whatever was
        loaded before, so results never depend on the previous scenario:
        1. drop and recreate schema public with Supabase's standard grants; drop functions and
           views the previous scenario created; delete all storage objects and buckets; drop
           every RLS policy on storage.objects and storage.buckets that is not part of a fresh
           Supabase install (scenarios such as L11 create them), so applying any scenario twice,
           or after any other scenario, gives the same state;
        2. delete all auth.users and recreate LAB_USERS (fixed ids and emails from
           rlsentry.contracts.ground_truth.LAB_USERS, passwords from lab_password, confirmed
           email, empty user_metadata) so each test user can log in with
           POST /auth/v1/token?grant_type=password;
        3. reset role-level PostgREST settings scenarios may change
           (ALTER ROLE authenticator RESET pgrst.openapi_mode);
        4. run lab/<scenario>_*/migration.sql as postgres in one transaction (ON_ERROR_STOP);
           then, if the scenario has a storage/ folder, upload every file
           storage/<bucket>/<path> to <bucket> at <path> through the local Storage API with the
           service_role key (upsert) (ADR-018 #6); then run seed.sql the same way as the
           migration (seed may UPDATE storage.objects, e.g. owner_id);
        5. NOTIFY pgrst 'reload schema' and 'reload config', then wait (≤ 10 s) until
           PostgREST serves the new schema.
        Unknown scenario → ValueError. Must hold lock() while running."""
        ...

    def lab_password(self, role: Role) -> str:
        """os.environ[LAB_USERS[role]['password_env']] if set, else LAB_DEFAULT_PASSWORDS[role]."""
        ...

    def query(self, sql: str) -> list[tuple[str, ...]]:
        """Run one read-only SQL statement as postgres and return rows as text tuples
        (psql -At semantics; NULL → ""). For tests that check schema, owners and grants.
        Read-only is enforced, not assumed (ADR-022): the session runs with
        default_transaction_read_only = on, so a write through query() fails with
        RuntimeError (SQLSTATE 25006) and changes nothing. This guards against accidents in
        test code, not against a statement that deliberately turns the setting off."""
        ...

    def execute(self, sql: str) -> None:
        """Run `sql` (one or more statements) as postgres in ONE transaction with
        ON_ERROR_STOP (psql -1), then NOTIFY pgrst 'reload schema' and wait (≤ 10 s) until
        PostgREST answers again, so a changed grant, policy or function is served at once.
        Any SQL error → RuntimeError with psql's last lines; nothing of the transaction stays.
        For lab mutation tests only (ADR-022 #3: break a loaded scenario on purpose and check
        that the oracle notices); the caller re-applies the scenario afterwards. Holds lock()
        while running. Never used by rlsentry itself (lab code is not product code)."""
        ...

    def write_command(self, sql: str) -> str | None:
        """Pure classification of one logged statement (ADR-019, ADR-024). Replace every
        SQL_QUOTED_RE match, in one left-to-right pass, by: '' for a single-quoted literal,
        "x" for a double-quoted identifier, '' for a dollar-quoted string. Then return the
        upper-cased first word of the first WRITE_KEYWORD_RE match (INSERT, UPDATE, DELETE,
        MERGE, TRUNCATE, COPY), or None when there is none. No I/O."""
        ...

    def db_log_marker(self) -> str:
        """An opaque marker for 'now' in the Postgres log (e.g. a timestamp)."""
        ...

    def db_writes_since(self, marker: str) -> list[DbWrite]:
        """Writes logged after `marker`, in order, for every role (filter with POSTGREST_ROLES).
        For a PostgREST role, a logged statement is returned iff write_command(statement) is
        not None (this catches PostgREST's CTE-wrapped writes, ADR-019, and ignores keywords
        inside quoted parts, ADR-024, so `GET /rest/v1/` logs no write); command = that value.
        For any other role every logged statement is returned (log_statement = mod logs only
        writes and DDL), command = write_command(statement) or its first keyword (CREATE, …).
        An UPDATE/DELETE that RLS filters down to 0 rows is still returned: NFR-01 counts write
        attempts, not effects.
        Flush (MS2 audit F6): before reading, emit a unique sentinel to the server log as
        postgres (`DO $$BEGIN RAISE LOG 'rlsentry-flush-<uuid4>'; END$$;`) and read the log
        until that sentinel appears (≤ 10 s, else RuntimeError). Only records before the
        sentinel record are considered; the sentinel and anything after it are never
        returned. A fixed sleep alone is not enough to prove the log is complete."""
        ...

    def scenario_dir(self, scenario: str) -> Path:
        """lab/<scenario>_<slug>/ (exactly one match), else ValueError."""
        ...

    def lock(self) -> AbstractContextManager[None]:
        """Exclusive fcntl lock on LAB_LOCK_FILE; blocks until free. Re-entrant within one
        process (nested use does not deadlock). `fcntl` is imported inside the call, never at
        module level, so labctl imports on platforms without it (Windows) and the Docker-free
        helpers such as write_command work there; only lock() raises ImportError (MS2 approval
        note 5)."""
        ...

