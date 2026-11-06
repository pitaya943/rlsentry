"""MS7, ADR-051 #1–#2: fix SQL drops only policies that can apply to the finding's role, and
generated policy names fit PostgreSQL's 63-byte limit without colliding.

Why: the SQL is pasted into a database by a human. Dropping a policy that serves another role
would break legitimate access; a name the server truncates could collide with another one.
"""
from __future__ import annotations

import hashlib

import pytest

from rlsentry.contracts.models import Op, PolicyRow, Role
from rlsentry.contracts.report import PG_NAME_MAX_BYTES
from rlsentry.report.fix_sql import fix_sql, policy_name
from tests.report.helpers import finding
from tests.report.test_fix_sql import ctx


def pol(name: str, roles: list[str], cmd: str = "SELECT") -> PolicyRow:
    return PolicyRow(schema="public", table="notes", name=name, command=cmd, roles=roles, permissive=True)


POLICIES = [pol("p_anon", ["anon"]), pol("p_public", ["public"]), pol("p_auth", ["authenticated"]),
            pol("p_both", ["anon", "authenticated"]), pol("p_service", ["service_role"])]


def drops(sql: str | None) -> list[str]:
    assert sql is not None
    return [ln.split('"')[1] for ln in sql.splitlines() if ln.startswith("DROP POLICY")]


def test_anon_finding_drops_only_policies_anon_can_use() -> None:
    sql = fix_sql(finding("ANON_READ_OWNER_SCOPED", "notes", Role.ANON, Op.SELECT), ctx(policies=POLICIES))
    assert drops(sql) == ["p_anon", "p_public", "p_both"]


@pytest.mark.parametrize("role", [Role.USER_A, Role.USER_B])
def test_user_finding_drops_only_policies_signed_in_users_can_use(role: Role) -> None:
    sql = fix_sql(finding("CROSS_TENANT_READ", "notes", role, Op.SELECT), ctx(policies=POLICIES))
    assert drops(sql) == ["p_public", "p_auth", "p_both"]


def test_other_roles_only_means_no_drop_but_still_a_policy() -> None:
    sql = fix_sql(finding("CROSS_TENANT_WRITE", "notes", Role.USER_A, Op.UPDATE),
                  ctx(policies=[pol("svc", ["service_role"], "UPDATE"), pol("anon_all", ["anon"], "ALL")]))
    assert drops(sql) == [] and sql is not None and "CREATE POLICY" in sql
    assert "沒有 DB 連線" not in sql                   # M4 did list policies; none applied


def test_short_names_are_unchanged() -> None:
    assert policy_name("notes", "select", False) == "rlsentry_notes_select_user"
    assert policy_name("notes", "insert", True) == "rlsentry_notes_insert_anon"
    exact = "t" * (PG_NAME_MAX_BYTES - len("rlsentry__select_user"))
    assert policy_name(exact, "select", False) == f"rlsentry_{exact}_select_user"   # exactly 63 bytes


def test_long_names_fit_and_stay_distinct() -> None:
    a, b = "x" * 60 + "_alpha", "x" * 60 + "_beta"
    na, nb = policy_name(a, "update", False), policy_name(b, "update", False)
    for n, t in ((na, a), (nb, b)):
        full = f"rlsentry_{t}_update_user"
        assert len(n.encode()) <= PG_NAME_MAX_BYTES
        assert n.endswith("_" + hashlib.sha256(full.encode()).hexdigest()[:8])
        assert full.startswith(n[:-9])
    assert na != nb and na[:-9] == nb[:-9]                 # same head, the hash tells them apart
    assert policy_name(a, "update", False) == na             # deterministic


def test_multibyte_names_are_never_cut_inside_a_character() -> None:
    t = "顧客資料表" * 6                                     # 3 bytes per character
    n = policy_name(t, "select", True)
    assert len(n.encode("utf-8")) <= PG_NAME_MAX_BYTES
    n.encode("utf-8").decode("utf-8")                        # valid UTF-8
    assert f"rlsentry_{t}_select_anon".startswith(n[:-9])


def test_fix_sql_uses_the_bounded_name() -> None:
    t = "a_really_long_table_name_" * 3
    sql = fix_sql(finding("CROSS_TENANT_READ", t, Role.USER_A, Op.SELECT), ctx())
    assert sql is not None and f'CREATE POLICY "{policy_name(t, "select", False)}" ON' in sql
