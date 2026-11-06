"""M3 Probe contracts for reads (SPEC §5 M3; FR-06, FR-07, FR-08, FR-10). Owned by the architect.

MS2 covers SELECT only; write probes (FR-09) are added in MS3 (the "--- M3 writes" section
below). Implementations live in rlsentry/probe/<file>.py (and rlsentry/rules/severity.py for
the rule functions in rlsentry.contracts.rules) with exactly these names and signatures.
Design decisions: ADR-023 (reads), ADR-029 (writes).

How a write cell (target × role × INSERT/UPDATE/DELETE) is decided — dev/ci only; audit never
writes (SPEC §5 M3; FR-09; ADR-029):
1. plan_writes: for each role, enumerate the forbidden writes worth attempting from the
   expected policy and the identities (anon writing at all; a user writing another user's row;
   a user transferring ownership of its own row to the other user). A write is attempted only
   when the expected policy forbids its END state (forbidden_write).
2. seed_work_row: each UPDATE/DELETE plan gets its OWN fresh canary, created by the required
   owner just before the probe, so a successful destructive write never corrupts another
   probe's row (ADR-029 補記). INSERT makes its own canary. The scanner only ever writes to
   canaries it created, so it is always the owner and can clean up (SPEC §5 M3 清理).
3. send_write: one POST/PATCH/DELETE with `Prefer: return=minimal` (ADR-029 #2: a returned
   representation would re-run the SELECT policy and hide a real write behind a 403).
4. read_back: the identity that SHOULD see the end state (the work row's owner, or the new
   owner of a transfer/insert) reads the single primary key back immediately. write_outcome
   turns the after-state into "the forbidden change took effect" — the only thing that counts
   (SPEC §5 M3: a 2xx is not a write, a filtered 0-row UPDATE is not a write).
5. write_cell: took effect → allowed (a vulnerability); verifiably did not → denied; could not
   send or could not trust the read-back → inconclusive. cleanup_seeded then removes every
   canary (read-seed, work and INSERT) by its owner and reports any it could not (SPEC §5 M3).

How a read cell (target × role × SELECT) is decided — the core of the "count = 0 is not
denied" rule (SPEC §5 M3 三態結果):
1. Known rows: in every profile (MS2) each test user lists the primary keys of its OWN rows
   (`GET ?select=<pk>&<owner>=eq.<own id>`, primary keys only, KNOWN_ROWS_LIMIT at most),
   split into public / non-public when a public column is known (collect_known_rows). This is
   the audit "主鍵交集" of SPEC §5 M3; MS3 adds seeded rows for dev/ci.
2. split_known: for the probed role, every known row is either forbidden (the expected policy
   does not let this role see it) or permitted.
3. count_visible: one `HEAD … ?<pk>=in.(<forbidden pks>)` with `Prefer: count=exact`; the
   total in Content-Range says how many forbidden rows the role can see. No body is fetched.
4. read_cell: forbidden rows visible → allowed; none visible → denied; no forbidden known row,
   or no trustworthy count → inconclusive. Permitted rows are counted too, only to produce the
   EXPECTED_ACCESS_DENIED / SENSITIVE_COLUMN_PUBLIC hints (read_findings).
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rlsentry.contracts.models import AccessMatrix, Finding, Op, ProbeResult, Profile, Role, Target
from rlsentry.contracts.policy import ExpectedAccess, ExpectedPolicy, TestUser
from rlsentry.contracts.safety import SafeClientContract

PROBE_ROLES: tuple[Role, ...] = (Role.ANON, Role.USER_A, Role.USER_B)
"""Order in which roles are probed and cells are listed."""

USER_ROLES: tuple[Role, ...] = (Role.USER_A, Role.USER_B)

WRITE_OPS: tuple[Op, ...] = (Op.INSERT, Op.UPDATE, Op.DELETE)

KNOWN_ROWS_LIMIT = 50
"""Max primary keys one user lists per request in collect_known_rows (bounds what is
downloaded; primary keys are the only values RLSentry ever reads, CLAUDE.md)."""

AUDIT_WRITE_REASON = "audit profile is read-only (NFR-01)"
WRITE_PENDING_REASON = "write probes are not implemented yet (MS3)"
WRITE_REFUSED_REASON = "write refused by the safety gate for this host (ADR-041)"
"""Reason prefix of write cells that could not be probed because the SafeClient gate refused
the write (dev against a remote host, ci host not in write_hosts). Such cells are INCONCLUSIVE,
never denied: nothing was tested (MS3 approval note 1)."""
"""Reasons of the NOT_TESTED write cells produced by probe() in MS2."""

CONTENT_RANGE_TOTAL_RE = r"^(?:\*|\d+-\d+)/(\d+)$"
"""PostgREST Content-Range with count=exact: "*/0" (nothing) or "0-1/2". Group 1 = total.
A total of "*" (count not computed) does not match: no count, no verdict."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginFailed(Exception):
    """FR-07 login did not yield a usable JWT. The message names only the HTTP status or the
    exception class: never the email's password, the token or the response body (NFR-03)."""


class Sessions(_Strict):
    """Bearer token per role (anon → the anon key), the user id (JWT `sub`) of each logged-in
    test user, and why a role has no session. Tokens are excluded from repr and from
    model_dump/JSON so a session object can be logged without leaking them (NFR-03)."""

    tokens: dict[Role, str] = Field(default_factory=dict, repr=False, exclude=True)
    user_ids: dict[Role, str] = {}
    missing: dict[Role, str] = {}


class KnownRow(_Strict):
    """A row whose existence and owner are known without reading its content."""

    pk: str
    owner: Role            # user_a or user_b: the user that listed it as its own
    public: bool = False   # True only when a public column is known and the row is public


class KnownRows(_Strict):
    rows: list[KnownRow] = []
    notes: list[str] = []  # e.g. "user_b: HTTP 404"; why fewer rows are known than expected


class CountResult(_Strict):
    """One HEAD count request: how many of `queried` primary keys the role can see."""

    queried: int = Field(ge=1)
    status: int | None      # None: transport error, nothing received
    total: int | None       # parsed from Content-Range; None when absent or unparsable
    curl: str               # reproduction command, secrets masked (curl_command)


