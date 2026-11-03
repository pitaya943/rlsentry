"""MS2 scanner reads against the real lab (ADR-023): discover() + probe() in the audit profile,
scored against every audit-profile SELECT case of lab/*/expected.yaml.

What this proves beyond the unit tests:
- the three-state verdicts hold on real PostgREST/RLS (C03/C04 inconclusive, never denied);
- vulnerable cases get a confirmed finding with the ground-truth rule and severity, and no
  confirmed vulnerability finding appears anywhere else (no false positive in audit);
- nothing but primary keys is downloaded, HEAD responses carry no body, the only non-GET
  request is the login POST, and the database logs no write by a PostgREST role (NFR-01).
Needs Docker (tests/lab/conftest.py). Key (M1) and storage (P2) cases are out of MS2 scope;
SECURITY_DEFINER_EXECUTABLE warnings come from M4 (MS4).
"""
from __future__ import annotations

import asyncio
import json

import httpx
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

M3_READ_WARNINGS = {"SENSITIVE_COLUMN_PUBLIC"}


class Recording(httpx.AsyncBaseTransport):
    """Real transport to the local lab that keeps (method, path, status, body) of every exchange."""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.seen: list[tuple[str, str, int, bytes]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        resp = await self.inner.handle_async_request(request)
        body = await resp.aread()
        self.seen.append((request.method, request.url.path, resp.status_code, body))
        return httpx.Response(resp.status_code, headers=resp.headers, content=body, request=request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def frontend_sources(sid: str) -> list[str]:
    d = scenario_path(sid) / "frontend"
    return [p.read_text("utf-8") for p in sorted(d.rglob("*.js"))] if d.is_dir() else []


def scan(info: LabInfo, sid: str, gt: GroundTruth, rec: Recording) -> tuple[list[str], AccessMatrix, list[Finding]]:
    users = [TestUser(name=r, email=u["email"], password_env=u["password_env"]) for r, u in LAB_USERS.items()]
    env = {u["password_env"]: labctl.lab_password(r) for r, u in LAB_USERS.items()}

    async def go() -> tuple[list[str], AccessMatrix, list[Finding]]:
        async with SafeClient(profile=Profile.AUDIT, limiter=RateLimiter(rps=200, concurrency=4),
                              transport=rec) as client:
            disc = await discover(client, info.api_url, info.anon_key, gt.policy, frontend_sources(sid))
            sessions = await build_sessions(client, info.api_url, info.anon_key, users, env)
            assert sessions.missing == {}, f"{sid}: lab login failed: {sessions.missing}"
            matrix, findings = await probe(client, info.api_url, info.anon_key, disc.targets, sessions,
                                           gt.policy, Profile.AUDIT)
            return [f"{t.name}:{t.discovered_by}:{t.confidence}" for t in disc.targets], matrix, findings
    return asyncio.run(go())


def audit_select(cases: list[Case]) -> list[Case]:
    return [c for c in cases if c.kind is CaseKind.ACCESS and c.op is Op.SELECT and Profile.AUDIT in c.profiles]


def judge(gt: GroundTruth, targets: list[str], matrix: AccessMatrix, findings: list[Finding]) -> list[str]:
    errs: list[str] = []
    Key = tuple[str | None, Role | None, Op | None]
    cell: dict[Key, ProbeResult] = {(c.target, c.role, c.op): c for c in matrix.cells}
    vuln = [f for f in findings if f.evidence is Evidence.CONFIRMED and RULES[f.rule].vulnerability]
    hit: dict[tuple[str | None, Role | None, Op | None, str | None], Finding] = {
        (f.target, f.role, f.op, f.rule): f for f in vuln}
    expected_hits: set[tuple[str | None, Role | None, Op | None, str | None]] = set()
    for c in audit_select(gt.vulnerable_cases):
        key = (c.target, c.role, c.op, c.rule)
        expected_hits.add(key)
        f = hit.get(key)
        if f is None:
            errs.append(f"{c.id}: no confirmed {c.rule} finding")
        elif f.severity is not c.severity:
            errs.append(f"{c.id}: severity {f.severity.value} != {c.severity and c.severity.value}")
    for c in audit_select(gt.safe_cases) + audit_select(gt.inconclusive_cases):
        got = cell.get((c.target, c.role, c.op))
        if got is None:
            errs.append(f"{c.id}: cell missing")
            continue
        if any((f.target, f.role, f.op) == (c.target, c.role, c.op) for f in vuln):
            errs.append(f"{c.id}: confirmed vulnerability on a {c.expect and c.expect.value} cell")
        if c.expect in (Outcome.DENIED, Outcome.INCONCLUSIVE) and got.outcome is not c.expect:
            errs.append(f"{c.id}: outcome {got.outcome.value} != {c.expect.value} ({got.reason})")
    for c in audit_select(gt.warning_cases):
        if c.rule in M3_READ_WARNINGS and not any(
                (f.target, f.role, f.op, f.rule) == (c.target, c.role, c.op, c.rule) for f in findings):
            errs.append(f"{c.id}: no {c.rule} finding")
    extra = [f"{k[0]}/{k[1] and k[1].value}/{k[3]}" for k in hit if k not in expected_hits]
    if extra:
        errs.append(f"unexpected confirmed findings (FP): {extra}")
    for d in gt.discovery_cases:
        if f"{d.target}:{d.discovered_by}:{d.confidence}" not in targets:
            errs.append(f"discovery {d.target}: expected {d.discovered_by}/{d.confidence}, got {targets}")
    return errs


def traffic_problems(gt: GroundTruth, rec: Recording) -> list[str]:
    pks = {e_name: set(e.primary_key) for e_name, e in gt.schema_.items()}
    pks.update({n: set(tp.primary_key) for n, tp in gt.policy.tables.items() if tp.primary_key})
    errs: list[str] = []
    for method, path, status, body in rec.seen:
        if method == "POST" and path == "/auth/v1/token":
            continue
        if method not in ("GET", "HEAD"):
            errs.append(f"{method} {path}")
        # HEAD bodies are never read by httpx, so only the method allowlist and the GET
        # bodies below can prove "no download" (MS2 audit F5).
        elif method == "GET" and path != "/rest/v1/" and 200 <= status < 300:
            if not path.startswith("/rest/v1/"):
                errs.append(f"GET {path}: only PostgREST is read in MS2")
                continue
            name = path.removeprefix("/rest/v1/").removeprefix("rpc/")
            rows = json.loads(body)
            keys = {k for r in rows for k in r} if isinstance(rows, list) else {"<not a list>"}
            if not keys <= pks.get(name, set()):
                errs.append(f"GET {path} downloaded non-key columns {sorted(keys)}")
    return errs


@pytest.mark.safety
# L11 has no PostgREST target (Storage only, P2); Storage probing is not in MS2 (ADR-023).
@pytest.mark.parametrize("sid", [s for s in SCENARIO_IDS if s != "L11"])
def test_audit_reads_match_ground_truth(lab_info: LabInfo, sid: str) -> None:
    gt = load_gt(sid)
    labctl.apply(sid)
    rec = Recording()
    marker = labctl.db_log_marker()
    targets, matrix, findings = scan(lab_info, sid, gt, rec)
    writes = [w for w in labctl.db_writes_since(marker) if w.role in POSTGREST_ROLES]
    problems = judge(gt, targets, matrix, findings) + traffic_problems(gt, rec)
    assert not writes, f"{sid}: PostgREST roles wrote during an audit scan: {writes}"
    assert not problems, f"{sid}: " + "; ".join(problems)
