"""Probe stage (SPEC §5 M3, ADR-023): composes the read helpers into the access matrix.

Why: one place owns cell order, NOT_TESTED rules and finding deduplication, while every
request still goes through the caller's SafeClient. MS2 sends only GET and HEAD.
"""
from __future__ import annotations

from rlsentry.contracts.models import AccessMatrix, Finding, Op, Outcome, ProbeResult, Profile, Role, Target
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.probe import (
    AUDIT_WRITE_REASON,
    PROBE_ROLES,
    WRITE_OPS,
    WRITE_PENDING_REASON,
    KnownRows,
    ReadObservation,
    Sessions,
)
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.policy.resolve import resolve_expected
from rlsentry.probe.cross_tenant import collect_known_rows
from rlsentry.probe.diff import read_findings, target_findings
from rlsentry.probe.read import count_visible
from rlsentry.probe.verdict import read_cell, split_known


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
    write_reason = AUDIT_WRITE_REASON if profile is Profile.AUDIT else WRITE_PENDING_REASON
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
        for op in WRITE_OPS:
            for role in PROBE_ROLES:
                cells.append(ProbeResult(target=target.name, role=role, op=op,
                                         outcome=Outcome.NOT_TESTED, known_rows_checked=0,
                                         reason=write_reason, evidence_curl=""))
        findings.extend(target_findings(target))
    seen: set[str] = set()
    unique: list[Finding] = []
    for f in findings:
        if f.id not in seen:
            seen.add(f.id)
            unique.append(f)
    return AccessMatrix(cells=cells), unique