class ReadObservation(_Strict):
    """Everything read_cell and read_findings need for one cell; built by probe()."""

    target: str
    role: Role
    expected: ExpectedAccess
    forbidden: CountResult | None = None   # None: no forbidden known row (nothing sent)
    permitted: CountResult | None = None   # None: no permitted known row (nothing sent)
    note: str | None = None                # why forbidden is None


# --- probe/session.py (FR-07) ---------------------------------------------------------------

async def login(client: SafeClientContract, supabase_url: str, anon_key: str, email: str,
                password: str) -> tuple[str, str]:
    """Contract only; implemented by rlsentry.probe.session.login. ⚠ sends a POST.

    `POST <supabase_url without trailing slash>/auth/v1/token` with params
    {"grant_type": "password"} (the exact login request the write gate allows in every
    profile, ADR-014 #1), header `apikey: <anon_key>`, JSON body {"email", "password"}.
    Success = HTTP 200, a JSON object whose "access_token" is a string with three dot-separated
    parts whose middle part base64url-decodes (padding added) to a JSON object with a string
    "sub". Returns (access_token, sub). The signature is NOT verified: the token comes straight
    from the server we just asked. Anything else raises LoginFailed("login failed: HTTP <n>")
    or, for transport errors, LoginFailed("login failed: <exception class name>").
    """
    raise NotImplementedError


async def build_sessions(client: SafeClientContract, supabase_url: str, anon_key: str,
                         users: list[TestUser], env: Mapping[str, str]) -> Sessions:
    """Contract only; implemented by rlsentry.probe.session.build_sessions.

    tokens[ANON] = anon_key. For each TestUser: password = env.get(password_env); missing or
    empty → missing[name] = "<password_env> is not set" (no request). Otherwise login();
    success → tokens[name], user_ids[name]; LoginFailed → missing[name] = str(exc).
    A user role with no TestUser → missing[role] = "no test account configured".
    One failed user never stops the other: the scan continues and that role's cells become
    not_tested (probe()).
    """
    raise NotImplementedError


# --- probe/evidence.py ----------------------------------------------------------------------

def curl_command(method: str, url: str, headers: Mapping[str, str]) -> str:
    """Contract only; implemented by rlsentry.probe.evidence.curl_command. Pure. ⚠ NFR-03.

    "curl -sS" + (" -I" for HEAD, else " -X <METHOD>") + " " + shlex.quote(url), then for each
    header in the given order " -H " + shlex.quote("<name>: <value>"), where the value of a
    header named apikey (case-insensitive) is mask(value) and the value of Authorization is
    "Bearer " + mask(token) when it starts with "Bearer ", else mask(value). Finally the whole
    string goes through mask_text, so no JWT or sb_ key can survive anywhere (e.g. in the URL).
    """
    raise NotImplementedError


# --- probe/cross_tenant.py (FR-08: known rows for the cross-tenant comparison) -------------

async def collect_known_rows(client: SafeClientContract, supabase_url: str, anon_key: str,
                             target: Target, owner_column: str | None,
                             public_column: str | None, sessions: Sessions) -> KnownRows:
    """Contract only; implemented by rlsentry.probe.cross_tenant.collect_known_rows.

    No request and empty rows (with a note) when len(target.primary_key) != 1 or owner_column
    is None. Otherwise, for each role in USER_ROLES that has both a token and a user id:
    GET <base>/rest/v1/<name> (RPC: /rest/v1/rpc/<name>) with headers apikey: <anon_key>,
    Authorization: Bearer <that user's token>, params select=<pk>, <owner_column>=eq.<user id>,
    limit=KNOWN_ROWS_LIMIT, and — only when public_column is set — <public_column>=is.true
    (rows marked public=True) and, in a second request, <public_column>=is.false (public=False).
    A 200 response whose body is a JSON list contributes str(item[pk]) for every dict item
    with a non-null pk; any other response adds the note "<role>: HTTP <status>" (or the
    exception class name for transport errors) and contributes nothing. Rows are deduplicated
    by pk (first occurrence wins), in request order (user_a before user_b).
    Each user lists only rows it owns, with its own token: a row is never attributed to a
    user because someone else could see it.
    """
    raise NotImplementedError


# --- probe/read.py (FR-06) ------------------------------------------------------------------

async def count_visible(client: SafeClientContract, supabase_url: str, anon_key: str,
                        target: Target, token: str, pks: list[str]) -> CountResult:
    """Contract only; implemented by rlsentry.probe.read.count_visible. Never downloads rows.

    Precondition: pks non-empty and len(target.primary_key) == 1 (else ValueError).
    HEAD <base>/rest/v1/<name> (RPC: /rest/v1/rpc/<name>) with params
    select=<pk> and <pk>=in.(<v1>,<v2>,…) where each value is written as a double-quoted
    PostgREST literal ('"' + v with \\ → \\\\ and " → \\" + '"'), headers apikey: <anon_key>,
    Authorization: Bearer <token>, Prefer: count=exact.
    total = int(group 1 of CONTENT_RANGE_TOTAL_RE on the Content-Range header) or None.
    curl = curl_command("HEAD", <final URL with params, as sent>, <the same headers>).
    Transport errors → status=None, total=None (never raised).
    """
    raise NotImplementedError


class VisibleResult(_Strict):
    """One merged GET over a role's known primary keys (ADR-040): which of them it can see."""

    queried: int = Field(ge=1)
    status: int | None             # None: transport error
    visible: list[str] | None      # queried pks the response contained; None = untrustworthy
    curl: str                      # reproduction command, secrets masked (curl_command)


