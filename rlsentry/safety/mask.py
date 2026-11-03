"""mask, mask_text (NFR-03); contract: rlsentry/contracts/safety.py."""
from __future__ import annotations

import re

from rlsentry.contracts.safety import (
    JWT_RE,
    MASK_FILL,
    MASK_HEAD,
    MASK_MIN_LEN,
    MASK_TAIL,
    SB_KEY_RE,
)


def mask(secret: str) -> str:
    """Hide a secret, keeping head and tail only when long enough that this reveals little.

    Short secrets become MASK_FILL alone: showing 10 characters of a short one would leak most of it.
    """
    if len(secret) < MASK_MIN_LEN:
        return MASK_FILL
    return secret[:MASK_HEAD] + MASK_FILL + secret[-MASK_TAIL:]


def _sub(match: re.Match[str]) -> str:
    return mask(match.group(0))


def mask_text(text: str) -> str:
    """Mask every JWT and Supabase key in free text before it reaches output or logs.

    Idempotent: a masked value no longer matches either pattern.
    """
    return SB_KEY_RE.sub(_sub, JWT_RE.sub(_sub, text))
