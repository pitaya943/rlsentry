"""load_config (T-023). SPEC §6 rlsentry.yaml; contract: rlsentry/contracts/policy.py."""
import pytest

from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ConfigError, RowScope, ScanConfig
from rlsentry.policy.load import load_config

GOOD = """
target: http://localhost:54321
authorized: true
profile: dev
tables:
  posts:
    owner_column: author_id
    select: {anon: deny, user: own_rows_only}
"""


def test_loads_valid_text() -> None:
    c = load_config(GOOD)
    assert isinstance(c, ScanConfig) and c.profile is Profile.DEV
    assert c.tables["posts"].select is not None
    assert c.tables["posts"].select.user is RowScope.OWN_ROWS_ONLY


def test_error_names_the_key_path() -> None:
    with pytest.raises(ConfigError) as ei:
        load_config(GOOD.replace("anon: deny", "anon: nobody"))
    assert "tables.posts.select.anon" in str(ei.value)


def test_typo_key_is_an_error_with_path() -> None:
    with pytest.raises(ConfigError) as ei:
        load_config(GOOD.replace("select:", "selct:"))
    assert "tables.posts.selct" in str(ei.value)


@pytest.mark.parametrize("text", ["target: [unclosed", "- just\n- a list\n", "", "42"])
def test_non_mapping_or_broken_yaml_is_config_error(text: str) -> None:
    with pytest.raises(ConfigError):
        load_config(text)


@pytest.mark.safety
def test_env_vars_are_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLS_A_PW", "s3cret-value")
    c = load_config(GOOD + "test_users: [{name: user_a, email: a@test.dev, password_env: RLS_A_PW}]\n")
    assert "s3cret-value" not in c.model_dump_json()


def test_config_error_is_a_value_error() -> None:
    assert issubclass(ConfigError, ValueError)
