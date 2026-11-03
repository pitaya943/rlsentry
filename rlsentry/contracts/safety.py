"""Safety layer contracts (SPEC §5 Safety 層; NFR-01..04). Owned by the architect.

Every module that talks to a target goes through these functions, so a bug here is a bug in
every scan. Implementations live in rlsentry/safety/<name>.py with the same names and
signatures (tickets in docs/tickets, MS1). They import the constants below instead of
redefining them, so the tests and the implementation can never disagree on a value.

Decisions: ADR-014 (#1 login exception, #3 RPC never POSTed), ADR-017 (ci write_hosts),
ADR-010 (safe defaults).
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime
from typing import Any, Protocol, Self

from rlsentry.contracts.models import AuthorizationRecord, Profile
from rlsentry.contracts.policy import ScanConfig

TOOL_VERSION = "0.0.0"
"""Must equal [project].version in pyproject.toml (tests check it)."""

USER_AGENT = f"RLSentry/{TOOL_VERSION}"
"""SPEC §5 可識別流量: every request carries exactly this User-Agent."""

READ_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})
"""The only methods that never reach the write gate's refusal logic."""

LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})
"""Hosts dev and ci may always write to (lab / local Supabase)."""

LOGIN_PATH = "/auth/v1/token"
LOGIN_QUERY = "grant_type=password"
"""ADR-014 #1: `POST <LOGIN_PATH>?<LOGIN_QUERY>` is the one non-GET request every profile may
send (test-user login, FR-07). Matched exactly: same path, query string exactly LOGIN_QUERY."""

RPC_PATH_PREFIX = "/rest/v1/rpc/"
"""ADR-014 #3: RPCs are called with GET/HEAD only, in every profile; any other method on a path
starting with this prefix is refused even where writes are allowed."""

MASK_HEAD = 6
MASK_TAIL = 4
MASK_FILL = "****"
MASK_MIN_LEN = 20
"""NFR-03: keep the first 6 and last 4 characters. Secrets shorter than MASK_MIN_LEN are
replaced by MASK_FILL alone, because 6 + 4 visible characters of a short secret would reveal
most of it."""

JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
SB_KEY_RE = re.compile(r"sb_(?:secret|publishable)_[A-Za-z0-9_-]{10,}")
"""Secrets that mask_text must find in free text (JWTs, including anon keys, and new-format
Supabase keys). Anything matched is replaced by mask(match)."""

WRITE_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::\d{1,5})?$")
"""Format of one ScanConfig.write_hosts entry after lower-casing (ADR-017): a bare host name or
IPv4 address, optionally with :port. No scheme, path, wildcard, whitespace or IPv6."""


# --- function contracts --------------------------------------------------------------------

def authorize(config: ScanConfig, *, cli_confirmed: bool, confirmed_by: str,
              profile: Profile | None = None, now: datetime | None = None) -> AuthorizationRecord:
    """Contract only; implemented by rlsentry.safety.gate.authorize (NFR-02).

    Called before any request is sent. Rules:
    1. Neither `config.authorized` nor `cli_confirmed` → raise
       rlsentry.contracts.interfaces.AuthorizationRefused; the message names both ways to
       confirm (`--i-own-this-target`, `authorized: true`).
    2. `confirmed_by` stripped of whitespace must be non-empty, else AuthorizationRefused.
    3. method = "cli_flag" when cli_confirmed (even if the config also says authorized),
       else "config".
    4. confirmed_at = `now` if given, else the current UTC time; a naive `now` (no tzinfo)
       raises ValueError, because the report must state an unambiguous time.
    5. write_hosts = list(config.write_hosts) when the effective profile is ci, else [];
       effective profile = `profile` if given, else config.profile (ADR-017 #3: the report
       lists the hosts this run may write to; dev and audit never write to remote hosts).
    No I/O, no network.
    """
    raise NotImplementedError


