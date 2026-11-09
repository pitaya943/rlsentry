"""Rule catalog: every `Finding.rule` value, with its default evidence level and severity.

Owned by the architect (ADR-008). Ground truth (lab/**/expected.yaml) and the benchmark match
findings by rule id, so the ids below are part of the report format: rename = ADR.

Severity follows SPEC §5 M5. Where one rule can take two severities (anon read of a table that
holds sensitive columns is Critical, otherwise High) the catalog gives the base value and
`escalates_to` the higher one; the rules/ module decides which applies.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from rlsentry.contracts.models import Evidence, Op, Role, Severity


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    evidence: Evidence
    severity: Severity
    vulnerability: bool          # True: counts in benchmark scoring when evidence is confirmed
    description: str             # one line, Traditional Chinese, shown in the report
    escalates_to: Severity | None = None


def _r(id_: str, ev: Evidence, sev: Severity, vuln: bool, desc: str,
       esc: Severity | None = None) -> RuleSpec:
    return RuleSpec(id=id_, evidence=ev, severity=sev, vulnerability=vuln, description=desc,
                    escalates_to=esc)


_C, _S, _W = Evidence.CONFIRMED, Evidence.SUSPECTED, Evidence.CONFIG_WARNING

RULES: dict[str, RuleSpec] = {r.id: r for r in (
    # --- M3 dynamic probes (confirmed by known rows / read-back) ---
    _r("ANON_READ_OWNER_SCOPED", _C, Severity.HIGH, True,
       "anon 讀得到預期不可見的列", Severity.CRITICAL),       # Critical if sensitive columns
    _r("ANON_WRITE", _C, Severity.CRITICAL, True, "anon 可新增／修改／刪除"),
    _r("CROSS_TENANT_READ", _C, Severity.MEDIUM, True, "使用者讀得到他人的列"),
    _r("CROSS_TENANT_WRITE", _C, Severity.HIGH, True,
       "使用者可寫入、修改、刪除他人的列，或把列轉給他人"),
    _r("USER_METADATA_ESCALATION", _C, Severity.HIGH, True,
       "使用者自改 user_metadata 後取得預期不可見的資料"),
    _r("SECURITY_DEFINER_RPC_DATA", _C, Severity.MEDIUM, True,
       "經 SECURITY DEFINER RPC 實際取得受保護資料"),
    _r("PUBLIC_BUCKET_PRIVATE_OBJECT", _C, Severity.HIGH, True,
       "公開 Storage bucket 中的私人檔案可被 anon 存取（P2）"),
    # --- M1 recon ---
    _r("SECRET_KEY_IN_BUNDLE", _C, Severity.CRITICAL, True,
       "service_role／secret key 或其他高權限 JWT（supabase_admin、postgres 等）出現在前端"),
    _r("UNVERIFIED_KEY", _W, Severity.LOW, False, "無法辨識的疑似 key，請人工確認"),
    # --- configuration-level signals (never confirmed) ---
    _r("SECURITY_DEFINER_EXECUTABLE", _W, Severity.LOW, False,
       "SECURITY DEFINER 函式可被執行，但未實測取得受保護資料"),
    _r("SENSITIVE_COLUMN_PUBLIC", _W, Severity.REVIEW, False,
       "公開可讀的表含敏感欄位（email、phone、token 等），請確認是否應公開"),
    _r("LINT_ONLY", _W, Severity.LOW, False, "splinter 有報、實測無法存取"),
    # --- cannot judge ---
    _r("INCONCLUSIVE_CELL", _S, Severity.REVIEW, False, "無已知資料列可判定，不代表安全"),
    _r("INFERRED_TARGET", _S, Severity.REVIEW, False, "目標只由 bundle 推測，未經 OpenAPI 確認"),
    _r("NO_OWNER_COLUMN", _S, Severity.REVIEW, False, "找不到擁有者欄位，無法判斷預期權限"),
    _r("EXPECTED_ACCESS_DENIED", _W, Severity.REVIEW, False,
       "預期允許但實際拒絕（功能性提示，非漏洞）"),
    _r("CLEANUP_FAILED", _S, Severity.REVIEW, False,
       "寫入探測植入的 canary 列無法被其擁有者刪除，請人工清理（非漏洞，ADR-029）"),
)}

SENSITIVE_COLUMN_PATTERNS: tuple[str, ...] = (
    "email", "phone", "token", "password", "secret", "ssn",
)
"""Case-insensitive substrings marking a column as sensitive (SPEC §5 M5 Critical row)."""


# --- function contracts (implemented in rlsentry/rules/severity.py, MS2; ADR-023) ----------

def is_sensitive_column(name: str) -> bool:
    """Contract only; implemented by rlsentry.rules.severity.is_sensitive_column. Pure.

    True iff any SENSITIVE_COLUMN_PATTERNS entry is a substring of name.lower().
    """
    raise NotImplementedError


def read_rule(target_kind: str, role: Role) -> str:
    """Contract only; implemented by rlsentry.rules.severity.read_rule. Pure.

    Rule id for a confirmed read beyond the expected scope, by role only: ANON →
    ANON_READ_OWNER_SCOPED; user_a / user_b → CROSS_TENANT_READ. `target_kind` (table, view,
    rpc) no longer changes the rule (MS4 approval note 5 (b), ADR-039): M3 cannot tell whether
    an RPC is SECURITY DEFINER, so it never claims SECURITY_DEFINER_RPC_DATA; M4 correlate
    relabels the finding when splinter proves the function is SECURITY DEFINER and executable
    by that role. The argument is kept so callers need not change.
    """
    raise NotImplementedError


def read_severity(rule: str, columns: list[str]) -> Severity:
    """Contract only; implemented by rlsentry.rules.severity.read_severity. Pure.

    RULES[rule].escalates_to when it is set and any column is_sensitive_column, else
    RULES[rule].severity (SPEC §5 M5: anon read of a table with sensitive columns is Critical).
    Unknown rule → KeyError. Columns unknown (bundle-inferred target, []) never escalate.
    """
    raise NotImplementedError


def write_rule(role: Role, op: Op) -> str:
    """Contract only; implemented by rlsentry.rules.severity.write_rule. Pure (MS3; ADR-029 #4).

    Rule id for a confirmed forbidden write: role ANON → ANON_WRITE; user_a / user_b →
    CROSS_TENANT_WRITE. The write probe only attempts writes the policy forbids (anon writing
    at all, or a user writing/transferring another user's data), so a confirmed effect maps
    straight to these rules. `op` is accepted for symmetry and future rules; it does not change
    the result in MS3.
    """
    raise NotImplementedError
