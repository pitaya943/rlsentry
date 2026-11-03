"""probe/session.py (FR-07). Contract: rlsentry/contracts/probe.py (login, build_sessions).

Errors carry only an HTTP status or an exception class name: never a password, token or
response body (NFR-03).
"""
from __future__ import annotations

import base64
import json
from collections.abc import Mapping

import httpx

from rlsentry.contracts.models import Role
from rlsentry.contracts.policy import TestUser
from rlsentry.contracts.probe import USER_ROLES, LoginFailed, Sessions
from rlsentry.contracts.safety import SafeClientContract


def _subject(token: object) -> str | None:
    """Return the JWT `sub` (signature unchecked: the token came straight from the server)."""
    if not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        mid = parts[1]
        payload = json.loads(base64.urlsafe_b64decode(mid + "=" * (-len(mid) % 4)))
    except ValueError:
        return None
    sub = payload.get("sub") if isinstance(payload, dict) else None
    return sub if isinstance(sub, str) else None


async def login(client: SafeClientContract, supabase_url: str, anon_key: str, email: str,
                password: str) -> tuple[str, str]:
    """Password-grant login; returns (access_token, sub) or raises a secret-free LoginFailed."""
    try:
        resp = await client.request(
            "POST", supabase_url.rstrip("/") + "/auth/v1/token",
            headers={"apikey": anon_key}, params={"grant_type": "password"},
            json={"email": email, "password": password})
    except httpx.HTTPError as exc:
        raise LoginFailed(f"login failed: {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise LoginFailed(f"login failed: HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        raise LoginFailed("login failed: HTTP 200") from None
    token = body.get("access_token") if isinstance(body, dict) else None
    sub = _subject(token)
    if sub is None or not isinstance(token, str):
        raise LoginFailed("login failed: HTTP 200")
    return token, sub


async def build_sessions(client: SafeClientContract, supabase_url: str, anon_key: str,
                         users: list[TestUser], env: Mapping[str, str]) -> Sessions:
    """Log in every configured test user; a failure only marks that role as missing."""
    tokens: dict[Role, str] = {Role.ANON: anon_key}
    user_ids: dict[Role, str] = {}
    missing: dict[Role, str] = {}
    for user in users:
        password = env.get(user.password_env)
        if not password:
            missing[user.name] = f"{user.password_env} is not set"
            continue
        try:
            tokens[user.name], user_ids[user.name] = await login(
                client, supabase_url, anon_key, user.email, password)
        except LoginFailed as exc:
            missing[user.name] = str(exc)
    for role in USER_ROLES:
        if role not in tokens and role not in missing:
            missing[role] = "no test account configured"
    return Sessions(tokens=tokens, user_ids=user_ids, missing=missing)