async def visible_pks(client: SafeClientContract, supabase_url: str, anon_key: str,
                      target: Target, token: str, pks: list[str]) -> VisibleResult:
    """Contract only; implemented by rlsentry.probe.read.visible_pks. Downloads primary keys only.

    MS4 approval note 2 (ADR-040): one request per (target, role) instead of one HEAD for the
    forbidden and one for the permitted known rows. Precondition: pks non-empty and
    len(target.primary_key) == 1 (else ValueError).
    GET <base>/rest/v1/<name> (RPC: /rest/v1/rpc/<name>) with params select=<pk>,
    <pk>=in.(<v1>,…) (same double-quoted literals as count_visible) and limit=<len(pks)>,
    headers apikey: <anon_key>, Authorization: Bearer <token> (no Prefer header).
    visible = [str(item[pk]) for each item, first occurrence, response order] ONLY when the
    status is 200 or 206, the body is a JSON list, every item is a dict whose pk value is not
    None, and every str(item[pk]) is one of `pks`; otherwise visible = None (a row outside the
    queried set means the filter was not applied: untrustworthy, ADR-023 #3).
    curl = curl_command("GET", <final URL with params, as sent>, <the same headers>).
    Transport errors → status=None, visible=None (never raised).
    """
    raise NotImplementedError


def observation_counts(res: VisibleResult | None, forbidden: list[str],
                       permitted: list[str]) -> tuple[CountResult | None, CountResult | None]:
    """Contract only; implemented by rlsentry.probe.read.observation_counts. Pure (ADR-040).

    Splits one VisibleResult back into the two CountResults read_cell / read_findings expect:
    for each of forbidden, permitted: [] → None; else CountResult(queried=len(list),
    status=res.status, total=len(set(res.visible) & set(list)) if res.visible is not None
    else None, curl=res.curl). res None with a non-empty list → ValueError.
    """
    raise NotImplementedError


# --- probe/verdict.py -----------------------------------------------------------------------

def split_known(expected: ExpectedAccess, rows: list[KnownRow],
                user_ids: Mapping[Role, str]) -> tuple[list[str], list[str]]:
    """Contract only; implemented by rlsentry.probe.verdict.split_known. Pure.

    (forbidden pks, permitted pks) for expected.role, in input order: a row is permitted iff
    row_permitted(expected.scope, actor_id, owner_id, row.public) where actor_id is None for
    anon and user_ids.get(role) otherwise, and owner_id = user_ids.get(row.owner).
    """
    raise NotImplementedError


def read_cell(obs: ReadObservation) -> ProbeResult:
    """Contract only; implemented by rlsentry.probe.verdict.read_cell. Pure.

    target/role from obs, op SELECT. evidence_curl = forbidden.curl, else permitted.curl, else
    "". First matching rule:
    1. obs.expected.is_review → INCONCLUSIVE, known_rows_checked 0,
       reason = obs.expected.review_reason.
    2. obs.forbidden is None → INCONCLUSIVE, 0, reason = obs.note or
       "no known row outside the expected scope".
    3. forbidden.status in (200, 206) and forbidden.total is not None and
       forbidden.total <= forbidden.queried → ALLOWED if total > 0 else DENIED;
       known_rows_checked = forbidden.queried; http_status = forbidden.status; reason states
       "<total>/<queried> known rows outside the expected scope are visible".
    4. otherwise INCONCLUSIVE, 0, http_status = forbidden.status, reason names the status
       (or "no response") and that no row count was obtained — a 401/403/404/400 is never
       read as "denied": HEAD has no body to tell a privilege error from a bad JWT or filter,
       and a total above `queried` means the filter was not applied (ADR-023 #3).
    """
    raise NotImplementedError


# --- probe/diff.py (FR-10) ------------------------------------------------------------------

def read_findings(target: Target, obs: ReadObservation, cell: ProbeResult) -> list[Finding]:
    """Contract only; implemented by rlsentry.probe.diff.read_findings. Pure.

    finding = actual − expected (SPEC §5 M3 差分). Each Finding has target=target.name,
    role=cell.role, op=SELECT, probes=[cell], id=finding_id(...), evidence and severity from
    RULES unless stated:
    - cell ALLOWED → rule = read_rule(target.kind, cell.role), severity =
      read_severity(rule, target.columns), evidence confirmed.
    - cell INCONCLUSIVE → NO_OWNER_COLUMN if obs.expected.is_review else INCONCLUSIVE_CELL.
    - obs.permitted with status in (200, 206) and total not None:
      total < queried → EXPECTED_ACCESS_DENIED (functional hint, never a vulnerability);
      cell.role is ANON and total > 0 and any target column is_sensitive_column →
      SENSITIVE_COLUMN_PUBLIC.
    DENIED and NOT_TESTED cells alone produce nothing.
    """
    raise NotImplementedError


def target_findings(target: Target) -> list[Finding]:
    """Contract only; implemented by rlsentry.probe.diff.target_findings. Pure.

    [INFERRED_TARGET finding (target=name, role=None, op=None, no probes)] when
    target.confidence == "inferred", else [].
    """
    raise NotImplementedError


# --- probe/run.py (Probe stage, reads only in MS2) -----------------------------------------

