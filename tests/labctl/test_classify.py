"""labctl.write_command: pure classification of logged statements (ADR-019, ADR-024 補記;
MS2 audit F1, F2). No Docker needed. Contract: rlsentry/contracts/lab.py."""
import pytest

from lab._shared import labctl

PGRST_UPDATE = ('WITH pgrst_source AS (UPDATE "public"."notes" SET "body" = "pgrst_body"."body" FROM '
                "(SELECT $1 AS json_data) pgrst_payload, LATERAL (SELECT \"body\" FROM json_to_record(pgrst_payload.json_data) "
                'AS _ ("body" text)) pgrst_body WHERE "public"."notes"."id" = $2 RETURNING 1) '
                "SELECT '' AS total_result_set, pg_catalog.count(_postgrest_t) AS page_total")
OPENAPI = ("select c.relname from pg_class c where has_table_privilege(c.oid, "
           "'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')")

pytestmark = pytest.mark.safety


@pytest.mark.parametrize("sql,command", [
    (PGRST_UPDATE, "UPDATE"),
    ('WITH pgrst_source AS (INSERT INTO "public"."t"("a") SELECT "a" FROM json_populate_recordset(null, $1)) SELECT 1',
     "INSERT"),
    ('WITH pgrst_source AS (DELETE FROM "public"."t" WHERE "id" = $1 RETURNING 1) SELECT 1', "DELETE"),
    ("merge into t using s on true when matched then delete", "MERGE"),
    ('COPY "t" FROM stdin', "COPY"),
    ("truncate table t", "TRUNCATE"),
])
def test_real_writes_are_found(sql: str, command: str) -> None:
    assert labctl.write_command(sql) == command


@pytest.mark.parametrize("sql", [
    OPENAPI,
    "select 'INSERT INTO x' as a",
    "select 'it''s' || 'DELETE FROM t'",
    "select $$TRUNCATE t$$",
    "select $fn$DELETE FROM t$fn$",
    'select "truncate", "insert into" from t',
    "select 1",
    "",
])
def test_quoted_keywords_and_reads_are_not_writes(sql: str) -> None:
    assert labctl.write_command(sql) is None


@pytest.mark.parametrize("sql,command", [
    # An apostrophe inside an identifier or a dollar-quoted body must not open a fake literal
    # that swallows the write after it (audit F2).
    ('WITH a AS (SELECT "o\'x" FROM t), b AS (DELETE FROM t RETURNING 1) SELECT \'z\'', "DELETE"),
    ("DO $$ BEGIN PERFORM 'it''s'; END $$; INSERT INTO t VALUES (1)", "INSERT"),
    ("select $$it's$$; UPDATE t SET a = 'x'", "UPDATE"),
    ("select 'a'''; insert into t values ('b')", "INSERT"),
])
def test_stray_quotes_cannot_hide_a_write(sql: str, command: str) -> None:
    assert labctl.write_command(sql) == command
