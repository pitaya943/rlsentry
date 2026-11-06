"""probe/escalation.py: L03 user_metadata escalation (ADR-029 #9, ADR-042; MS3 approval note 1).

Contract: rlsentry/contracts/probe.py escalation_pass. The pass writes only the test user's own
Auth record, only when a verified DENIED read could reveal the change, and always restores it.
"""
from __future__ import annotations

from collections.abc import Mapping

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import (
    AccessMatrix,
    Finding,
    Op,
    Outcome,
    ProbeResult,
    Target,
    finding_id,
)
from rlsentry.contracts.policy import ExpectedPolicy, TestUser
from rlsentry.contracts.probe import ESCALATION_REASON, USER_ROLES, LoginFailed, Sessions
from rlsentry.contracts.rules import RULES
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.policy.resolve import resolve_expected
from rlsentry.probe.cross_tenant import collect_known_rows
from rlsentry.probe.metadata import escalate_user_metadata, restore_user_metadata
from rlsentry.probe.read import visible_pks
from rlsentry.probe.session import login
from rlsentry.probe.verdict import split_known

RULE = "USER_METADATA_ESCALATION"


async def escalation_pass(client: SafeClientContract, supabase_url: str, anon_key: str,
                          targets: list[Target], policy: ExpectedPolicy, sessions: Sessions,
                          users: list[TestUser], env: Mapping[str, str],
                          matrix: AccessMatrix) -> tuple[list[Finding], list[str]]:
    """The L03 technique (ADR-029 #9), wired in now that the caller has the test passwords."""
    findings: list[Finding] = []
    notes: list[str] = []
    users_by_role = {u.name: u for u in users}

    for role in USER_ROLES:
        token = sessions.tokens.get(role)
        user_id = sessions.user_ids.get(role)
        user = users_by_role.get(role)
        if token is None or user_id is None or user is None:
            continue
        password = env.get(user.password_env, "")
        if not password:
            continue

        candidates: list[tuple[Target, list[str]]] = []
        for target in targets:
            if len(target.primary_key) != 1:
                continue
            cell = next((c for c in matrix.cells
                        if c.target == target.name and c.role is role and c.op is Op.SELECT),
                       None)
            if cell is None or cell.outcome is not Outcome.DENIED:
                continue
            expected = resolve_expected(policy, target.name, Op.SELECT, role,
                                        tuple(target.columns))
            if expected.is_review:
                continue
            known = await collect_known_rows(client, supabase_url, anon_key, target,
                                              expected.owner_column, expected.public_column,
                                              sessions)
            forbidden, _ = split_known(expected, known.rows, sessions.user_ids)
            if not forbidden:
                continue
            res0 = await visible_pks(client, supabase_url, anon_key, target, token, forbidden)
            if res0.visible is None or res0.status not in (200, 206):
                continue
            hidden = [pk for pk in forbidden if pk not in res0.visible]
            if not hidden:
                continue
            candidates.append((target, hidden))

        if not candidates:
            continue

        try:
            status, changed = await escalate_user_metadata(client, supabase_url, anon_key, token)
        except WriteRefused as exc:
            notes.append(f"user_metadata escalation refused by the safety gate: {exc}")
            break
        if not changed:
            notes.append(f"{role.value}: user_metadata not changed ({status})")
            continue

        token2: str | None = None
        try:
            try:
                token2, _ = await login(client, supabase_url, anon_key, user.email, password)
            except LoginFailed as exc:
                notes.append(f"{role.value}: re-login after escalation failed ({exc})")
                continue
            for target, hidden in candidates:
                res = await visible_pks(client, supabase_url, anon_key, target, token2, hidden)
                if res.visible is None or res.status not in (200, 206):
                    continue
                n = len(res.visible)
                if n <= 0:
                    continue
                spec = RULES[RULE]
                reason = (f"{ESCALATION_REASON}: {n}/{len(hidden)} known rows outside the "
                         f"expected scope are visible")
                probe = ProbeResult(target=target.name, role=role, op=Op.SELECT,
                                    outcome=Outcome.ALLOWED, known_rows_checked=len(hidden),
                                    reason=reason, evidence_curl=res.curl,
                                    http_status=res.status)
                findings.append(Finding(id=finding_id(target.name, role, Op.SELECT, RULE),
                                        rule=RULE, evidence=spec.evidence,
                                        severity=spec.severity, target=target.name, role=role,
                                        op=Op.SELECT, probes=[probe]))
        finally:
            await restore_user_metadata(client, supabase_url, anon_key,
                                        token2 if token2 is not None else token)

    return findings, notes