async def probe(client: SafeClientContract, supabase_url: str, anon_key: str,
                targets: list[Target], sessions: Sessions, policy: ExpectedPolicy,
                profile: Profile) -> tuple[AccessMatrix, list[Finding]]:
    """Contract only; implemented by rlsentry.probe.run.probe (Probe protocol, MS2 subset).

    For each target in input order:
    1. owner/public columns = resolve_expected(policy, name, SELECT, USER_A, columns) fields;
       known = collect_known_rows(...) once per target.
    2. For each role in PROBE_ROLES: if role is not ANON and has no token → NOT_TESTED cell,
       known 0, reason sessions.missing.get(role, "no session"), evidence "", no findings.
       Else expected = resolve_expected(policy, name, SELECT, role, columns) and:
       - expected.is_review → observation with nothing sent;
       - len(primary_key) != 1 → nothing sent, note "needs a single-column primary key";
       - else (forbidden, permitted) = split_known(...); when either is non-empty, ONE
         visible_pks call over forbidden + permitted (that order, duplicates dropped) and
         (obs.forbidden, obs.permitted) = observation_counts(...) (ADR-040: one request per
         role and target; MS2–MS5 sent a HEAD count per list); note "no known row outside
         the expected scope of <role>" plus the KnownRows notes when forbidden is empty.
       cell = read_cell(obs); findings += read_findings(target, obs, cell).
    3. Write cells (SPEC §5 M3 writes; FR-09; ADR-029, revised in the ADR-029 補記):
       - audit → for each op in WRITE_OPS and role in PROBE_ROLES a NOT_TESTED cell, known 0,
         evidence "", reason AUDIT_WRITE_REASON. No request ever leaves in audit (NFR-01).
       - dev/ci → the write path runs ONLY for targets with kind == "table"; an RPC or a view
         gets NOT_TESTED write cells (reason WRITE_NO_OWNER_REASON) and no request (a write to
         an RPC path is refused by the gate, ADR-014 #3). For a table: pick
         text_column = pick_text_column(target, owner column, public column) (ADR-034 補記).
         For every plan in plan_writes(expected_by_op, user_ids, tokens, text_column):
         if plan.op is INSERT, work = None; else work = seed_work_row(target, plan.work_owner,
         text_column, ...) — a FRESH canary created just for this probe, so a destructive write
         never corrupts another probe's row (ADR-029 補記). work is None (seeding refused) →
         NOT_TESTED cell, reason from the seed note ("work row could not be seeded"), nothing
         else sent. Otherwise send_write + read_back (immediately, before the next probe) build
         a WriteObservation; cell = write_cell(obs); findings += write_findings(...). A
         (role, op) pair with no plan yields one NOT_TESTED cell (WRITE_NOT_FORBIDDEN_REASON /
         WRITE_NO_OWNER_REASON), so the matrix keeps a cell per (role, op). EVERY canary the
         probe created — each work row AND each INSERT canary whose POST returned 2xx (its
         new_pk) — is collected into one list; cleanup_seeded(...) deletes them at the end and
         its return (rows still present) becomes CLEANUP_FAILED findings (cleanup_findings). No
         canary is ever left without a CLEANUP_FAILED finding (SPEC §5 M3 清理; never leave data
         silently).
       - A role without a token still yields NOT_TESTED write cells (reason from
         sessions.missing), no request.
       - WriteRefused (ADR-041; MS3 approval note 1): if any request of a table's write path
         raises WriteRefused (the gate refused it before sending: dev against a remote host,
         ci host not in write_hosts), that table's write path stops and EVERY (role, op)
         write cell of the table is INCONCLUSIVE, known 0, evidence "", reason
         WRITE_REFUSED_REASON + ": " + str(exc) (the gate message names profile, method and
         host only). Canaries created before the refusal still go to cleanup_seeded; a
         WriteRefused there turns the remaining rows into CLEANUP_FAILED findings. No other
         finding is added for refused cells, and the scan continues with the next target.
       MS3 does NOT call seed_known_rows: reads use collect_known_rows on existing rows (as in
       MS2). dev/ci read-seeding of empty targets (SPEC "dev／ci 植入已知資料") and the L03
       user_metadata escalation read pass both need inputs probe() does not receive (a re-login
       needs the password) and are deferred to the MS6 pipeline (ADR-029 補記).
    4. findings += target_findings(target).
    Cells in target order, then per role the SELECT cell, then the write cells in WRITE_OPS
    order; findings deduplicated by id, first occurrence kept. In audit only GET/HEAD and the
    login POST are sent; in dev/ci the only writes are to canary rows (read-seed, work and
    INSERT canaries) and their cleanup.
    """
    raise NotImplementedError


# ============================================================================================
# --- M3 writes (FR-09; dev/ci only; ADR-029) ------------------------------------------------
# ============================================================================================

WRITE_OK_STATUS: frozenset[int] = frozenset({200, 201, 204, 206})
"""Write statuses from which the read-back decides the verdict. 401/403 is a policy denial;
anything else (400 NOT NULL, 409, 5xx, transport error) is inconclusive, not denied (ADR-029
補記): the scanner may simply have failed to build a valid canary row."""

CANARY_PREFIX = "rlsentry_canary_"
"""Every value the write probe writes starts with this, so a human (or cleanup) can spot a
leftover probe row. The marker is the only non-key value RLSentry ever writes, and it never
contains real user data (CLAUDE.md)."""

CLEANUP_FAILED_REASON = "a seeded canary row could not be deleted by its owner"
WRITE_NOT_FORBIDDEN_REASON = "the expected policy permits this write for this role (not probed)"
WRITE_NO_SEED_REASON = "no seeded row and reader available to probe this write safely"
WRITE_NO_OWNER_REASON = "needs a single-column primary key and an owner column to seed canaries"


FILL_TEXT_FORMATS: frozenset[str] = frozenset({"text", "character varying", "character", "citext"})
FILL_INT_FORMATS: frozenset[str] = frozenset({"smallint", "integer", "bigint"})
FILL_NUM_FORMATS: frozenset[str] = frozenset({"numeric", "real", "double precision"})
FILL_TIME_FORMATS: frozenset[str] = frozenset({"timestamp with time zone",
                                               "timestamp without time zone"})
SEED_UNFILLABLE_REASON = "required column without a fillable type (ADR-034)"


def fill_required(target: Target, owner_id: str, preset: Collection[str]) -> dict[str, Any] | None:
    """Contract only; implemented by rlsentry.probe.fill.fill_required. Pure apart from fresh
    uuid4 / clock values (ADR-034; MS3 approval note 1: L01, L05).

    Values for every column of target.required that is not in `preset` (the columns the caller
    already sets: pk, owner, public, text), in target.required order, chosen by
    target.column_formats[column]:
      "uuid" → owner_id (the row's owner: Supabase uuid columns are almost always user
               references, and policies often require them to equal auth.uid(), e.g. L05
               created_by);
      FILL_TEXT_FORMATS → CANARY_PREFIX + uuid4 hex;  FILL_INT_FORMATS → 0;
      FILL_NUM_FORMATS → 0;  "boolean" → False;  FILL_TIME_FORMATS → datetime.now(UTC)
      .isoformat();  "date" → date.today().isoformat();  "json"/"jsonb" → {}.
    Returns None when any such column has no format or another format (enum, array, …): the
    row cannot be built honestly, so the caller sends nothing (the cell stays not_tested or
    inconclusive, never a false verdict). No required column outside preset → {}."""
    raise NotImplementedError


