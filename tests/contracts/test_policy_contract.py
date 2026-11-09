"""Contract tests for rlsentry.contracts.policy (T-011). SPEC §6 設定檔 rlsentry.yaml."""
import pytest
import yaml
from pydantic import ValidationError

from rlsentry.contracts.models import Evidence, Profile, Role, Severity
from rlsentry.contracts.policy import ExpectedAccess, RowScope, ScanConfig

# The example of SPEC §6, verbatim apart from comments.
SPEC_EXAMPLE = """
target: https://my-app.example.com
authorized: true
profile: audit
rate_limit_rps: 5
test_users:
  - {name: user_a, email: a@test.dev, password_env: RLS_A_PW}
  - {name: user_b, email: b@test.dev, password_env: RLS_B_PW}
db_url_env: SUPABASE_DB_URL
tables:
  profiles:
    owner_column: id
    select: {anon: deny, user: own_rows_only}
    update: {anon: deny, user: own_rows_only}
    delete: {anon: deny, user: deny}
  posts:
    owner_column: author_id
    public_column: is_published
    select: {anon: public_rows_only, user: public_or_own_rows}
    insert: {anon: deny, user: own_rows_only}
defaults:
  anon: deny
  user: own_rows_only
fail_on: {evidence: confirmed, severity: high}
"""


def _cfg(text: str) -> ScanConfig:
    return ScanConfig.model_validate(yaml.safe_load(text))


def test_spec_example_parses() -> None:
    c = _cfg(SPEC_EXAMPLE)
    assert c.profile is Profile.AUDIT and c.authorized is True
    assert c.tables["posts"].select is not None
    assert c.tables["posts"].select.user is RowScope.PUBLIC_OR_OWN_ROWS
    assert c.tables["profiles"].insert is None          # falls back to defaults at resolve time
    assert [u.name for u in c.test_users] == [Role.USER_A, Role.USER_B]
    assert c.fail_on.evidence is Evidence.CONFIRMED and c.fail_on.severity is Severity.HIGH
    assert c.policy.tables.keys() == c.tables.keys()


def test_safe_defaults_when_omitted() -> None:
    c = _cfg("target: http://localhost:54321\n")
    assert c.authorized is False                       # NFR-02: never assumed
    assert c.profile is Profile.AUDIT                  # ADR-010: read-only by default
    assert c.rate_limit_rps == 5                       # NFR-04
    assert c.defaults.anon is RowScope.DENY and c.defaults.user is RowScope.OWN_ROWS_ONLY
    assert c.fail_on.severity is Severity.HIGH


@pytest.mark.parametrize("bad", [
    "target: http://x\ntables: {t: {selct: {anon: deny}}}\n",            # typo in op
    "target: http://x\ntables: {t: {select: {anon: nobody}}}\n",          # unknown scope
    "target: http://x\ntables: {t: {select: {user_a: deny}}}\n",          # roles are anon/user
    "target: ftp://x\n",                                                  # not http(s)
    "target: http://x\nrate_limit_rps: 0\n",
    "target: http://x\nprofile: prod\n",
])
def test_invalid_configs_are_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        _cfg(bad)


@pytest.mark.safety
def test_passwords_cannot_be_written_into_the_file() -> None:
    # SPEC §6: passwords only by env var name, so the file is safe to commit.
    with pytest.raises(ValidationError):
        _cfg("target: http://x\ntest_users: [{name: user_a, email: a@t, password: hunter2}]\n")
    with pytest.raises(ValidationError):
        _cfg("target: http://x\ntest_users: [{name: user_a, email: a@t, password_env: 'hunter2!'}]\n")


def test_test_users_are_user_a_and_user_b_once_each() -> None:
    with pytest.raises(ValidationError):
        _cfg("target: http://x\ntest_users: [{name: anon, email: a@t, password_env: P}]\n")
    with pytest.raises(ValidationError):
        _cfg("target: http://x\ntest_users: [{name: user_a, email: a@t, password_env: P},"
             " {name: user_a, email: b@t, password_env: Q}]\n")


def test_expected_access_review_flag() -> None:
    from rlsentry.contracts.models import Op
    e = ExpectedAccess(target="t", op=Op.SELECT, role=Role.USER_A, scope=RowScope.OWN_ROWS_ONLY)
    assert not e.is_review
    assert e.model_copy(update={"review_reason": "no owner column"}).is_review


def test_table_primary_key_is_optional_and_typed() -> None:
    c = _cfg("target: http://x\ntables: {diary: {primary_key: [id], owner_column: owner_id}}\n")
    assert c.tables["diary"].primary_key == ["id"]
    assert _cfg("target: http://x\ntables: {t: {}}\n").tables["t"].primary_key is None
    with pytest.raises(ValidationError):
        _cfg("target: http://x\ntables: {t: {primary_key: id}}\n")
