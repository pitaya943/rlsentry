"""mask, mask_text (T-052). NFR-03; contract: rlsentry/contracts/safety.py."""
import pytest

from rlsentry.contracts.safety import MASK_FILL, MASK_MIN_LEN
from rlsentry.safety.mask import mask, mask_text

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.SIGNATUREsignature0123"
# Built at runtime from a fake body: a literal in the sb_secret_ format trips GitHub push
# protection (it did once, see PRODUCTION_LOG MS1).
SB = "sb_" + "secret_" + "FAKEfakeFAKEfake-0123_x"


@pytest.mark.safety
def test_long_secret_keeps_head_and_tail() -> None:
    assert mask(JWT) == JWT[:6] + MASK_FILL + JWT[-4:]
    assert mask(SB) == SB[:6] + MASK_FILL + SB[-4:]


@pytest.mark.safety
@pytest.mark.parametrize("n", [0, 1, 10, MASK_MIN_LEN - 1])
def test_short_secret_fully_hidden(n: int) -> None:
    assert mask("x" * n) == MASK_FILL


def test_boundary_length_is_partially_shown() -> None:
    s = "abcdefghijklmnopqrst"
    assert len(s) == MASK_MIN_LEN
    assert mask(s) == "abcdef" + MASK_FILL + "qrst"


@pytest.mark.safety
def test_mask_text_hides_every_secret_and_keeps_the_rest() -> None:
    text = f"curl -H 'apikey: {JWT}' -H 'Authorization: Bearer {JWT}' x={SB} done"
    out = mask_text(text)
    assert JWT not in out and SB not in out
    assert out == f"curl -H 'apikey: {mask(JWT)}' -H 'Authorization: Bearer {mask(JWT)}' x={mask(SB)} done"


def test_mask_text_idempotent_and_plain_text_unchanged() -> None:
    text = f"token={JWT};key={SB}"
    assert mask_text(mask_text(text)) == mask_text(text)
    assert mask_text("GET /rest/v1/notes?id=eq.5 HTTP/1.1") == "GET /rest/v1/notes?id=eq.5 HTTP/1.1"
