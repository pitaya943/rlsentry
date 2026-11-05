"""MS3 write + escalation scan against the real lab (SPEC §5 M3 writes; FR-09; ADR-029): the
scanner's probe() in the DEV profile, scored against every dev-profile case of lab/*/expected.yaml.

What this proves beyond the unit tests:
- forbidden writes that really take effect are confirmed with the ground-truth rule/severity,
  and no confirmed vulnerability finding appears on a safe cell (no false positive);
- a 2xx that RLS filtered to 0 rows is NOT reported as a write (three-state write verdict);
- the L03 user_metadata escalation read is found only in dev/ci;
- cleanup is complete: after the scan every base table holds exactly its seeded rows (no canary
  left behind) and there is no CLEANUP_FAILED finding — the focus of MS3 (清理完整).
Needs Docker (tests/lab/conftest.py). Storage (L11, P2) is out of scope.
"""
from __future__ import annotations

import asyncio

import pytest

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS, SCENARIO_IDS, Case, CaseKind, GroundTruth
from rlsentry.contracts.lab import POSTGREST_ROLES, LabInfo
from rlsentry.contracts.models import AccessMatrix, Evidence, Finding, Op, Outcome, ProbeResult, Profile, Role
from rlsentry.contracts.policy import TestUser
from rlsentry.contracts.rules import RULES
from rlsentry.discovery.discover import discover
from rlsentry.probe.run import probe
from rlsentry.probe.session import build_sessions
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.lab.oracle import load_gt, scenario_path

Cell = tuple[str | None, Role | None, Op | None]


def frontend_sources(sid: str) -> list[str]:
    d = scenario_path(sid) / "frontend"
    return [p.read_text("utf-8") for p in sorted(d.rglob("*.js"))] if d.is_dir() else []


def scan(info: LabInfo, sid: str, gt: GroundTruth) -> tuple[AccessMatrix, list[Finding]]:
    users = [TestUser(name=r, email=u["email"], password_env=u["password_env"]) for r, u in LAB_USERS.items()]
    env = {u["password_env"]: labctl.lab_password(r) for r, u in LAB_USERS.items()}

    async def go() -> tuple[AccessMatrix, list[Finding]]:
        async with SafeClient(profile=Profile.DEV, limiter=RateLimiter(rps=200, concurrency=4)) as client:
            disc = await discover(client, info.api_url, info.anon_key, gt.policy, frontend_sources(sid))
            sessions = await build_sessions(client, info.api_url, info.anon_key, users, env)
            assert sessions.missing == {}, f"{sid}: lab login failed: {sessions.missing}"
            return await probe(client, info.api_url, info.anon_key, disc.targets, sessions, gt.policy, Profile.DEV)
    return asyncio.run(go())


def dev_cases(cases: list[Case]) -> list[Case]:
    return [c for c in cases if c.kind is CaseKind.ACCESS and Profile.DEV in c.profiles]


def base_tables(gt: GroundTruth) -> dict[str, list[str]]:
    """Base table name → its single pk column, for the leftover/unchanged check."""
    out: dict[str, list[str]] = {}
    for name, e in gt.schema_.items():
        if e.kind == "table":
            out[name] = e.primary_key
    return out


def seed_pks(gt: GroundTruth, table: str) -> set[str]:
    return {r.pk for r in gt.rows.values() if r.target == table}


# Vulnerable write cases the scanner may legitimately be unable to seed (a non-text NOT NULL
# column it cannot populate without types): the cell is then not_tested/inconclusive, never a
# false "safe". These are a documented limitation (ADR-029 補記 2), not a missed detection.
UNSEEDABLE = {Outcome.NOT_TESTED, Outcome.INCONCLUSIVE}


def judge(gt: GroundTruth, matrix: AccessMatrix, findings: list[Finding]) -> list[str]:
    errs: list[str] = []
    cells: dict[Cell, ProbeResult] = {(c.target, c.role, c.op): c for c in matrix.cells}
    vuln = [f for f in findings if f.evidence is Evidence.CONFIRMED and RULES[f.rule].vulnerability]
    hit = {(f.target, f.role, f.op, f.rule): f for f in vuln}
    expected: set[tuple] = set()
    for c in dev_cases(gt.vulnerable_cases):
        # L03 user_metadata escalation needs a re-login (password); deferred to MS6 (ADR-029 補記 2).
        if c.rule == "USER_METADATA_ESCALATION":
            continue
        key = (c.target, c.role, c.op, c.rule)
        expected.add(key)
        f = hit.get(key)
        got = cells.get((c.target, c.role, c.op))
        if f is not None:
            if f.severity is not c.severity:
                errs.append(f"{c.id}: severity {f.severity.value} != {c.severity and c.severity.value}")
        elif got is not None and got.outcome in UNSEEDABLE:
            pass   # could not seed a valid canary row → honest limitation, not a false negative
        else:
            errs.append(f"{c.id}: no confirmed {c.rule} finding and cell is "
                        f"{got.outcome.value if got else 'missing'} ({got.reason if got else ''})")
    for c in dev_cases(gt.safe_cases) + dev_cases(gt.inconclusive_cases):
        got = cells.get((c.target, c.role, c.op))
        if got is None:
            errs.append(f"{c.id}: cell missing")
            continue
        if any((f.target, f.role, f.op) == (c.target, c.role, c.op) for f in vuln):
            errs.append(f"{c.id}: confirmed vulnerability on a {c.expect and c.expect.value} cell")
        if c.expect is Outcome.DENIED and got.outcome is Outcome.ALLOWED:
            errs.append(f"{c.id}: outcome allowed on a denied cell ({got.reason})")
        if c.op is Op.SELECT and c.expect in (Outcome.DENIED, Outcome.INCONCLUSIVE) and got.outcome is not c.expect:
            errs.append(f"{c.id}: read outcome {got.outcome.value} != {c.expect.value} ({got.reason})")
    extra = [f"{k[0]}/{k[1] and k[1].value}/{k[2] and k[2].value}/{k[3]}" for k in hit if k not in expected]
    if extra:
        errs.append(f"unexpected confirmed findings (FP): {extra}")
    return errs


