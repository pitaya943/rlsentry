"""recon/classify.py: JWT decoded without verification, FR-03 classes, labels, findings (T-182)."""
from __future__ import annotations

import base64
import binascii
import json
import re

from rlsentry.contracts.models import Finding, KeyFinding, finding_id
from rlsentry.contracts.recon import (
    JWT_CLAIMS_KEPT,
    PUBLISHABLE_JWT_ROLES,
    SECRET_JWT_ROLES,
    Candidate,
    KeyKind,
)
from rlsentry.contracts.rules import RULES
from rlsentry.safety.mask import mask

_ROLE_LABEL_RE = re.compile(r"^[a-z_]+$")
Claims = dict[str, str | int | None]


def decode_jwt_claims(token: str) -> Claims | None:
    """Read role/ref/exp from a JWT without verifying it: we hold no key, and the server trusts
    these claims as written. Never raises; user-data claims are dropped (CLAUDE.md)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1]
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, binascii.Error):
        return None
    if not isinstance(data, dict):
        return None
    claims: Claims = {}
    for name in JWT_CLAIMS_KEPT:
        if name in data:
            v = data[name]
            claims[name] = v if isinstance(v, (str, int)) and not isinstance(v, bool) else None
    return claims


def classify_key(c: Candidate) -> tuple[KeyKind, str, Claims | None]:
    """Map a candidate to (kind, label, claims) per FR-03; every label fits KEY_LABEL_RE."""
    if c.form == "sb_publishable":
        return "publishable", "sb_publishable", None
    if c.form == "sb_secret":
        return "secret", "sb_secret", None
    if c.form != "jwt":
        return "unverified", "unverified", None
    claims = decode_jwt_claims(c.value)
    if claims is None:
        return "unverified", "unverified", None
    role = claims.get("role")
    if isinstance(role, str):
        if role in PUBLISHABLE_JWT_ROLES:
            return "publishable", f"jwt:{role}", claims
        if role in SECRET_JWT_ROLES:
            return "secret", f"jwt:{role}", claims
        if _ROLE_LABEL_RE.match(role):
            return "unverified", f"jwt:{role}", claims
    return "unverified", "unverified", claims


def key_finding(c: Candidate, source_file: str) -> KeyFinding:
    """Build the report-safe record of a key; only the masked value is kept (NFR-03)."""
    kind, label, claims = classify_key(c)
    return KeyFinding(kind=kind, label=label, masked=mask(c.value), source_file=source_file,
                      jwt_claims=claims)


def findings_from_keys(keys: list[KeyFinding]) -> list[Finding]:
    """One finding per distinct non-publishable label; publishable keys are public by design."""
    out: list[Finding] = []
    seen: set[str] = set()
    for k in keys:
        if k.kind == "publishable" or k.label in seen:
            continue
        seen.add(k.label)
        rule = "SECRET_KEY_IN_BUNDLE" if k.kind == "secret" else "UNVERIFIED_KEY"
        spec = RULES[rule]
        out.append(Finding(id=finding_id(k.label, None, None, rule), rule=rule,
                           evidence=spec.evidence, severity=spec.severity, target=k.label))
    return out
