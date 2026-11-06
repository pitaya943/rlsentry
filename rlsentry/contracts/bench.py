"""Benchmark contracts (SPEC §8 執行方式, §9 評估指標). Owned by the architect.

Design: ADR-011 (scoring), ADR-033 (coverage, ratios, splinter status, probe-only, runtime).
Implementations: rlsentry/bench/score.py (pure scoring) and rlsentry/bench/run.py +
rlsentry/bench/__main__.py (`python -m rlsentry.bench`). Only bench/ and tests may import
ground truth (tests/contracts/test_contract_imports.py).

The bench drives the lab (lab/_shared/labctl.py, test infrastructure that lives in the repo,
not in the installed package), so `python -m rlsentry.bench` runs from the repository root.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from rlsentry.contracts.ground_truth import BenchReport, GroundTruth, ScenarioResult
from rlsentry.contracts.lab import LabInfo
from rlsentry.contracts.models import AccessMatrix, Finding, Profile
from rlsentry.contracts.policy import ExpectedPolicy, ScanConfig
from rlsentry.contracts.whitebox import Lint

SCORING_PROFILE = Profile.DEV
"""Metrics (tp, fp, fn, tn, recall, precision, fpr, coverage) come from DEV runs only (ADR-011
#7). AUDIT runs are listed in `scenarios` for the read-only (db_writes == 0) and inconclusive
checks, never summed into the metrics."""

BENCH_RPS = 50.0
"""Rate limit for scenario runs: the lab is localhost and disposable (ADR-033). The runtime
measurement uses RUNTIME_RPS instead."""

RUNTIME_RPS = 5.0
"""= ScanConfig.rate_limit_rps default (NFR-04): runtime is what a user gets with defaults."""

RUNTIME_TABLES: tuple[int, ...] = (5, 20, 50)
"""SPEC §9 Runtime: table counts; BenchReport.runtime keys are str(n)."""

RUNTIME_PROFILE = Profile.AUDIT
"""Runtime is measured in AUDIT (read-only, the profile for real projects; ADR-033)."""


# --- bench/score.py (pure) ---------------------------------------------------------------------

def splinter_status(gt: GroundTruth, lints: list[Lint],
                    db_schemas: Sequence[str] = ("public",)) -> Literal["reported", "not_reported"]:
    """Contract only; implemented by rlsentry.bench.score.splinter_status. Pure (ADR-033).

    MS4 approval note 5 (c): the exposed schemas are a parameter, never hard-coded "public".
    "reported" iff some lint has "SECURITY" in categories, object_schema in db_schemas and
    object_name equal to the `target` of one of gt.vulnerable_cases whose kind is ACCESS or
    STORAGE (any profile); else "not_reported". So a scenario whose planted flaw splinter
    flags counts as reported; lints on other objects (e.g. L12 audit_log) or non-security lints
    do not, so scenarios without ACCESS/STORAGE vulnerable cases (L08 key, L10, C01–C04) are
    always "not_reported" (their security lints still appear in ScenarioResult.splinter_lints)."""
    raise NotImplementedError


def lint_labels(lints: list[Lint]) -> list[str]:
    """Contract only; implemented by rlsentry.bench.score.lint_labels. Pure.

    Sorted distinct "<name>:<object_name>" for every lint with "SECURITY" in categories
    (object_name None → "<name>:")."""
    raise NotImplementedError


def score_scenario(gt: GroundTruth, profile: Profile, matrix: AccessMatrix,
                   findings: list[Finding], runtime_s: float, *,
                   lints: list[Lint] | None = None, db_writes: int | None = None,
                   db_schemas: Sequence[str] = ("public",)) -> ScenarioResult:
    """Contract only; implemented by rlsentry.bench.score.score_scenario. Pure (ADR-011, ADR-033).

    Only cases whose `profiles` contain `profile` are scored; the rest are omitted from
    `cases`. Definitions (f = a Finding; "proven" = evidence CONFIRMED and
    RULES[f.rule].vulnerability):
    - vulnerable case c → "tp" iff some proven f matches it, else "fn". Match: for kind KEY,
      f.target == c.target and f.rule == c.rule; otherwise f.target, f.op, f.role, f.rule all
      equal c's. detail of "fn" = the matrix cell's "<outcome>: <reason>" for that
      (target, role, op), or "no cell" (key cases: "no finding").
    - unmatched_findings = sorted ids of proven findings matching no scored vulnerable case of
      this profile (ADR-011 #2: includes findings the ground truth did not foresee).
    - safe case c → "fp" iff some proven f has (f.target, f.role, f.op) == (c.target, c.role,
      c.op); else "tn".
    - inconclusive case c → "inconclusive_ok" iff the matrix cell (c.target, c.role, c.op)
      exists with outcome INCONCLUSIVE and no proven f is on that cell; else
      "inconclusive_violation" (detail = the cell's outcome or "no cell").
    - warning case c → "warning_seen" iff some f has rule == c.rule, evidence == c.evidence,
      target == c.target, role == c.role and op == c.op; else "warning_missing".
    - Coverage counters over the distinct cells (target, role, op) of the scored ACCESS cases
      (vulnerable + safe + inconclusive; not warning, KEY or STORAGE): cells_total; cells_tested
      = those present in the matrix with outcome ALLOWED, DENIED or INCONCLUSIVE;
      cells_inconclusive = those with outcome INCONCLUSIVE.
    - safe_denied_total = scored safe cases with expect DENIED; safe_denied_decided = those
      whose matrix cell outcome is DENIED.
    - scored = (gt.priority != "P2"). splinter fields when `lints` is not None:
      splinter = splinter_status(gt, lints, db_schemas), splinter_lints = lint_labels(lints),
      splinter_match = None if gt.splinter_expected == "measure" else
      (gt.splinter_expected == splinter). With lints None all three stay None/[].
    - probe_only = sorted ids of "tp" vulnerable cases whose FIRST matching finding (in
      `findings` order) has correlation == "probe_only".
    - db_writes copied as given (PostgREST-role writes during the run; None = not measured).
    """
    raise NotImplementedError


def aggregate(results: Sequence[ScenarioResult], runtime: dict[str, float]) -> BenchReport:
    """Contract only; implemented by rlsentry.bench.score.aggregate. Pure (ADR-033).

    Counted results = those with scored True and profile == SCORING_PROFILE. Over them:
    tp/fn = count of "tp"/"fn" case verdicts; fp = total len(unmatched_findings);
    fp_safe/tn = count of "fp"/"tn" verdicts; recall = tp/(tp+fn); precision = tp/(tp+fp);
    fpr = fp_safe/(fp_safe+tn); coverage = Σcells_tested/Σcells_total; inconclusive_ratio =
    Σcells_inconclusive/Σcells_total; safe_decided_ratio = Σsafe_denied_decided /
    Σsafe_denied_total. Every ratio with a zero denominator is 0.0 (the raw counts beside it
    show why; ADR-033). probe_only = {scenario: probe_only ids} for counted results with a
    non-empty list. scenarios = all results in the given order (including AUDIT and P2).
    runtime copied as given."""
    raise NotImplementedError


# --- bench/run.py (lab, I/O) -------------------------------------------------------------------

BENCH_ANON_KEY_ENV = "RLSENTRY_BENCH_ANON_KEY"
BENCH_DB_URL_ENV = "RLSENTRY_BENCH_DB_URL"
"""Environment variable NAMES used in the in-memory env dict the bench passes to run_scan; the
values are the lab's (labctl.ensure_up()). Nothing is exported to the process environment."""


def bench_config(target_url: str, info: LabInfo, policy: ExpectedPolicy, profile: Profile,
                 rps: float, with_db: bool) -> tuple[ScanConfig, dict[str, str]]:
    """Contract only; implemented by rlsentry.bench.run.bench_config. Pure (ADR-042).

    The ScanConfig a user of the lab would write, plus the env dict run_scan reads:
    ScanConfig(target=target_url, authorized=True, profile=profile, rate_limit_rps=rps,
    test_users=[TestUser(name=role, email=u["email"], password_env=u["password_env"]) for
    LAB_USERS], supabase_url=info.api_url, anon_key_env=BENCH_ANON_KEY_ENV,
    db_url_env=BENCH_DB_URL_ENV if with_db else None, tables=policy.tables,
    defaults=policy.defaults) and env = {password_env: labctl.lab_password(role) for LAB_USERS}
    | {BENCH_ANON_KEY_ENV: info.anon_key} | ({BENCH_DB_URL_ENV: info.db_url} if with_db).
    """
    raise NotImplementedError


def run_scenario(sid: str, profile: Profile, info: LabInfo, *,
                 rps: float = BENCH_RPS, with_whitebox: bool = True) -> ScenarioResult:
    """Contract only; implemented by rlsentry.bench.run.run_scenario. ⚠ lab writes (dev).

    MS6 (ADR-042, ADR-020 #6): the bench measures the product path itself, run_scan, so the
    only SafeClient is the one pipeline.py builds. Holding labctl.lock(): labctl.apply(sid);
    gt = the scenario's expected.yaml (GroundTruth.model_validate); marker =
    labctl.db_log_marker(); inside `labctl.serve_frontend(sid) as url`: config, env =
    bench_config(url, info, gt.policy, profile, rps, with_whitebox); report =
    asyncio.run(pipeline.run_scan(config, confirmed_by="rlsentry-bench", env=env)).
    runtime_s = report.timings.get("M2", 0) + report.timings.get("M3", 0) (M2+M3 only,
    ADR-033 #6). db_writes = number of labctl.db_writes_since(marker) entries whose role is in
    POSTGREST_ROLES. lints = run_splinter(info.db_url, config.db_schemas) if with_whitebox
    else None (a second, read-only run used only for splinter_status; run_scan already
    correlated). Return score_scenario(gt, profile, report.matrix, report.findings, runtime_s,
    lints=lints, db_writes=db_writes, db_schemas=config.db_schemas).
    An empty lint list is a measurement ("splinter reported nothing", e.g. L11), not "not
    run" (ADR-033 補記)."""
    raise NotImplementedError


def run_runtime(info: LabInfo, tables: Sequence[int] = RUNTIME_TABLES) -> dict[str, float]:
    """Contract only; implemented by rlsentry.bench.run.run_runtime. ⚠ lab writes (setup only).

    For each n: holding labctl.lock(), policy = labctl.apply_synthetic(n); config, env =
    bench_config(info.api_url, info, policy, RUNTIME_PROFILE, RUNTIME_RPS, with_db=False);
    report = asyncio.run(run_scan(config, confirmed_by="rlsentry-bench", env=env)); record
    round(report.timings["M2"] + report.timings["M3"], 1) under key str(n). (M1 fetches the API
    root once, untimed; M4 is off.)"""
    raise NotImplementedError


def run_bench(scenarios: Sequence[str], *, runtime: bool = True) -> BenchReport:
    """Contract only; implemented by rlsentry.bench.run.run_bench.

    info = labctl.ensure_up(). For each sid in the given order: run_scenario(sid, DEV, info)
    then run_scenario(sid, AUDIT, info) (M4 is read-only and runs in every profile,
    ADR-032; ADR-033 補記). runtime dict = run_runtime(info)
    if runtime else {}. Return aggregate(results, runtime_dict). Finally (try/finally) leave
    the lab with the last scenario re-applied: labctl.apply(scenarios[-1])."""
    raise NotImplementedError


def main(argv: Sequence[str] | None = None) -> int:
    """Contract only; implemented by rlsentry.bench.__main__.main (argparse).

    Options: `--scenario ID` (repeatable; default: every SCENARIO_IDS entry in order),
    `--json PATH` (write BenchReport.model_dump_json(indent=2) to PATH, creating parent
    directories), `--no-runtime` (skip run_runtime; implied when --scenario is given).
    An unknown scenario id → print an error to stderr and return 2 before touching the lab.
    Prints a one-screen summary to stdout: raw counts and ratios ("recall 38/40 = 0.95"
    style, SPEC §9 統計上的誠實), probe-only scenarios, splinter mismatches, any AUDIT result
    with db_writes != 0 and any inconclusive_violation. Returns 0 when it ran (metrics are
    reported, not enforced), 1 if an AUDIT run recorded db_writes != 0 (NFR-01 breach).
    `python -m rlsentry.bench` calls `raise SystemExit(main())`."""
    raise NotImplementedError
