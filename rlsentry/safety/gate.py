"""authorize (NFR-02; contract: rlsentry/contracts/safety.py; ADR-017 #3)."""
from __future__ import annotations

from datetime import UTC, datetime

from rlsentry.contracts.interfaces import AuthorizationRefused
from rlsentry.contracts.models import AuthorizationRecord, Profile
from rlsentry.contracts.policy import ScanConfig


def authorize(config: ScanConfig, *, cli_confirmed: bool, confirmed_by: str,
              profile: Profile | None = None, now: datetime | None = None) -> AuthorizationRecord:
    """Refuse to proceed unless the operator confirmed they own the target.

    Why: every scan must be traceable to a named, time-stamped confirmation (NFR-02). The CLI
    flag takes precedence in the record; write_hosts are listed only for ci (ADR-017 #3).
    """
    if not (config.authorized or cli_confirmed):
        raise AuthorizationRefused(
            "Target ownership not confirmed: pass --i-own-this-target or set "
            "`authorized: true` in the config."
        )
    who = confirmed_by.strip()
    if not who:
        raise AuthorizationRefused("confirmed_by must name the person confirming ownership.")
    if now is not None and now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware")
    effective = profile if profile is not None else config.profile
    return AuthorizationRecord(
        confirmed_by=who,
        method="cli_flag" if cli_confirmed else "config",
        confirmed_at=now if now is not None else datetime.now(UTC),
        write_hosts=list(config.write_hosts) if effective == Profile.CI else [],
    )
