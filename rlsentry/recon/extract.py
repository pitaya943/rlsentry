"""Extraction of Supabase URLs, client pairs and key candidates from scanned text (FR-02)."""
from __future__ import annotations

import math
from collections import Counter

from rlsentry.contracts.recon import (
    ASSIGN_TAIL_RE,
    CLIENT_PAIR_RE,
    ENTROPY_MIN,
    GENERIC_MAX_LEN,
    GENERIC_MIN_LEN,
    KEY_CONTEXT_RE,
    LITERAL_RE,
    SB_ENTROPY_MIN,
    SUPABASE_HOST_RE,
    Candidate,
)
from rlsentry.contracts.safety import JWT_RE, SB_KEY_RE

_CONTEXT_WINDOW = 64


def shannon_entropy(s: str) -> float:
    """Bits per character; why: separates real keys from words, hashes of low variety and placeholders."""
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values()) + 0.0


def supabase_hosts(text: str) -> list[str]:
    """Hosted project URLs in first-occurrence order, deduplicated."""
    return list(dict.fromkeys(m.group(0) for m in SUPABASE_HOST_RE.finditer(text)))


def client_pairs(text: str) -> list[tuple[str, str]]:
    """(url, key) of adjacent literals where the key really is a JWT or sb_ key.

    Why: minified createClient calls have no recognisable function name."""
    pairs: list[tuple[str, str]] = []
    for m in CLIENT_PAIR_RE.finditer(text):
        key = m.group(4)
        if not (JWT_RE.fullmatch(key) or SB_KEY_RE.fullmatch(key)):
            continue
        pair = (m.group(2).rstrip("/"), key)
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def _in_key_context(text: str, quote_pos: int) -> bool:
    before = text[max(0, quote_pos - _CONTEXT_WINDOW):quote_pos]
    tail = ASSIGN_TAIL_RE.search(before)
    return tail is not None and KEY_CONTEXT_RE.search(tail.group(1)) is not None


def key_candidates(text: str) -> list[Candidate]:
    """JWTs, sb_ keys and entropy-filtered generic keys in key context, ordered by position."""
    found: list[tuple[int, Candidate]] = []
    seen: set[str] = set()
    spans: list[tuple[int, int]] = []

    for m in JWT_RE.finditer(text):
        spans.append(m.span())
        if m.group(0) not in seen:
            seen.add(m.group(0))
            found.append((m.start(), Candidate(value=m.group(0), form="jwt")))

    for m in SB_KEY_RE.finditer(text):
        value = m.group(0)
        spans.append(m.span())
        if value in seen:
            continue
        if value.startswith("sb_secret_"):
            cand = Candidate(value=value, form="sb_secret")
            rest = value[len("sb_secret_"):]
        else:
            cand = Candidate(value=value, form="sb_publishable")
            rest = value[len("sb_publishable_"):]
        if shannon_entropy(rest) >= SB_ENTROPY_MIN:
            seen.add(value)
            found.append((m.start(), cand))

    for m in LITERAL_RE.finditer(text):
        s = m.group(2)
        start, end = m.span(2)
        if any(start < e and b < end for b, e in spans):
            continue
        if not GENERIC_MIN_LEN <= len(s) <= GENERIC_MAX_LEN or s in seen:
            continue
        if s.startswith(("http://", "https://")):
            continue
        if not (any(ch.isascii() and ch.isdigit() for ch in s)
                and any(ch.isascii() and ch.isalpha() for ch in s)):
            continue
        if shannon_entropy(s) < ENTROPY_MIN or not _in_key_context(text, m.start()):
            continue
        seen.add(s)
        found.append((start, Candidate(value=s, form="generic")))

    found.sort(key=lambda t: t[0])
    return [c for _, c in found]
