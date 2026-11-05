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

from collections.abc import Mapping

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
       - else (forbidden, permitted) = split_known(...); count_visible for each non-empty
         list (forbidden first); note "no known row outside the expected scope of <role>"
         plus the KnownRows notes when forbidden is empty.
       cell = read_cell(obs); findings += read_findings(target, obs, cell).
    3. Write cells (SPEC §5 M3 writes; FR-09; ADR-029, revised in the ADR-029 補記):
       - audit → for each op in WRITE_OPS and role in PROBE_ROLES a NOT_TESTED cell, known 0,
         evidence "", reason AUDIT_WRITE_REASON. No request ever leaves in audit (NFR-01).
       - dev/ci → pick text_column = the first target column that is not the primary key, the
         owner column or the public column (a best-effort mutable column; None when none).
         For every plan in plan_writes(expected_by_op, user_ids, tokens, text_column is not None):
         if plan.op is INSERT, work = None; else work = seed_work_row(target, plan.work_owner,
         text_column, ...) — a FRESH canary created just for this probe, so a destructive write
         never corrupts another probe's row (ADR-029 補記). work is None (seeding refused) →
         NOT_TESTED cell, reason from the seed note, nothing else sent. Otherwise send_write +
         read_back (immediately, before the next probe) build a WriteObservation; cell =
         write_cell(obs); findings += write_findings(...). A (role, op) pair with no plan
         yields one NOT_TESTED cell (WRITE_NOT_FORBIDDEN_REASON / WRITE_NO_OWNER_REASON), so
         the matrix keeps a cell per (role, op). Every work row, every INSERT canary and the
         read-seed rows are collected and cleanup_seeded(...) deletes them at the end; leftovers
         become CLEANUP_FAILED findings (cleanup_findings, from its results).
       - A role without a token still yields NOT_TESTED write cells (reason from
         sessions.missing), no request.
       Read seeding: in dev/ci seed_known_rows(...) once per target adds canary rows to the
       READ known set (SPEC §5 M3 "dev／ci 植入已知資料"), so empty real targets (C04) become
       decidable; it never feeds the write probes.
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

CANARY_PREFIX = "rlsentry_canary_"
"""Every value the write probe writes starts with this, so a human (or cleanup) can spot a
leftover probe row. The marker is the only non-key value RLSentry ever writes, and it never
contains real user data (CLAUDE.md)."""

CLEANUP_FAILED_REASON = "a seeded canary row could not be deleted by its owner"
WRITE_NOT_FORBIDDEN_REASON = "the expected policy permits this write for this role (not probed)"
WRITE_NO_SEED_REASON = "no seeded row and reader available to probe this write safely"
WRITE_NO_OWNER_REASON = "needs a single-column primary key and an owner column to seed canaries"


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
    First match:
    1. obs.plan is None → NOT_TESTED, known 0, reason obs.note or WRITE_NOT_FORBIDDEN_REASON.
    2. obs.attempt is None or obs.after is None → INCONCLUSIVE, 0, reason obs.note or
       "write not sent".
    3. took = write_outcome(obs.op, obs.after.present). took is None → INCONCLUSIVE, 0,
       http_status obs.attempt.status, reason names that the end state could not be read back
       (obs.after.status). took True → ALLOWED; took False → DENIED; known_rows_checked = 1
       (the one seeded/canary row read back), http_status = obs.attempt.status.
    A 2xx write with no verified effect is therefore DENIED, never ALLOWED (SPEC §5 M3: USING
    filters an UPDATE/DELETE to 0 rows and PostgREST still answers 2xx).
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
    text_column (if any) to CANARY_PREFIX + uuid4 hex. A 2xx (or a readable-back pk) adds a
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
    CANARY_PREFIX + uuid4 hex when given), `Prefer: return=minimal`. A 2xx returns the SeededRow
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
      text_column CANARY_PREFIX+uuid when the target has one); new_pk = that uuid; new_value None.
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
                                 token: str) -> None:
    """Contract only; implemented by rlsentry.probe.metadata.restore_user_metadata. ⚠ writes.

    `PUT <supabase_url>/auth/v1/user` with body {"data": {"role": None}}, clearing the role the
    escalation set, so the probe leaves the test account as it found it (SPEC §5 M3 清理). Best
    effort: a non-200 is ignored (the caller already recorded the escalation).
    """
    raise NotImplementedError
