"""M5 Report contracts (SPEC §5 M5; FR-12, FR-13; NFR-03). Owned by the architect.

Implementations: rlsentry/report/{fix_sql,enrich,json,html,sarif,exit_code}.py, and the GitHub
Action in action/action.yml. Decisions: ADR-044.

Every renderer works from the ScanReport only (never from raw module state) and passes its
final text through safety.mask.mask_text, so a key that slipped into any field is still masked
(defence in depth on top of the per-module masking, NFR-03). The fix SQL is advice: RLSentry
never executes it (SPEC §5 M5).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from rlsentry.contracts.models import Evidence, Finding, PolicyRow, Profile, ScanReport
from rlsentry.contracts.policy import FailOn, RowScope, ScanConfig

REPORT_FILE_STEM = "rlsentry-report"
"""CLI output files: <out>/rlsentry-report.json, .html, .sarif."""

DEFAULT_FORMATS: dict[Profile, tuple[str, ...]] = {
    Profile.DEV: ("html",),
    Profile.CI: ("json", "sarif"),
    Profile.AUDIT: ("html", "json"),
}
"""SPEC §2 profile table (dev: HTML + terminal summary; ci: JSON + SARIF + exit code; audit:
HTML + JSON with the authorization record)."""

EXIT_OK = 0
EXIT_FINDINGS = 1      # ci: a finding meets fail_on (FR-13)
EXIT_USAGE = 2         # bad config / missing input (ConfigError, ScanSetupError, CLI misuse)
EXIT_REFUSED = 3       # AuthorizationRefused, EndpointRefused, WriteRefused
EXIT_CLEANUP = 4       # ci: a CLEANUP_FAILED finding and no fail_on hit (ADR-014 補記 #4)

EVIDENCE_RANK: dict[Evidence, int] = {
    Evidence.CONFIRMED: 2, Evidence.SUSPECTED: 1, Evidence.CONFIG_WARNING: 0,
}
"""Higher is stronger evidence. fail_on.evidence = suspected also matches confirmed findings."""

FIX_SQL_HEADER = "-- RLSentry 修補建議：請先審閱再自行執行；RLSentry 不會執行任何 SQL。"

_RLS = "https://supabase.com/docs/guides/database/postgres/row-level-security"
_KEYS = "https://supabase.com/docs/guides/api/api-keys"
_DEFINER = "https://supabase.com/docs/guides/database/database-advisors"
_FUNCS = "https://supabase.com/docs/guides/database/functions"
REFERENCES: dict[str, tuple[str, ...]] = {
    "ANON_READ_OWNER_SCOPED": (_RLS,),
    "ANON_WRITE": (_RLS,),
    "CROSS_TENANT_READ": (_RLS,),
    "CROSS_TENANT_WRITE": (_RLS,),
    "USER_METADATA_ESCALATION": (_RLS,),
    "SECURITY_DEFINER_RPC_DATA": (_FUNCS, _DEFINER),
    "SECURITY_DEFINER_EXECUTABLE": (_FUNCS, _DEFINER),
    "SECRET_KEY_IN_BUNDLE": (_KEYS,),
    "UNVERIFIED_KEY": (_KEYS,),
    "LINT_ONLY": (_DEFINER,),
}
"""Documentation links per rule (static strings; RLSentry never fetches them)."""


class FixContext(BaseModel):
    """What fix_sql needs besides the finding. Built by enrich from the report and config."""

    model_config = ConfigDict(extra="forbid")

    kind: str | None = None             # Target.kind of finding.target (table|view|rpc), None unknown
    schema_name: str = "public"         # config.db_schemas[0]
    scope: RowScope | None = None       # resolve_expected(...).scope for (target, op, role)
    owner_column: str | None = None
    public_column: str | None = None
    policies: list[PolicyRow] = []      # report.policies on (schema_name, target)


# --- report/fix_sql.py --------------------------------------------------------------------------

def quote_ident(name: str) -> str:
    """Contract only; implemented by rlsentry.report.fix_sql.quote_ident. Pure.

    '"' + name with every '"' doubled + '"'. Empty names and names containing any character
    below U+0020 or U+007F raise ValueError: target names come from the target's OpenAPI (not
    trusted), and a newline inside a name could break out of a SQL comment line.
    """
    raise NotImplementedError


def fix_sql(finding: Finding, ctx: FixContext) -> str | None:
    """Contract only; implemented by rlsentry.report.fix_sql.fix_sql. Pure (ADR-044).

    Returns None for rules without a template, for findings without a target, and when
    quote_ident raises. Otherwise FIX_SQL_HEADER, "\\n", then lines. rel =
    quote_ident(ctx.schema_name) + "." + quote_ident(finding.target). Identifiers are ALWAYS
    written through quote_ident; nothing from the target (names, policy text) is written
    unquoted, and comments contain fixed text only.
    Role clause: anon → "TO anon"; user_a/user_b → "TO authenticated".
    Scope expression (o = quote_ident(owner_column), p = quote_ident(public_column)):
      own_rows_only → "auth.uid() = o"; public_rows_only → "p = true";
      public_or_own_rows → "p = true OR auth.uid() = o"; deny → no CREATE POLICY;
      a scope needing a column that is None → no CREATE POLICY and the comment line
      "-- 需要擁有者欄位或公開欄位才能產生 policy，請在設定檔中指定".
    Templates by rule:
    - ANON_READ_OWNER_SCOPED, CROSS_TENANT_READ, USER_METADATA_ESCALATION, ANON_WRITE,
      CROSS_TENANT_WRITE (op = finding.op, SELECT when None):
      * ctx.kind == "view": "ALTER VIEW <rel> SET (security_invoker = true);" only.
      * ctx.kind == "rpc": "REVOKE EXECUTE ON FUNCTION <rel> FROM <anon|authenticated>;"
        (by role) only.
      * else (table or unknown):
        "ALTER TABLE <rel> ENABLE ROW LEVEL SECURITY;";
        for each p in ctx.policies (in order) with p.permissive and p.command in
        (<OP>, "ALL"): "DROP POLICY <quote_ident(p.name)> ON <rel>;";
        when ctx.policies is empty: the comment line
        "-- 沒有 DB 連線（M4），無法列出既有 policy：請先移除此表上過寬的 permissive policy";
        then, unless no CREATE POLICY (see above):
        'CREATE POLICY <quote_ident("rlsentry_" + target + "_" + op + "_" + ("anon" if
        anon else "user"))> ON <rel> FOR <OP> <role clause> ' + by op:
        SELECT/DELETE → "USING (<expr>);", INSERT → "WITH CHECK (<expr>);",
        UPDATE → "USING (<expr>) WITH CHECK (<expr>);".
        USER_METADATA_ESCALATION adds the comment line
        "-- 授權條件請改用 app_metadata（使用者無法自行修改），不要信任 user_metadata".
    - SECURITY_DEFINER_RPC_DATA, SECURITY_DEFINER_EXECUTABLE:
      "ALTER FUNCTION <rel> SECURITY INVOKER;" then the comment line
      "-- 若必須保留 SECURITY DEFINER：撤銷 anon／authenticated 的 EXECUTE，並在函式內檢查 auth.uid()".
    - SECRET_KEY_IN_BUNDLE: comment lines only (key rotation, SPEC §5 M5):
      "-- 1. 立即在 Supabase Dashboard 輪替或撤銷此 key（service_role／secret key 或 JWT secret）",
      "-- 2. 從前端原始碼與建置環境變數移除，只在伺服器端使用",
      "-- 3. 重新建置、部署，並以 RLSentry 重掃確認 bundle 中已無此 key".
    - anything else → None.
    Lines are joined with "\\n" and the result ends with "\\n".
    """
    raise NotImplementedError


# --- report/enrich.py ---------------------------------------------------------------------------

def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Contract only; implemented by rlsentry.report.enrich.sort_findings. Pure.

    SPEC §5 M5: evidence level, then severity. Key: (-EVIDENCE_RANK[evidence],
    -SEVERITY_RANK[severity], target or "", rule, role value or "", op value or "", id).
    """
    raise NotImplementedError


