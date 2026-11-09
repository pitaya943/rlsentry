"""load_config must not echo file content in errors (T-031/T-032; NFR-03, auditor F5)."""
import pytest

from rlsentry.contracts.policy import ConfigError
from rlsentry.policy.load import load_config


@pytest.mark.safety
@pytest.mark.parametrize("text", [
    "target: http://x\ntest_users: [{name: user_a, password: hunter2SECRET\n",
    "target: http://x\nnote: 'hunter2SECRET\n",
    "target: http://x\n\tkey: hunter2SECRET\n",
])
def test_yaml_errors_never_echo_file_content(text: str) -> None:
    # NFR-03 / ConfigError contract: report where (line, column) and what kind of error,
    # never a snippet of the file (it may hold a pasted secret).
    with pytest.raises(ConfigError) as ei:
        load_config(text)
    msg = str(ei.value)
    assert "hunter2SECRET" not in msg and "hunter2" not in msg
    assert "line" in msg