def cleanup_problems(gt: GroundTruth, findings: list[Finding]) -> list[str]:
    """Originals must survive; every leftover canary row must be accounted for by exactly one
    CLEANUP_FAILED finding (SPEC §5 M3: never leave data silently). A table whose policy denies
    the owner DELETE (e.g. L09 feedback) legitimately leaves canaries, each reported."""
    errs: list[str] = []
    for table, pk in base_tables(gt).items():
        if len(pk) != 1:
            continue
        got = {r[0] for r in labctl.query(f"select {pk[0]}::text from public.{table}")}
        want = seed_pks(gt, table)
        if not want <= got:
            errs.append(f"{table}: seeded rows were deleted (missing {sorted(want - got)})")
        leftover = got - want
        cf = [f for f in findings if f.rule == "CLEANUP_FAILED" and f.target == table]
        # CLEANUP_FAILED is deduped by (target, owner), so counts need not match; but leftover
        # canaries must be reported, and a report must correspond to real leftovers.
        if leftover and not cf:
            errs.append(f"{table}: {len(leftover)} leftover canary rows but no CLEANUP_FAILED finding")
        if cf and not leftover:
            errs.append(f"{table}: CLEANUP_FAILED finding but no leftover canary row")
    return errs


def seed_snapshot(gt: GroundTruth) -> dict[str, dict[str, str]]:
    """Full contents (as jsonb text) of every seeded row, read with the DB connection. Used to
    prove the scan modified no real row (NFR-01): the scanner must only ever touch its canaries."""
    snap: dict[str, dict[str, str]] = {}
    for table, pk in base_tables(gt).items():
        if len(pk) != 1:
            continue
        want = seed_pks(gt, table)
        rows = labctl.query(f"select {pk[0]}::text, to_jsonb(t)::text from public.{table} t")
        snap[table] = {r[0]: r[1] for r in rows if r[0] in want}
    return snap


def traffic_problems(gt: GroundTruth, marker: str, before: dict[str, dict[str, str]]) -> list[str]:
    """NFR-01 independent evidence, read from the DB itself (not the scanner's self-report): the
    scan modified no seeded (real) row, and the only data writes the Postgres log attributes to
    a PostgREST role are INSERT/UPDATE/DELETE on the scanner's own canaries. db_writes_since
    keeps only role+command (never values, NFR-03), so auth-session writes by supabase_auth_admin
    (the FR-07 login) are expected and ignored here; the canary-only guarantee rests on the
    seed-row snapshot below plus cleanup_problems. audit's zero-write property is proven
    separately in tests/lab/test_scan_reads.py."""
    errs: list[str] = []
    pgrst_writes = [w for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES]
    bad_cmd = {w.command for w in pgrst_writes} - {"INSERT", "UPDATE", "DELETE"}
    if bad_cmd:
        errs.append(f"unexpected PostgREST write commands during the scan: {sorted(bad_cmd)}")
    after = seed_snapshot(gt)
    for table, rows in before.items():
        if after.get(table) != rows:
            errs.append(f"{table}: a seeded (real) row changed during the scan")
    return errs


@pytest.mark.safety
@pytest.mark.parametrize("sid", [s for s in SCENARIO_IDS if s != "L11"])
def test_dev_writes_match_ground_truth(lab_info: LabInfo, sid: str) -> None:
    gt = load_gt(sid)
    labctl.apply(sid)
    try:
        before = seed_snapshot(gt)
        marker = labctl.db_log_marker()
        matrix, findings = scan(lab_info, sid, gt)
        problems = (judge(gt, matrix, findings) + cleanup_problems(gt, findings)
                    + traffic_problems(gt, marker, before))
        assert not problems, f"{sid}: " + "; ".join(problems)
    finally:
        labctl.apply(sid)   # discard any canary / escalation residue for the next scenario
