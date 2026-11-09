"""report/fix_sql.py: fix SQL templates (SPEC §5 M5; ADR-044). Advice only, never executed."""
from __future__ import annotations

import hashlib

from rlsentry.contracts.models import Finding, Op, Role
from rlsentry.contracts.policy import RowScope
from rlsentry.contracts.report import FIX_SQL_HEADER, PG_NAME_MAX_BYTES, POLICY_ROLES_FOR, FixContext

_ACCESS_RULES = frozenset({
    "ANON_READ_OWNER_SCOPED", "CROSS_TENANT_READ", "USER_METADATA_ESCALATION", "ANON_WRITE",
    "CROSS_TENANT_WRITE"})
_DEFINER_RULES = frozenset({"SECURITY_DEFINER_RPC_DATA", "SECURITY_DEFINER_EXECUTABLE"})
_NO_COLUMN = "-- 需要擁有者欄位或公開欄位才能產生 policy，請在設定檔中指定"
_NO_M4 = "-- 沒有 DB 連線（M4），無法列出既有 policy：請先移除此表上過寬的 permissive policy"
_METADATA = "-- 授權條件請改用 app_metadata（使用者無法自行修改），不要信任 user_metadata"
_DEFINER_NOTE = ("-- 若必須保留 SECURITY DEFINER：撤銷 anon／authenticated 的 EXECUTE，"
                 "並在函式內檢查 auth.uid()")
_KEY_LINES = [
    "-- 1. 立即在 Supabase Dashboard 輪替或撤銷此 key（service_role／secret key 或 JWT secret）",
    "-- 2. 從前端原始碼與建置環境變數移除，只在伺服器端使用",
    "-- 3. 重新建置、部署，並以 RLSentry 重掃確認 bundle 中已無此 key",
]


def quote_ident(name: str) -> str:
    """Quote a SQL identifier; reject names that could break out of a line or comment.

    Why: names come from the target's OpenAPI (untrusted) and are pasted into a database.
    """
    if not name or any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        raise ValueError("unsafe identifier")
    return '"' + name.replace('"', '""') + '"'


def policy_name(target: str, op: str, anon: bool) -> str:
    """Policy name bounded to PG_NAME_MAX_BYTES; long names get a hash suffix (ADR-051 #2).

    Why: PostgreSQL silently truncates names, which could make two policies collide.
    """
    full = f"rlsentry_{target}_{op}_{'anon' if anon else 'user'}"
    if len(full.encode("utf-8")) <= PG_NAME_MAX_BYTES:
        return full
    budget = PG_NAME_MAX_BYTES - 9
    head = full.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return head + "_" + hashlib.sha256(full.encode("utf-8")).hexdigest()[:8]


def _expr(ctx: FixContext) -> str | None:
    """Scope expression, or None when no policy can be generated."""
    o = quote_ident(ctx.owner_column) if ctx.owner_column else None
    p = quote_ident(ctx.public_column) if ctx.public_column else None
    match ctx.scope:
        case RowScope.OWN_ROWS_ONLY:
            return f"auth.uid() = {o}" if o else None
        case RowScope.PUBLIC_ROWS_ONLY:
            return f"{p} = true" if p else None
        case RowScope.PUBLIC_OR_OWN_ROWS:
            return f"{p} = true OR auth.uid() = {o}" if o and p else None
        case _:
            return None


def _table_lines(f: Finding, ctx: FixContext, rel: str, target: str) -> list[str]:
    op = (f.op or Op.SELECT).value
    up = op.upper()
    anon = f.role is Role.ANON
    lines = [f"ALTER TABLE {rel} ENABLE ROW LEVEL SECURITY;"]
    for p in ctx.policies:
        if (p.permissive and p.command.upper() in (up, "ALL")
                and set(p.roles) & POLICY_ROLES_FOR["anon" if anon else "user"]):
            lines.append(f"DROP POLICY {quote_ident(p.name)} ON {rel};")
    if not ctx.policies:
        lines.append(_NO_M4)
    if ctx.scope is not RowScope.DENY:
        expr = _expr(ctx)
        if expr is None:
            if ctx.scope is not None and ctx.scope is not RowScope.ALL:
                lines.append(_NO_COLUMN)
        else:
            name = quote_ident(policy_name(target, op, anon))
            head = f"CREATE POLICY {name} ON {rel} FOR {up} TO {'anon' if anon else 'authenticated'} "
            tail = {Op.INSERT.value: f"WITH CHECK ({expr});",
                    Op.UPDATE.value: f"USING ({expr}) WITH CHECK ({expr});"}.get(op, f"USING ({expr});")
            lines.append(head + tail)
    if f.rule == "USER_METADATA_ESCALATION":
        lines.append(_METADATA)
    return lines


def fix_sql(finding: Finding, ctx: FixContext) -> str | None:
    """Build advisory fix SQL for a finding, or None when no template applies (ADR-044)."""
    rule = finding.rule
    if rule == "SECRET_KEY_IN_BUNDLE":
        return "\n".join([FIX_SQL_HEADER, *_KEY_LINES]) + "\n"
    if finding.target is None or (rule not in _ACCESS_RULES and rule not in _DEFINER_RULES):
        return None
    try:
        rel = quote_ident(ctx.schema_name) + "." + quote_ident(finding.target)
        if rule in _DEFINER_RULES:
            lines = [f"ALTER FUNCTION {rel} SECURITY INVOKER;", _DEFINER_NOTE]
        elif ctx.kind == "view":
            lines = [f"ALTER VIEW {rel} SET (security_invoker = true);"]
        elif ctx.kind == "rpc":
            who = "anon" if finding.role is Role.ANON else "authenticated"
            lines = [f"REVOKE EXECUTE ON FUNCTION {rel} FROM {who};"]
        else:
            lines = _table_lines(finding, ctx, rel, finding.target)
    except ValueError:
        return None
    return "\n".join([FIX_SQL_HEADER, *lines]) + "\n"