def pick_text_column(target: Target, owner_column: str | None,
                     public_column: str | None) -> str | None:
    """Contract only; implemented by rlsentry.probe.run.pick_text_column. Pure (ADR-034 補記).

    The column the write probe puts its CANARY_PREFIX marker into: the first column of
    target.columns (in order) that is not in target.primary_key, not owner_column, not
    public_column, and — when target.column_formats has an entry for it — whose format is in
    FILL_TEXT_FORMATS. A column without a format entry is still eligible (no type information:
    MS3 behaviour, e.g. bundle- or policy-discovered targets). None when no column qualifies.
    Why: a canary string written into a uuid column (L05 created_by) fails with 400, so the
    work row was never seeded and the write cells stayed not_tested."""
    raise NotImplementedError


class SeededRow(_Strict):
    """A canary row the write probe created with its owner's token, to probe and then delete.

    The probe only ever mutates rows it seeded, so it is always the owner and can clean up
    (SPEC §5 M3 清理). `text_column` is the mutable text column the marker went into (used by
    UPDATE value probes); None when the table has no such column (then only transfer/delete
    probes use the row)."""

    target: str
    pk: str
    owner: Role                 # the test user whose token created and owns the row
    marker: str                 # CANARY_PREFIX + uuid4 hex
    public: bool = False
    text_column: str | None = None


class WritePlan(_Strict):
    """One forbidden write worth attempting, chosen by plan_writes from the expected policy.
    `reader` is the identity that can observe the forbidden end state. UPDATE/DELETE plans name
    `work_owner`: run() seeds a FRESH canary owned by that role just for this probe (ADR-029
    補記), so a destructive write never corrupts another probe's row."""

    op: Op                      # INSERT / UPDATE / DELETE
    actor: Role                 # the role attempting the write
    rule: str                   # write_rule(actor, op): ANON_WRITE or CROSS_TENANT_WRITE
    reader: Role                # verifies the end state (INSERT/transfer: new_owner; else owner)
    work_owner: Role | None = None  # owner of the fresh work row (UPDATE/DELETE); None for INSERT
    new_owner: Role | None = None   # owner the INSERT sets, or the transfer target (UPDATE)
    text_column: str | None = None  # column an UPDATE value-change sets; None = transfer/ins/del
    transfer: bool = False      # UPDATE that moves ownership of the work row to new_owner


class WriteAttempt(_Strict):
    """The single write request of a plan. new_pk / new_value are what send_write chose, so the
    read-back filter and cleanup can find exactly what was written."""

    status: int | None          # None: transport error, nothing received
    curl: str                   # reproduction command, secrets masked
    new_pk: str | None = None   # INSERT: the canary's primary key (to read back and clean up)
    new_value: str | None = None  # UPDATE value-change: the marker written (to read back)


class ReadBack(_Strict):
    """End-state check by the reader. present is None when the count is untrustworthy (a non
    2xx, or no parsable Content-Range): then the write cell is inconclusive, never denied."""

    present: bool | None
    status: int | None
    curl: str


class WriteObservation(_Strict):
    """Everything write_cell and write_findings need for one write cell; built by probe()."""

    target: str
    role: Role
    op: Op
    plan: WritePlan | None = None     # None: nothing attempted (see note)
    attempt: WriteAttempt | None = None
    after: ReadBack | None = None     # end-state read-back by plan.reader
    note: str | None = None           # why nothing was attempted / could not be judged


# The write rule selector write_rule lives in rlsentry.contracts.rules (next to read_rule);
# plan_writes and write_findings import it from there.


# --- probe/verdict.py (pure) ----------------------------------------------------------------

def forbidden_write(scope: object, actor_id: str | None, owner_id: str | None,
                    is_public: bool) -> bool:
    """Contract only; implemented by rlsentry.probe.verdict.forbidden_write. Pure.

    True iff the expected `scope` (a RowScope) does NOT permit `actor_id` to own/touch a row
    owned by `owner_id` (row_permitted is False). This is the end state the write would create:
    for INSERT/transfer, owner_id is the new owner; for UPDATE value / DELETE, owner_id is the
    current owner. Only forbidden writes are attempted, so a confirmed effect is a vulnerability.
    """
    raise NotImplementedError


def write_outcome(op: Op, after_present: bool | None) -> bool | None:
    """Contract only; implemented by rlsentry.probe.verdict.write_outcome. Pure.

    Did the forbidden write take effect, judged only by the read-back of the end state? The
    initial state is fixed by construction (a fresh canary pk/value, an own row, or a row we
    just seeded), so only the after-state is read. None (untrustworthy read-back) → None.
    DELETE: took effect iff the row is now absent (after_present is False). INSERT and UPDATE
    (value or transfer): took effect iff the end state is now present (after_present is True).
    """
    raise NotImplementedError


def write_cell(obs: WriteObservation) -> ProbeResult:
    """Contract only; implemented by rlsentry.probe.verdict.write_cell. Pure.

    target/role/op from obs. evidence_curl = obs.attempt.curl if an attempt was made, else "".
    http_status = obs.attempt.status throughout. Classify by the write's HTTP status, because a
    non-2xx can be a policy denial OR our own invalid request, and only the former is "denied":
    1. obs.plan is None → NOT_TESTED, known 0, reason obs.note or WRITE_NOT_FORBIDDEN_REASON.
    2. obs.attempt is None or obs.after is None → INCONCLUSIVE, 0, reason obs.note or
       "write not sent".
    3. obs.attempt.status in (401, 403) → DENIED, known 1: the policy refused the write
       (PostgREST 403 / Postgres 42501 WITH CHECK). reason names the status.
    4. obs.attempt.status in WRITE_OK_STATUS (200, 201, 204, 206) → took =
       write_outcome(obs.op, obs.after.present); took None → INCONCLUSIVE, 0 (end state could
       not be read back, reason names obs.after.status); took True → ALLOWED, known 1; took
       False → DENIED, known 1. A 2xx with no verified effect is DENIED, never ALLOWED (SPEC §5
       M3: USING filters an UPDATE/DELETE to 0 rows yet PostgREST answers 2xx).
    5. any other status, or None → INCONCLUSIVE, 0: the write was not accepted for a
       non-authorization reason (e.g. 400 NOT NULL / bad input, 409 conflict, 5xx, or a
       transport error — our canary could not be built or the server erred), so denial cannot
       be concluded. reason names the status (or "no response").
    So an INSERT that fails because the scanner could not satisfy a NOT NULL / typed column it
    does not know about is inconclusive, never a false "denied" (ADR-029 補記).
    """
    raise NotImplementedError


