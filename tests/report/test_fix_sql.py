"""report/fix_sql.py: fix SQL templates (SPEC §5 M5; ADR-044; MS4 approval note 3).

The SQL is advice that a human pastes into a database, so identifiers from the target (not
trusted) must always be quoted and must never break out of a comment line.
"""
from __future__ import annotations

import pytest

from rlsentry.contracts.models import Op, PolicyRow, Role
from rlsentry.contracts.policy import RowScope
from rlsentry.contracts.report import FIX_SQL_HEADER, FixContext
from rlsentry.report.fix_sql import fix_sql, quote_ident
from tests.report.helpers import finding


def pol(name: str, cmd: str = "SELECT", permissive: bool = True, table: str = "notes",
        roles: tuple[str, ...] = ("authenticated",)) -> PolicyRow:
    return PolicyRow(schema="public", table=table, name=name, command=cmd, roles=list(roles),
                     permissive=permissive)


def ctx(**kw: object) -> FixContext:
    base: dict[str, object] = {"kind": "table", "scope": RowScope.OWN_ROWS_ONLY, "owner_column": "owner_id"}
    base.update(kw)
    return FixContext.model_validate(base)


def test_quote_ident() -> None:
    assert quote_ident("notes") == '"notes"'
    assert quote_ident('we"ird') == '"we""ird"'
    for bad in ("", "a\nb", "a\rb", "a\x00b", "a\x7fb"):
        with pytest.raises(ValueError):
            quote_ident(bad)


def test_l04_cross_tenant_read_with_m4_policies() -> None:
    f = finding("CROSS_TENANT_READ", "notes", Role.USER_B, Op.SELECT)
    sql = fix_sql(f, ctx(policies=[pol("notes_select"), pol("notes_insert", "INSERT"),
                                   pol("restrictive_one", permissive=False), pol("all_cmds", "ALL")]))
    create = ('CREATE POLICY "rlsentry_notes_select_user" ON "public"."notes" FOR SELECT TO authenticated '
              'USING (auth.uid() = "owner_id");')
    lines = [FIX_SQL_HEADER, 'ALTER TABLE "public"."notes" ENABLE ROW LEVEL SECURITY;',
             'DROP POLICY "notes_select" ON "public"."notes";', 'DROP POLICY "all_cmds" ON "public"."notes";',
             create]
    assert sql == "\n".join(lines) + "\n"


def test_without_m4_a_comment_replaces_the_drop() -> None:
    sql = fix_sql(finding("CROSS_TENANT_READ", "notes", Role.USER_A, Op.SELECT), ctx())
    assert sql is not None and "DROP POLICY" not in sql
    assert "-- 沒有 DB 連線（M4），無法列出既有 policy：請先移除此表上過寬的 permissive policy" in sql


@pytest.mark.parametrize("scope, expr", [
    (RowScope.PUBLIC_ROWS_ONLY, '"is_public" = true'),
    (RowScope.PUBLIC_OR_OWN_ROWS, '"is_public" = true OR auth.uid() = "owner_id"'),
])
def test_scope_expressions(scope: RowScope, expr: str) -> None:
    sql = fix_sql(finding("ANON_READ_OWNER_SCOPED", "posts", Role.ANON, Op.SELECT),
                  ctx(scope=scope, public_column="is_public"))
    assert sql is not None and f'FOR SELECT TO anon USING ({expr});' in sql
    assert '"rlsentry_posts_select_anon"' in sql


def test_deny_scope_drops_but_creates_nothing() -> None:
    sql = fix_sql(finding("ANON_READ_OWNER_SCOPED", "notes", Role.ANON, Op.SELECT),
                  ctx(scope=RowScope.DENY, policies=[pol("open", roles=("anon",))]))
    assert sql is not None and 'DROP POLICY "open"' in sql and "CREATE POLICY" not in sql


def test_missing_owner_column_gives_a_comment_not_a_policy() -> None:
    sql = fix_sql(finding("CROSS_TENANT_READ", "notes", Role.USER_A, Op.SELECT), ctx(owner_column=None))
    assert sql is not None and "CREATE POLICY" not in sql
    assert "-- 需要擁有者欄位或公開欄位才能產生 policy，請在設定檔中指定" in sql


