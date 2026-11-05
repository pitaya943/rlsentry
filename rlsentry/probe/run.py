"""Probe stage (SPEC §5 M3, ADR-023): composes the read helpers into the access matrix.

Why: one place owns cell order, NOT_TESTED rules and finding deduplication, while every
request still goes through the caller's SafeClient. MS2 sends only GET and HEAD.
"""
from __future__ import annotations

from rlsentry.contracts.models import AccessMatrix, Finding, Op, Outcome, ProbeResult, Profile, Role, Target
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.probe import (
    AUDIT_WRITE_REASON,
    CANARY_PREFIX,
    FILL_TEXT_FORMATS,
    PROBE_ROLES,
    WRITE_NO_OWNER_REASON,
    WRITE_NOT_FORBIDDEN_REASON,
    WRITE_OPS,
    KnownRows,
    ReadObservation,
    SeededRow,
    Sessions,
    WriteObservation,
    WritePlan,
)
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.policy.resolve import resolve_expected
from rlsentry.probe.cleanup import cleanup_seeded
from rlsentry.probe.cross_tenant import collect_known_rows
from rlsentry.probe.diff import cleanup_findings, read_findings, target_findings, write_findings
from rlsentry.probe.read import count_visible
from rlsentry.probe.verdict import read_cell, split_known, write_cell
from rlsentry.probe.write import after_filter, plan_writes, read_back, seed_work_row, send_write

_PRIORITY = {Outcome.ALLOWED: 0, Outcome.INCONCLUSIVE: 1, Outcome.DENIED: 2, Outcome.NOT_TESTED: 3}


def _not_tested(target: str, role: Role, op: Op, reason: str) -> ProbeResult:
    return ProbeResult(target=target, role=role, op=op, outcome=Outcome.NOT_TESTED,
                       known_rows_checked=0, reason=reason, evidence_curl="")


def pick_text_column(target: Target, owner_column: str | None,
                     public_column: str | None) -> str | None:
    """Why: the canary marker must go into a text column; a string in a uuid column (L05
    created_by) fails with 400 and the work row is never seeded. Columns without type
    information stay eligible (MS3 behaviour)."""
    skip = {*target.primary_key, owner_column, public_column}
    for c in target.columns:
        if c in skip:
            continue
        fmt = target.column_formats.get(c)
        if fmt is None or fmt in FILL_TEXT_FORMATS:
            return c
    return None


async def _write_target(client: SafeClientContract, supabase_url: str, anon_key: str,
                        target: Target, sessions: Sessions, policy: ExpectedPolicy,
                        owner: str | None, public: str | None
                        ) -> tuple[list[ProbeResult], list[Finding]]:
    """Why: dev/ci write probing of one table; every canary created is cleaned up at the end."""
    name = target.name
    cols = tuple(target.columns)
    cells: list[ProbeResult] = []
    findings: list[Finding] = []
    if target.kind != "table" or len(target.primary_key) != 1 or owner is None:
        return [_not_tested(name, r, op, WRITE_NO_OWNER_REASON)
                for r in PROBE_ROLES for op in WRITE_OPS], findings
    text_column = pick_text_column(target, owner, public)
    expected = {(op, r): resolve_expected(policy, name, op, r, cols)
                for op in WRITE_OPS for r in PROBE_ROLES}
    plans = plan_writes(expected, sessions.user_ids, sessions.tokens, text_column)
    canaries: list[SeededRow] = []
    by_cell: dict[tuple[Role, Op], list[ProbeResult]] = {}
    for plan in plans:
        work: SeededRow | None = None
        if plan.op is not Op.INSERT:
            assert plan.work_owner is not None
            work = await seed_work_row(client, supabase_url, anon_key, target, plan.work_owner,
                                       text_column, owner, sessions)
            if work is None:
                by_cell.setdefault((plan.actor, plan.op), []).append(
                    _not_tested(name, plan.actor, plan.op, "work row could not be seeded"))
                continue
            canaries.append(work)
        cell = await _run_plan(client, supabase_url, anon_key, target, plan, work, owner,
                               sessions, canaries, findings)
        by_cell.setdefault((plan.actor, plan.op), []).append(cell)
    for role in PROBE_ROLES:
        for op in WRITE_OPS:
            got = by_cell.get((role, op))
            if got:
                cells.append(min(got, key=lambda c: _PRIORITY[c.outcome]))
            elif role is not Role.ANON and role not in sessions.tokens:
                cells.append(_not_tested(name, role, op, sessions.missing.get(role, "no session")))
            else:
                reason = (WRITE_NOT_FORBIDDEN_REASON if not expected[(op, role)].is_review
                          else WRITE_NO_OWNER_REASON)
                cells.append(_not_tested(name, role, op, reason))
    if canaries:
        left = await cleanup_seeded(client, supabase_url, anon_key, target, canaries, sessions)
        findings.extend(cleanup_findings(target, left))
    return cells, findings