# --- probe/diff.py (pure; FR-10) ------------------------------------------------------------

def write_findings(target: Target, obs: WriteObservation, cell: ProbeResult) -> list[Finding]:
    """Contract only; implemented by rlsentry.probe.diff.write_findings. Pure.

    - cell ALLOWED → one Finding, rule = obs.plan.rule, evidence/severity from RULES[rule],
      target=target.name, role=cell.role, op=cell.op, probes=[cell].
    - otherwise [] (a DENIED/INCONCLUSIVE/NOT_TESTED write is not a vulnerability; inconclusive
      writes are visible in the matrix, not as findings — they never claim "safe").
    """
    raise NotImplementedError


def cleanup_findings(target: Target, failures: list[SeededRow]) -> list[Finding]:
    """Contract only; implemented by rlsentry.probe.diff.cleanup_findings. Pure.

    One CLEANUP_FAILED finding per seeded row that cleanup_seeded could not delete (SPEC §5 M3:
    "刪不掉就記錄並提示"): target=target.name, role=row.owner, op=Op.DELETE, no probes. Empty
    list → []. CLEANUP_FAILED is a non-vulnerability Review rule (it means leftover probe data,
    not an access flaw).
    """
    raise NotImplementedError


# --- probe/seed.py (FR-09; dev/ci) ----------------------------------------------------------

async def seed_known_rows(client: SafeClientContract, supabase_url: str, anon_key: str,
                          target: Target, owner_column: str | None, public_column: str | None,
                          text_column: str | None, sessions: Sessions) -> tuple[list[SeededRow], list[str]]:
    """Contract only; implemented by rlsentry.probe.seed.seed_known_rows. ⚠ sends POSTs.

    Returns ([], [note]) without a request when len(target.primary_key) != 1 or owner_column is
    None (note WRITE_NO_OWNER_REASON). Otherwise, for each role in USER_ROLES that has a token
    and a user id, POST <base> (RPC is never seeded) one private canary row owned by that role,
    and — when public_column is set — one public canary row, with headers apikey/Authorization
    (that user's token) and `Prefer: return=minimal`. The JSON body sets: the primary key to a
    new uuid4 str; owner_column to the user's id; public_column (if any) to False then True;
    text_column (if any) to CANARY_PREFIX + uuid4 hex; plus fill_required(target, <that user's
    id>, <the keys already set>) (ADR-034). When fill_required returns None, that user's rows
    are not sent and the note "<role>: " + SEED_UNFILLABLE_REASON is added (role value).
    A 2xx (or a readable-back pk) adds a
    SeededRow; any other response adds the note "<role>: seed HTTP <status>" and no row (the
    scanner never fabricates a seed it could not create). The marker and pk let read_back and
    cleanup find exactly this row.
    """
    raise NotImplementedError


# --- probe/write.py (FR-09; dev/ci) ---------------------------------------------------------

def plan_writes(expected_by_op: Mapping[tuple[Op, Role], ExpectedAccess],
                user_ids: Mapping[Role, str], tokens: Mapping[Role, str],
                text_column: str | None) -> list[WritePlan]:
    """Contract only; implemented by rlsentry.probe.write.plan_writes. Pure.

    The forbidden writes worth attempting, in (op INSERT→UPDATE→DELETE, actor PROBE_ROLES)
    order. actor_id = None for anon else user_ids.get(actor). The row each UPDATE/DELETE needs
    is created at probe time (work_owner), not here, so planning depends only on the policy and
    the identities. A plan is produced only when its reader AND its work_owner (if any) have a
    token (else the write could not be set up or verified). For each op and actor:
    - INSERT: new_owner = the first USER_ROLE != actor whose id and token exist (anon→user_a,
      user_a→user_b, user_b→user_a). reader = new_owner, work_owner None. Add iff
      forbidden_write(expected_by_op[(INSERT, actor)].scope, actor_id, user_ids[new_owner], False).
    - UPDATE / DELETE cross-tenant: work_owner = the first USER_ROLE != actor with id + token
      (the owner of a fresh row the actor then tries to touch). reader = work_owner. Add iff
      forbidden_write(scope, actor_id, user_ids[work_owner], False). For UPDATE this is the
      value-change plan: WritePlan.text_column = the given `text_column` NAME; it is skipped
      when `text_column` is None (the table has no mutable text column).
    - UPDATE transfer: actor is a user (actor_id present); work_owner = actor (its own fresh
      row); new_owner = the other user with id + token; reader = new_owner, transfer=True. Add
      iff forbidden_write(expected_by_op[(UPDATE, actor)].scope, actor_id, user_ids[new_owner],
      False) — the moved row would be owned by someone the policy does not allow.
    At most one plan per (op, actor, kind); every plan carries rule = write_rule(actor, op).
    An expected scope that is_review (unknown owner) yields no plan for that op/actor.
    """
    raise NotImplementedError


async def seed_work_row(client: SafeClientContract, supabase_url: str, anon_key: str,
                        target: Target, owner: Role, text_column: str | None,
                        owner_column: str, sessions: Sessions) -> SeededRow | None:
    """Contract only; implemented by rlsentry.probe.write.seed_work_row. ⚠ sends one POST.

    Create one FRESH private canary owned by `owner` (its own token), exactly as
    seed_known_rows builds a private row (new uuid pk, owner_column = owner id, text_column =
    CANARY_PREFIX + uuid4 hex when given, plus fill_required(target, owner id, the keys already
    set); fill_required None → return None without a request, ADR-034),
    `Prefer: return=minimal`. A 2xx returns the SeededRow
    (so the write probe has an isolated row and cleanup can delete it); any other response or a
    missing token/id returns None (the write cell then becomes NOT_TESTED, never a false
    verdict). This is what makes every destructive probe independent (ADR-029 補記).
    """
    raise NotImplementedError