def enrich(report: ScanReport, config: ScanConfig) -> ScanReport:
    """Contract only; implemented by rlsentry.report.enrich.enrich. Pure (M5 step of run_scan).

    Returns a copy whose findings are sort_findings(...) of copies with:
    - title = RULES[rule].description;
    - repro = mask_text(first non-empty probes[i].evidence_curl) or None;
    - references = list(REFERENCES.get(rule, ()));
    - fix_sql = fix_sql(f, ctx) with ctx = FixContext(
        kind = kind of the first report.discovery target named f.target (None if absent),
        schema_name = config.db_schemas[0],
        scope / owner_column / public_column = resolve_expected(config.policy, f.target,
          f.op or SELECT, f.role, columns of that target) fields when f.target and f.role are
          set (else None),
        policies = [p for p in report.policies if p.table == f.target and
                    p.schema_ == config.db_schemas[0]]).
    Nothing else changes (ids, evidence, severity, correlation stay as they are).
    """
    raise NotImplementedError


# --- report/json.py, report/html.py, report/sarif.py, report/exit_code.py ---------------------

def render_json(report: ScanReport) -> str:
    """Contract only; implemented by rlsentry.report.json.render_json. Pure.

    mask_text(copy.model_dump_json(indent=2, by_alias=True)) where copy = report with
    target = recon.report_url(report.target). Parses back with ScanReport.model_validate_json.
    """
    raise NotImplementedError


