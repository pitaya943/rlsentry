"""STAGE0 holdout: same behaviour as tests/toy/test_add.py, different inputs."""
from rlsentry.toy import add


def test_add_zero() -> None:
    assert add(0, 0) == 0


def test_add_commutative() -> None:
    for a, b in [(7, -3), (100, 23), (-5, -9)]:
        assert add(a, b) == add(b, a) == a + b