async def send_write(client: SafeClientContract, supabase_url: str, anon_key: str,
                     target: Target, plan: WritePlan, work: SeededRow | None,
                     owner_column: str, sessions: Sessions) -> WriteAttempt:
    """Contract only; implemented by rlsentry.probe.write.send_write. ⚠ sends one write.

    Uses apikey + the ACTOR's token and `Prefer: return=minimal` (ADR-029 #2). pk column =
    target.primary_key[0]. `work` is the fresh row seed_work_row made for this probe (None for
    INSERT).
    - INSERT: POST <base> a private canary body (new uuid pk, owner_column = new_owner's id,
      text_column CANARY_PREFIX+uuid when the target has one, plus fill_required(target,
      fill_id, the keys already set), ADR-034) where fill_id = the ACTOR's id when the actor is
      a user with an id (an attacker sets the other uuid columns, e.g. created_by, to itself;
      ADR-034 補記 2, MS4 audit P1-1), else new_owner's id (anon has no id); the owner column
      still gets new_owner's id; new_pk = that uuid; new_value None.
      fill_required None → no request: WriteAttempt(status=None, curl="") (the cell becomes
      inconclusive, never denied).
    - UPDATE value-change: PATCH <base>?<pk>=eq.<work.pk> with {plan.text_column:
      CANARY_PREFIX+uuid}; new_value = that marker; new_pk None.
    - UPDATE transfer: PATCH <base>?<pk>=eq.<work.pk> with {owner_column: new_owner's id}.
    - DELETE: DELETE <base>?<pk>=eq.<work.pk>.
    Returns WriteAttempt(status, curl, new_pk, new_value). Transport error → status None.
    curl = curl_command(method, final URL, headers). RPC targets are never written (plan_writes
    does not produce them). The request still passes through the SafeClient write gate, so audit
    could never reach here (NFR-01).
    """
    raise NotImplementedError


async def read_back(client: SafeClientContract, supabase_url: str, anon_key: str,
                    target: Target, reader_token: str, filters: Mapping[str, str]) -> ReadBack:
    """Contract only; implemented by rlsentry.probe.write.read_back. Never downloads a row.

    One `HEAD <base>?select=<pk>&<each filter>` with `Prefer: count=exact`, headers apikey +
    reader_token. present = (total > 0) when status in (200, 206) and Content-Range gives a
    total (CONTENT_RANGE_TOTAL_RE), else present None. `filters` are PostgREST filter params
    that describe the forbidden end state (built by after_filter): the canary pk for INSERT and
    DELETE; pk plus the new value for an UPDATE value-change; pk plus the new owner id for a
    transfer. curl = curl_command("HEAD", final URL, headers).
    """
    raise NotImplementedError


def after_filter(plan: WritePlan, attempt: WriteAttempt, work: SeededRow | None, pk_col: str,
                 owner_col: str | None, user_ids: Mapping[Role, str]) -> dict[str, str]:
    """Contract only; implemented by rlsentry.probe.write.after_filter. Pure.

    PostgREST filter params that detect the forbidden end state after the write (`work` is the
    probe's work row; None for INSERT):
    - INSERT: {pk_col: "eq.<attempt.new_pk>"}.
    - DELETE: {pk_col: "eq.<work.pk>"} (present afterwards = NOT deleted).
    - UPDATE value: {pk_col: "eq.<work.pk>", plan.text_column: "eq.<attempt.new_value>"}.
    - UPDATE transfer: {pk_col: "eq.<work.pk>", owner_col: "eq.<user_ids[plan.new_owner]>"}.
    Values use plain eq.; the pk/owner are uuids and the marker has no PostgREST metacharacters.
    """
    raise NotImplementedError


# --- probe/cleanup.py (FR-09 清理) ----------------------------------------------------------

async def cleanup_seeded(client: SafeClientContract, supabase_url: str, anon_key: str,
                         target: Target, seeded: list[SeededRow],
                         sessions: Sessions) -> list[SeededRow]:
    """Contract only; implemented by rlsentry.probe.cleanup.cleanup_seeded. ⚠ sends DELETEs.

    For every SeededRow (and every canary a successful INSERT probe created, passed in as a
    SeededRow owned by its new owner), `DELETE <base>?<pk>=eq.<row.pk>` with the OWNER's token
    and `Prefer: return=minimal`, then one HEAD count as the owner to confirm the row is gone.
    Returns the rows still present (or whose delete/confirm failed): these become CLEANUP_FAILED
    findings (SPEC §5 M3). Each identity deletes only rows it owns, so cleanup is itself a
    read-your-own-write, never a cross-tenant action.
    """
    raise NotImplementedError


# --- probe/metadata.py (L03 USER_METADATA_ESCALATION; dev/ci) -------------------------------

async def escalate_user_metadata(client: SafeClientContract, supabase_url: str, anon_key: str,
                                  token: str) -> tuple[str, bool]:
    """Contract only; implemented by rlsentry.probe.metadata.escalate_user_metadata. ⚠ writes.

    The L03 technique: a user can set its own user_metadata, which some policies trust. `PUT
    <supabase_url>/auth/v1/user` with apikey + Bearer token and body {"data": {"role": "admin"}},
    then re-login is the caller's job. Returns (status_text, changed) where changed is True iff
    the PUT returned 200. This writes only to the test user's OWN Auth record on the target; it
    is reverted by restore_user_metadata after the escalation read pass. The write still goes
    through the SafeClient gate (allowed on localhost in dev/ci; refused in audit).
    """
    raise NotImplementedError


async def restore_user_metadata(client: SafeClientContract, supabase_url: str, anon_key: str,
                                 token: str) -> bool:
    """Contract only; implemented by rlsentry.probe.metadata.restore_user_metadata. ⚠ writes.

    `PUT <supabase_url>/auth/v1/user` with body {"data": {"role": None}}, clearing the role the
    escalation set, so the probe leaves the test account as it found it (SPEC §5 M3 清理).
    Returns True iff the PUT returned 200. Never raises httpx.HTTPError (a transport error returns
    False): the caller must be able to report a failed restore instead of losing it (MS6 audit,
    ADR-047). Known limit: the role is cleared to null, not set back to an earlier value.
    """
    raise NotImplementedError


# --- probe/seed_pass.py (dev/ci read seeding; ADR-042, ADR-029 補記 2) ------------------------