async def _run_plan(client: SafeClientContract, supabase_url: str, anon_key: str, target: Target,
                    plan: WritePlan, work: SeededRow | None, owner: str, sessions: Sessions,
                    canaries: list[SeededRow], findings: list[Finding]) -> ProbeResult:
    attempt = await send_write(client, supabase_url, anon_key, target, plan, work, owner, sessions)
    if (plan.op is Op.INSERT and attempt.new_pk is not None and attempt.status is not None
            and 200 <= attempt.status < 300 and plan.new_owner is not None):
        canaries.append(SeededRow(target=target.name, pk=attempt.new_pk, owner=plan.new_owner,
                                  marker=CANARY_PREFIX))
    filters = after_filter(plan, attempt, work, target.primary_key[0], owner, sessions.user_ids)
    after = await read_back(client, supabase_url, anon_key, target,
                            sessions.tokens[plan.reader], filters)
    obs = WriteObservation(target=target.name, role=plan.actor, op=plan.op, plan=plan,
                           attempt=attempt, after=after)
    cell = write_cell(obs)
    findings.extend(write_findings(target, obs, cell))
    return cell


async def _observe(client: SafeClientContract, supabase_url: str, anon_key: str, target: Target,
                   sessions: Sessions, policy: ExpectedPolicy, known: KnownRows,
                   role: Role) -> ReadObservation:
    expected = resolve_expected(policy, target.name, Op.SELECT, role, tuple(target.columns))
    obs = ReadObservation(target=target.name, role=role, expected=expected)
    if expected.is_review:
        return obs
    if len(target.primary_key) != 1:
        obs.note = "needs a single-column primary key"
        return obs
    forbidden, permitted = split_known(expected, known.rows, sessions.user_ids)
    token = sessions.tokens[role]
    if forbidden:
        obs.forbidden = await count_visible(client, supabase_url, anon_key, target, token, forbidden)
    if permitted:
        obs.permitted = await count_visible(client, supabase_url, anon_key, target, token, permitted)
    if not forbidden:
        note = f"no known row outside the expected scope of {role.value}"
        obs.note = "; ".join([note, *known.notes])
    return obs


async def probe(client: SafeClientContract, supabase_url: str, anon_key: str,
                targets: list[Target], sessions: Sessions, policy: ExpectedPolicy,
                profile: Profile) -> tuple[AccessMatrix, list[Finding]]:
    """Build the access matrix and findings for every target (reads only in MS2)."""
    cells: list[ProbeResult] = []
    findings: list[Finding] = []
    for target in targets:
        cols = tuple(target.columns)
        first = resolve_expected(policy, target.name, Op.SELECT, Role.USER_A, cols)
        known = await collect_known_rows(client, supabase_url, anon_key, target, first.owner_column,
                                         first.public_column, sessions)
        for role in PROBE_ROLES:
            if role is not Role.ANON and role not in sessions.tokens:
                cells.append(ProbeResult(target=target.name, role=role, op=Op.SELECT,
                                         outcome=Outcome.NOT_TESTED, known_rows_checked=0,
                                         reason=sessions.missing.get(role, "no session"),
                                         evidence_curl=""))
                continue
            obs = await _observe(client, supabase_url, anon_key, target, sessions, policy, known, role)
            cell = read_cell(obs)
            cells.append(cell)
            findings.extend(read_findings(target, obs, cell))
        if profile is Profile.AUDIT:
            cells.extend(_not_tested(target.name, r, op, AUDIT_WRITE_REASON)
                         for r in PROBE_ROLES for op in WRITE_OPS)
        else:
            wcells, wfindings = await _write_target(client, supabase_url, anon_key, target,
                                                    sessions, policy, first.owner_column,
                                                    first.public_column)
            cells.extend(wcells)
            findings.extend(wfindings)
        findings.extend(target_findings(target))
    seen: set[str] = set()
    unique: list[Finding] = []
    for f in findings:
        if f.id not in seen:
            seen.add(f.id)
            unique.append(f)
    return AccessMatrix(cells=cells), unique
