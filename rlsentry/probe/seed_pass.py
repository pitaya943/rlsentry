"""probe/seed_pass.py: dev/ci read seeding and its cleanup (SPEC §4 step 4; ADR-042).

Contract: rlsentry/contracts/probe.py seed_reads, cleanup_reads. Called by run_scan in dev/ci
only; never in audit (seed_known_rows' POSTs go through the SafeClient write gate regardless).
"""
from __future__ import annotations

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Finding, Op, Role, Target
from rlsentry.contracts.policy import ExpectedPolicy
from rlsentry.contracts.probe import SeededRow, Sessions
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.policy.resolve import resolve_expected
from rlsentry.probe.cleanup import cleanup_seeded
from rlsentry.probe.diff import cleanup_findings
from rlsentry.probe.run import pick_text_column
from rlsentry.probe.seed import seed_known_rows


async def seed_reads(client: SafeClientContract, supabase_url: str, anon_key: str,
                     targets: list[Target], policy: ExpectedPolicy,
                     sessions: Sessions) -> tuple[list[SeededRow], list[str]]:
    """Give every user a known row in each table before probe() runs (SPEC §4 step 4)."""
    rows: list[SeededRow] = []
    notes: list[str] = []
    for target in targets:
        if target.kind != "table" or len(target.primary_key) != 1:
            continue
        expected = resolve_expected(policy, target.name, Op.SELECT, Role.USER_A,
                                    tuple(target.columns))
        text_column = pick_text_column(target, expected.owner_column, expected.public_column)
        try:
            new_rows, new_notes = await seed_known_rows(
                client, supabase_url, anon_key, target, expected.owner_column,
                expected.public_column, text_column, sessions)
        except WriteRefused as exc:
            notes.append(f"read seeding refused by the safety gate: {exc}")
            break
        rows.extend(new_rows)
        notes.extend(f"{target.name}: {note}" for note in new_notes)
    return rows, notes


async def cleanup_reads(client: SafeClientContract, supabase_url: str, anon_key: str,
                        targets: list[Target], seeded: list[SeededRow],
                        sessions: Sessions) -> list[Finding]:
    """Delete every seeded canary, reporting any that cannot be removed (SPEC §5 M3 清理)."""
    by_target = {t.name: t for t in targets}
    seen_order: list[str] = []
    rows_by_target: dict[str, list[SeededRow]] = {}
    for row in seeded:
        if row.target not in rows_by_target:
            rows_by_target[row.target] = []
            seen_order.append(row.target)
        rows_by_target[row.target].append(row)

    findings: list[Finding] = []
    for name in seen_order:
        rows = rows_by_target[name]
        target = by_target.get(name) or Target(
            name=name, kind="table", discovered_by="policy", confidence="unknown")
        try:
            left = await cleanup_seeded(client, supabase_url, anon_key, target, rows, sessions)
        except WriteRefused:
            left = rows
        findings.extend(cleanup_findings(target, left))
    return findings