def require_write_allowed(profile: Profile, method: str, url: str,
                          write_hosts: Iterable[str] = ()) -> None:
    """Contract only; implemented by rlsentry.safety.mode.require_write_allowed (NFR-01).

    Returns None when the request may be sent; otherwise raises
    rlsentry.contracts.interfaces.WriteRefused. `method` is compared case-insensitively.
    The URL is parsed with urllib.parse.urlsplit; its scheme must be http or https and it must
    have a host, else WriteRefused (for every method). Host comparison is on
    `urlsplit(url).hostname` (lower-case, so "http://localhost@evil.test/" is evil.test).
    Rules, first match wins:
    1. method in READ_METHODS → allowed (any profile, any host).
    2. path starts with RPC_PATH_PREFIX → refused (ADR-014 #3).
    3. method is POST, path == LOGIN_PATH and query == LOGIN_QUERY → allowed (ADR-014 #1).
    4. profile audit → refused.
    5. host in LOCAL_HOSTS → allowed (dev and ci).
    6. profile ci and the host matches a `write_hosts` entry → allowed (ADR-017). An entry
       without a port matches the host on any port; an entry "host:port" matches only when the
       URL states that port explicitly. Entries are compared lower-cased; no wildcards.
    7. anything else → refused (dev never writes to a remote host, even if listed).
    The WriteRefused message names the profile, method and host, never the query string or
    headers (they may carry tokens or row ids). No I/O.
    """
    raise NotImplementedError


def mask(secret: str) -> str:
    """Contract only; implemented by rlsentry.safety.mask.mask (NFR-03).

    len(secret) < MASK_MIN_LEN → MASK_FILL. Otherwise
    secret[:MASK_HEAD] + MASK_FILL + secret[-MASK_TAIL:]. Pure function.
    """
    raise NotImplementedError


def mask_text(text: str) -> str:
    """Contract only; implemented by rlsentry.safety.mask.mask_text (NFR-03).

    Replace every JWT_RE and SB_KEY_RE match in `text` with mask(match); everything else is
    unchanged. Used on evidence (curl commands), logs and error messages before output.
    Applying it twice gives the same result as applying it once.
    """
    raise NotImplementedError


class RateLimiterContract(Protocol):
    """Implemented by rlsentry.safety.ratelimit.RateLimiter (NFR-04; SPEC §5: asyncio
    semaphore + token bucket).

    Constructor: RateLimiter(rps: float = 5.0, concurrency: int = 4, *,
                             clock: Callable[[], float] = time.monotonic,
                             sleep: Callable[[float], Awaitable[None]] = asyncio.sleep)
    rps <= 0 or concurrency < 1 → ValueError.
    Bucket capacity is 1 token, refilled at `rps` tokens per second, starting full. Each
    `async with limiter:` waits for a semaphore slot, then for a token (by awaiting `sleep`
    for exactly the missing time, using `clock`), then consumes it. Consequently the k-th
    entry (0-based) happens no earlier than first_entry + k / rps, and at most `concurrency`
    bodies run at once. The semaphore is released on exit even when the body raises.
    """

    async def __aenter__(self) -> None: ...

    async def __aexit__(self, *exc: object) -> None: ...


class SafeClientContract(Protocol):
    """Implemented by rlsentry.safety.http.SafeClient: the ONLY HTTP client in rlsentry.

    Constructor: SafeClient(*, profile: Profile, limiter: RateLimiter,
                            write_hosts: Iterable[str] = (),
                            transport: httpx.AsyncBaseTransport | None = None,
                            timeout: float = 10.0)
    `transport` exists for tests (httpx.MockTransport); production passes None.
    request():
    1. builds the final URL (url plus `params`, as httpx would send it) and calls
       require_write_allowed(profile, method, final_url, write_hosts) BEFORE waiting on the
       limiter or sending anything; WriteRefused propagates and nothing is sent;
    2. sends inside `async with limiter:`;
    3. sets the User-Agent header to USER_AGENT, replacing any caller value;
    4. never follows redirects (a 3xx is returned as is), so a redirect cannot carry a write
       or a token to another host.
    Usable as `async with SafeClient(...) as client:`; aclose() closes the transport.
    """

    async def request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None,
                      params: Mapping[str, str] | None = None, json: Any = None) -> Any: ...

    async def aclose(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *exc: object) -> None: ...


Sleep = Callable[[float], Awaitable[None]]
"""Type of the injectable sleep function of RateLimiter."""