async def seed_reads(client: SafeClientContract, supabase_url: str, anon_key: str,
                     targets: list[Target], policy: ExpectedPolicy,
                     sessions: Sessions) -> tuple[list[SeededRow], list[str]]:
    """Contract only; implemented by rlsentry.probe.seed_pass.seed_reads. ⚠ sends POSTs.

    SPEC §4 step 4 ("dev／ci 植入已知擁有者的資料"): before probe(), give every user a known
    row in each table so reads can be judged even where a user has no data of its own. The
    seeded rows are owned by the seeding user, so collect_known_rows inside probe() finds them
    like any other own row. Called by run_scan in dev/ci only, never in audit.
    For each target in order with kind == "table" and len(primary_key) == 1:
    e = resolve_expected(policy, name, Op.SELECT, Role.USER_A, tuple(columns));
    rows, notes = seed_known_rows(client, supabase_url, anon_key, target, e.owner_column,
    e.public_column, run.pick_text_column(target, e.owner_column, e.public_column), sessions);
    collect rows; each note becomes "<target>: <note>". A WriteRefused stops the pass: the note
    "read seeding refused by the safety gate: <str(exc)>" is added and no further target is
    seeded. An httpx.HTTPError for one target → note "<target>: seeding failed (<exception
    class>)" and the pass continues; rows already seeded are always returned (ADR-047: a row the
    caller never hears about could never be cleaned up). Returns (all rows, notes).
    """
    raise NotImplementedError


async def cleanup_reads(client: SafeClientContract, supabase_url: str, anon_key: str,
                        targets: list[Target], seeded: list[SeededRow],
                        sessions: Sessions) -> list[Finding]:
    """Contract only; implemented by rlsentry.probe.seed_pass.cleanup_reads. ⚠ sends DELETEs.

    For each target (input order) that has rows in `seeded` (matched by SeededRow.target ==
    target.name): left = cleanup_seeded(client, ..., target, those rows, sessions); a
    WriteRefused or httpx.HTTPError makes left = those rows, and the next target is still
    cleaned (ADR-047). Returns the concatenated cleanup_findings(target,
    left) (CLEANUP_FAILED; ADR-029 #8). Rows of a target name absent from `targets` are
    reported with a Target(name=<name>, kind="table", discovered_by="policy",
    confidence="unknown") so a leftover is never silent.
    """
    raise NotImplementedError


# --- probe/escalation.py (L03 USER_METADATA_ESCALATION; dev/ci; ADR-042) ----------------------

ESCALATION_REASON = "after setting its own user_metadata.role=admin and logging in again"


async def escalation_pass(client: SafeClientContract, supabase_url: str, anon_key: str,
                          targets: list[Target], policy: ExpectedPolicy, sessions: Sessions,
                          users: list[TestUser], env: Mapping[str, str],
                          matrix: AccessMatrix) -> tuple[list[Finding], list[str]]:
    """Contract only; implemented by rlsentry.probe.escalation.escalation_pass. ⚠ writes Auth.

    The L03 technique (ADR-029 #9), wired in now that the caller has the passwords needed to
    log in again (MS3 approval note 1). Called by run_scan in dev/ci only. Per role in
    USER_ROLES, in that order:
    1. Skip silently unless the role has a token, a user id, a TestUser in `users` and a
       non-empty env[password_env].
    2. candidates = targets with len(primary_key) == 1 whose matrix cell (target, role,
       SELECT) is DENIED (only a verified "cannot see" can show that metadata changed it; an
       ALLOWED cell is already reported, an inconclusive one proves nothing), whose
       e = resolve_expected(policy, name, SELECT, role, columns) is not review, and whose
       forbidden list is non-empty: known = collect_known_rows(..., e.owner_column,
       e.public_column, sessions) with the ORIGINAL sessions; forbidden = split_known(e,
       known.rows, sessions.user_ids)[0]; then a FRESH baseline with the ORIGINAL token,
       res0 = visible_pks(client, ..., target, sessions.tokens[role], forbidden): untrustworthy
       (visible None or status not 200/206) → not a candidate; hidden = [pk for pk in forbidden
       if pk not in res0.visible] (input order); hidden empty → not a candidate. The baseline is
       re-measured here because the write probes that ran after the matrix was built may have
       changed which rows the role sees (e.g. an L05-style owner transfer of a canary the role
       created; ADR-042 補記). No candidate → nothing is written for this role.
    3. (status, changed) = escalate_user_metadata(client, ..., sessions.tokens[role]).
       Not changed → note "<role>: user_metadata not changed (<status>)", next role.
       An httpx.HTTPError from it → note "<role>: escalation request failed (<exception class>)",
       then restore anyway (the server may have applied it; ADR-047), then next role.
    4. try: token2, _ = login(client, ..., user.email, password); for each candidate:
       res = visible_pks(client, ..., target, token2, hidden); trustworthy (res.visible not
       None, status 200/206) and n = len(res.visible) > 0 → one Finding: rule
       USER_METADATA_ESCALATION, evidence/severity from RULES, target=name, role, op SELECT,
       probes=[ProbeResult(target=name, role, op=SELECT, outcome=ALLOWED,
       known_rows_checked=len(hidden), reason=ESCALATION_REASON + f": {n}/{len(hidden)}
       known rows outside the expected scope are visible", http_status=res.status,
       evidence_curl=res.curl)], id=finding_id(name, role, SELECT, rule).
       LoginFailed → note "<role>: re-login after escalation failed (<exc>)"; an httpx.HTTPError
       inside this try → note "<role>: escalation check failed (<exception class>)".
       finally: restore_user_metadata(client, ..., token2 if obtained else the original
       token) — ALWAYS, so the test account is left as found (SPEC §5 M3 清理). A False return →
       note "<role>: user_metadata restore failed; the test account may still carry role=admin
       and must be cleared by hand" (ADR-047). escalation_pass itself never raises
       httpx.HTTPError.
    A WriteRefused from escalate_user_metadata → note "user_metadata escalation refused by the
    safety gate: <str(exc)>" and the pass stops (nothing was changed). Returns (findings, notes).
    The matrix is not modified: escalation findings carry their own ProbeResult.
    """
    raise NotImplementedError
