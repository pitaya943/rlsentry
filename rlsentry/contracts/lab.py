"""Lab tooling contract (SPEC §8 Lab Benchmark; ADR-018). Owned by the architect.

The lab is ONE local Supabase project (lab/_shared/supabase/) that every scenario is loaded
into in turn: `apply("L04")` wipes the previous scenario and loads lab/L04_*/migration.sql and
seed.sql. Implemented by lab-dev in lab/_shared/labctl.py with exactly these names; the
architect's lab verification tests (tests/lab/) and later bench/ (MS4) call it.

Lab code is test infrastructure, not product code: it may write freely, but only to the
local lab (localhost). It never contacts any other host.
"""
from __future__ import annotations

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
    command: str    # first SQL keyword, upper-case: INSERT, UPDATE, DELETE, TRUNCATE, …


class LabCtl(Protocol):
    """Module-level functions of lab/_shared/labctl.py (shown as a Protocol for typing)."""

    def ensure_up(self) -> LabInfo:
        """Start the lab if it is not running (`supabase start -x <LAB_EXCLUDED_SERVICES>` in
        LAB_PROJECT_DIR), otherwise reuse it. Idempotent. Ensures, as supabase_admin,
        `log_statement = 'mod'` (SPEC §8) with the database user in log_line_prefix, so
        db_writes_since can attribute every write. Raises RuntimeError with the CLI's last
        output lines when Docker or the CLI fails."""
        ...

    def apply(self, scenario: str) -> None:
        """Load scenario `scenario` (e.g. "L04") into the running lab, replacing whatever was
        loaded before, so results never depend on the previous scenario:
        1. drop and recreate schema public with Supabase's standard grants; drop functions and
           views the previous scenario created; delete all storage objects and buckets;
        2. delete all auth.users and recreate LAB_USERS (fixed ids and emails from
           rlsentry.contracts.ground_truth.LAB_USERS, passwords from lab_password, confirmed
           email, empty user_metadata) so each test user can log in with
           POST /auth/v1/token?grant_type=password;
        3. reset role-level PostgREST settings scenarios may change
           (ALTER ROLE authenticator RESET pgrst.openapi_mode);
        4. run lab/<scenario>_*/migration.sql then seed.sql as postgres, each in one
           transaction (ON_ERROR_STOP);
        5. NOTIFY pgrst 'reload schema' and 'reload config', then wait (≤ 10 s) until
           PostgREST serves the new schema.
        Unknown scenario → ValueError. Must hold lock() while running."""
        ...

    def lab_password(self, role: Role) -> str:
        """os.environ[LAB_USERS[role]['password_env']] if set, else LAB_DEFAULT_PASSWORDS[role]."""
        ...

    def query(self, sql: str) -> list[tuple[str, ...]]:
        """Run one read-only SQL statement as postgres and return rows as text tuples
        (psql -At semantics; NULL → ""). For tests that check schema, owners and grants."""
        ...

    def db_log_marker(self) -> str:
        """An opaque marker for 'now' in the Postgres log (e.g. a timestamp)."""
        ...

    def db_writes_since(self, marker: str) -> list[DbWrite]:
        """Data-modifying statements (log_statement = mod) logged after `marker`, in order,
        including those of every role (filter with POSTGREST_ROLES). DDL is included too,
        because log_statement = mod also logs it."""
        ...

    def scenario_dir(self, scenario: str) -> Path:
        """lab/<scenario>_<slug>/ (exactly one match), else ValueError."""
        ...

    def lock(self) -> AbstractContextManager[None]:
        """Exclusive fcntl lock on LAB_LOCK_FILE; blocks until free. Re-entrant within one
        process (nested use does not deadlock)."""
        ...

