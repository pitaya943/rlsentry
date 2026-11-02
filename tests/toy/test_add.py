"""Stage 0 toy test (written by the human-frozen harness, not by an agent)."""
from rlsentry.toy import add


def test_add() -> None:
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