def render_html(report: ScanReport) -> str:
    """Contract only; implemented by rlsentry.report.html.render_html. Pure (FR-12).

    One self-contained HTML5 document (lang="zh-Hant", UTF-8), rendered with a Jinja2
    Environment(autoescape=True) from a template string kept in the module; no <script>, no
    external stylesheet, image or font (a report must not call out when opened). Content, in
    order: header (report_url(target), profile, tool_version, started_at/finished_at);
    authorization record (confirmed_by, method, confirmed_at, supabase_url and its method,
    write_hosts); modules and notes; a summary table of finding counts by evidence level ×
    severity; the findings in the given order, grouped under the headings "Confirmed",
    "Suspected", "Configuration warning", each showing title, rule, severity, target, role,
    op, correlation and lint, its probes (outcome, known_rows_checked, http_status, reason),
    repro in <pre>, fix_sql in <pre>, and references as <a href> links; pg_policies (when
    present); the access matrix; the recon scope (chunks_scanned, chunks_skipped, keys with
    masked values only). The final string goes through mask_text.
    """
    raise NotImplementedError


def render_sarif(report: ScanReport, config_path: str = "rlsentry.yaml") -> str:
    """Contract only; implemented by rlsentry.report.sarif.render_sarif. Pure (FR-13).

    JSON text (indent=2) of a SARIF 2.1.0 log, valid against the OASIS schema:
    {"version": "2.1.0", "$schema": SARIF_SCHEMA_URI, "runs": [run]} with
    run.tool.driver = {"name": "RLSentry", "version": TOOL_VERSION, "informationUri":
    TOOL_URI, "rules": [one per distinct rule among the findings, in first-appearance order:
    {"id", "name": id, "shortDescription": {"text": RULES[id].description},
     "properties": {"evidence", "severity"} (catalog defaults), and "helpUri":
     REFERENCES[id][0] when present}]};
    run.results = one per finding, in order: {"ruleId": rule, "level": sarif_level(f),
     "message": {"text": "<title or description> — target <target or '-'>, role <role or
     '-'>, op <op or '-'>"}, "locations": [{"physicalLocation": {"artifactLocation":
     {"uri": config_path}}}], "partialFingerprints": {"rlsentryFindingId/v1": id},
     "properties": {"evidence", "severity", "target", "role", "op", "correlation"} (values or
     null)};
    run.properties = {"profile": profile value, "target": report_url(target)}.
    The final string goes through mask_text.
    """
    raise NotImplementedError


SARIF_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
TOOL_URI = "https://github.com/pitaya943/rlsentry"


def sarif_level(finding: Finding) -> str:
    """Contract only; implemented by rlsentry.report.sarif.sarif_level. Pure.

    Confirmed and severity critical/high → "error"; Confirmed and medium/low → "warning";
    everything else (Suspected, Configuration warning, review) → "note".
    """
    raise NotImplementedError


def exit_code(report: ScanReport, fail_on: FailOn) -> int:
    """Contract only; implemented by rlsentry.report.exit_code.exit_code. Pure (FR-13).

    SPEC §2: only the ci profile has a failure threshold. Profile dev or audit → EXIT_OK.
    ci → EXIT_FINDINGS if any finding has EVIDENCE_RANK[evidence] >=
    EVIDENCE_RANK[fail_on.evidence] and SEVERITY_RANK[severity] >=
    SEVERITY_RANK[fail_on.severity]; else EXIT_CLEANUP if any finding's rule is
    CLEANUP_FAILED (ci may write to a remote preview DB; leftover canaries must fail the job,
    ADR-014 補記); else EXIT_OK. With the default FailOn (confirmed, high) only Confirmed
    findings of severity high or critical fail the job (SPEC §5 M5; MS6 focus).
    """
    raise NotImplementedError


# --- action/action.yml (GitHub Action; FR-13) -------------------------------------------------
ACTION_PATH = "action/action.yml"
ACTION_INPUTS: dict[str, str | None] = {
    "config": "rlsentry.yaml",
    "profile": "ci",
    "supabase-url": "",
    "out": "rlsentry-report",
    "upload-sarif": "true",
}
"""A composite action: actions/setup-python (3.12); pip install the action's repository
(github.action_path/..); `rlsentry scan --config … --profile … --out … --format json,sarif`
(plus --supabase-url when non-empty); then github/codeql-action/upload-sarif with `if: always()` and the input
upload-sarif == 'true', sarif_file <out>/rlsentry-report.sarif. Inputs reach the shell only
through `env:` (never `${{ inputs.* }}` inside a `run:` script: that is a script-injection
hole). The action never passes --i-own-this-target: authorization must be committed in the
config (`authorized: true`), so it is reviewed like code. The scan's exit code is the step's
exit code (FR-13)."""
