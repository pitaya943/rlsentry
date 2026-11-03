"""M3 Probe contracts for reads (SPEC §5 M3; FR-06, FR-07, FR-08, FR-10). Owned by the architect.

MS2 covers SELECT only; write probes (FR-09) arrive in MS3 and will extend this file.
Implementations live in rlsentry/probe/<file>.py (and rlsentry/rules/severity.py for the rule
functions in rlsentry.contracts.rules) with exactly these names and signatures.
Design decisions: ADR-023.

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
    3. For each op in WRITE_OPS and role in PROBE_ROLES: NOT_TESTED cell, known 0, evidence "",
       reason AUDIT_WRITE_REASON for audit, else WRITE_PENDING_REASON. No request.
    4. findings += target_findings(target).
    Cells in that order; findings deduplicated by id, first occurrence kept. Only GET and HEAD
    are sent (NFR-01 in every profile for MS2).
    """
    raise NotImplementedError