@pytest.mark.parametrize("op, clause", [
    (Op.INSERT, 'FOR INSERT TO authenticated WITH CHECK (auth.uid() = "owner_id");'),
    (Op.UPDATE, 'FOR UPDATE TO authenticated USING (auth.uid() = "owner_id") WITH CHECK (auth.uid() = "owner_id");'),
    (Op.DELETE, 'FOR DELETE TO authenticated USING (auth.uid() = "owner_id");'),
])
def test_write_templates(op: Op, clause: str) -> None:
    sql = fix_sql(finding("CROSS_TENANT_WRITE", "projects", Role.USER_A, op),
                  ctx(policies=[pol("p_upd", "UPDATE", table="projects"), pol("p_all", "ALL", table="projects")]))
    assert sql is not None and clause in sql
    drops = [ln for ln in sql.splitlines() if ln.startswith("DROP POLICY")]
    assert ('DROP POLICY "p_upd" ON "public"."projects";' in drops) == (op is Op.UPDATE)
    assert 'DROP POLICY "p_all" ON "public"."projects";' in drops


def test_anon_write_uses_to_anon() -> None:
    sql = fix_sql(finding("ANON_WRITE", "feedback", Role.ANON, Op.INSERT), ctx(scope=RowScope.DENY))
    assert sql is not None and "CREATE POLICY" not in sql and 'ENABLE ROW LEVEL SECURITY' in sql


def test_view_and_rpc_templates() -> None:
    v = fix_sql(finding("ANON_READ_OWNER_SCOPED", "invoice_summary", Role.ANON, Op.SELECT), ctx(kind="view"))
    assert v == FIX_SQL_HEADER + '\nALTER VIEW "public"."invoice_summary" SET (security_invoker = true);\n'
    r = fix_sql(finding("CROSS_TENANT_READ", "list_all", Role.USER_A, Op.SELECT), ctx(kind="rpc"))
    assert r == FIX_SQL_HEADER + '\nREVOKE EXECUTE ON FUNCTION "public"."list_all" FROM authenticated;\n'


def test_security_definer_rpc_and_metadata_and_key() -> None:
    d = fix_sql(finding("SECURITY_DEFINER_RPC_DATA", "get_all_accounts", Role.ANON, Op.SELECT), ctx(kind="rpc"))
    assert d is not None and 'ALTER FUNCTION "public"."get_all_accounts" SECURITY INVOKER;' in d
    m = fix_sql(finding("USER_METADATA_ESCALATION", "reports", Role.USER_A, Op.SELECT), ctx())
    assert m is not None and "app_metadata" in m and "CREATE POLICY" in m
    k = fix_sql(finding("SECRET_KEY_IN_BUNDLE", "jwt:service_role"), FixContext())
    assert k is not None and all(ln.startswith("--") for ln in k.splitlines())


def test_no_template_or_unsafe_name_gives_none() -> None:
    assert fix_sql(finding("INCONCLUSIVE_CELL", "notes", Role.USER_A, Op.SELECT), ctx()) is None
    assert fix_sql(finding("LINT_ONLY", "notes"), ctx()) is None
    evil = finding("CROSS_TENANT_READ", "notes\nDROP TABLE x; --", Role.USER_A, Op.SELECT)
    assert fix_sql(evil, ctx()) is None


def test_hostile_names_stay_inside_quotes() -> None:
    sql = fix_sql(finding("CROSS_TENANT_READ", 'a"; DROP TABLE x; --', Role.USER_A, Op.SELECT),
                  ctx(owner_column='o"; --', policies=[pol('p"q', table='a"; DROP TABLE x; --')]))
    assert sql is not None
    assert '"a""; DROP TABLE x; --"' in sql and '"o""; --"' in sql and '"p""q"' in sql
    for line in sql.splitlines():
        assert line.startswith(("--", "ALTER ", "DROP POLICY ", "CREATE POLICY "))
