"""A small ScanReport with one finding of each evidence level, shared by the M5 tests."""
from __future__ import annotations

from datetime import UTC, datetime

from rlsentry.contracts.models import (
    AccessMatrix,
    AuthorizationRecord,
    DiscoveryResult,
    Evidence,
    Finding,
    KeyFinding,
    Op,
    Outcome,
    PolicyRow,
    ProbeResult,
    Profile,
    ReconResult,
    Role,
    ScanReport,
    Severity,
    Target,
    finding_id,
)
from rlsentry.contracts.rules import RULES

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJlLW5vdC12ZXJpZmllZA"
T0 = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
CURL = ("curl -sS -X GET 'http://127.0.0.1:54321/rest/v1/notes?select=id&id=in.(%22a%22)' "
        f"-H 'apikey: {JWT}' -H 'Authorization: Bearer {JWT}'")


def finding(rule: str, target: str | None, role: Role | None = None, op: Op | None = None,
            severity: Severity | None = None, evidence: Evidence | None = None,
            curl: str = "") -> Finding:
    spec = RULES[rule]
    probes = []
    if curl:
        assert target is not None and role is not None and op is not None
        probes = [ProbeResult(target=target, role=role, op=op, outcome=Outcome.ALLOWED,
                              known_rows_checked=1, reason="1/1 known rows outside the expected scope are visible",
                              http_status=200, evidence_curl=curl)]
    return Finding(id=finding_id(target, role, op, rule), rule=rule, evidence=evidence or spec.evidence,
                   severity=severity or spec.severity, target=target, role=role, op=op, probes=probes)


def report(findings: list[Finding] | None = None, profile: Profile = Profile.DEV,
           policies: list[PolicyRow] | None = None, target: str = "http://app.test/") -> ScanReport:
    fs = findings if findings is not None else [
        finding("INCONCLUSIVE_CELL", "notes", Role.USER_A, Op.SELECT),
        finding("CROSS_TENANT_READ", "notes", Role.USER_B, Op.SELECT, curl=CURL),
        finding("SECURITY_DEFINER_EXECUTABLE", "ping", Role.ANON, Op.SELECT),
        finding("SECRET_KEY_IN_BUNDLE", "jwt:service_role"),
    ]
    return ScanReport(
        tool_version="0.0.0", target=target, profile=profile,
        authorization=AuthorizationRecord(confirmed_by="tester", method="cli_flag", confirmed_at=T0,
                                          supabase_url="http://127.0.0.1:54321", supabase_url_method="config"),
        started_at=T0, finished_at=T0,
        recon=ReconResult(supabase_url="http://127.0.0.1:54321", chunks_scanned=["http://app.test/assets/app.js"],
                          keys=[KeyFinding(kind="secret", label="jwt:service_role", masked=JWT[:6] + "****" + JWT[-4:],
                                           source_file="http://app.test/assets/app.js")]),
        discovery=DiscoveryResult(openapi_available=True, targets=[
            Target(name="notes", kind="table", columns=["id", "owner_id", "body"], primary_key=["id"],
                   discovered_by="openapi", confidence="confirmed"),
            Target(name="ping", kind="rpc", discovered_by="openapi", confidence="confirmed")]),
        matrix=AccessMatrix(cells=[p for f in fs for p in f.probes]),
        findings=fs, policies=policies or [], modules=["M1", "M2", "M3", "M5"],
        notes=["M4 skipped: no database URL (db_url_env not set or empty)"], timings={"M1": 0.1})
