"""Write gate (NFR-01). Contract: rlsentry/contracts/safety.py::require_write_allowed.

Why: every request passes through here before being sent, so only reads, the test-user login
and (profile permitting) writes to local or explicitly listed hosts can leave the process.
"""
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.contracts.safety import (
    LOCAL_HOSTS,
    LOGIN_PATH,
    LOGIN_QUERY,
    READ_METHODS,
    RPC_PATH_PREFIX,
)


def _refuse(profile: Profile, method: str, host: str, reason: str) -> WriteRefused:
    return WriteRefused(f"{reason}: profile={profile.value} method={method} host={host}")


def _host_listed(host: str, port: int | None, write_hosts: Iterable[str]) -> bool:
    for entry in write_hosts:
        name, sep, entry_port = entry.strip().lower().partition(":")
        if name != host:
            continue
        if not sep:
            return True
        if port is not None and entry_port == str(port):
            return True
    return False


def require_write_allowed(profile: Profile, method: str, url: str,
                          write_hosts: Iterable[str] = ()) -> None:
    """Raise WriteRefused unless this request may be sent under `profile` (NFR-01).

    Why: a single choke point keeps audit/dev/ci write rules, the login exception (ADR-014 #1),
    the RPC ban (ADR-014 #3) and the ci write_hosts allow-list (ADR-017) consistent.
    """
    method_u = method.upper()
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise _refuse(profile, method_u, "?", "invalid URL") from None
    if parts.scheme not in ("http", "https") or not host:
        raise _refuse(profile, method_u, host or "?", "URL must be http(s) with a host")
    if method_u in READ_METHODS:
        return
    if parts.path.startswith(RPC_PATH_PREFIX):
        raise _refuse(profile, method_u, host, "RPC is never called with a write method")
    if method_u == "POST" and parts.path == LOGIN_PATH and parts.query == LOGIN_QUERY:
        return
    if profile == Profile.AUDIT:
        raise _refuse(profile, method_u, host, "audit profile is read-only")
    if host in LOCAL_HOSTS:
        return
    if profile == Profile.CI and _host_listed(host, port, write_hosts):
        return
    raise _refuse(profile, method_u, host, "write to this host is not allowed")
