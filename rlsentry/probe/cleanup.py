"""probe/cleanup.py (FR-09 清理): delete every seeded canary as its owner, report leftovers.
Contract: rlsentry/contracts/probe.py (cleanup_seeded)."""
import re

import httpx

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import CONTENT_RANGE_TOTAL_RE, SeededRow, Sessions
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.probe.paths import rest_url


async def _gone(client: SafeClientContract, url: str, headers: dict[str, str], pk_col: str,
                pk: str) -> bool:
    """Why: a DELETE answering 2xx proves nothing (RLS may filter it to 0 rows); count confirms."""
    params = {"select": pk_col, pk_col: f"eq.{pk}"}
    resp = await client.request("HEAD", url, headers={**headers, "Prefer": "count=exact"}, params=params)
    match = re.match(CONTENT_RANGE_TOTAL_RE, resp.headers.get("Content-Range", ""))
    return resp.status_code in (200, 206) and match is not None and int(match.group(1)) == 0


async def cleanup_seeded(client: SafeClientContract, supabase_url: str, anon_key: str,
                         target: Target, seeded: list[SeededRow],
                         sessions: Sessions) -> list[SeededRow]:
    """Delete each canary with its owner's token, confirm by count, return rows still present.

    Why: each identity only deletes rows it owns, so cleanup is never a cross-tenant action;
    any row that cannot be deleted or confirmed is reported, never assumed gone. WriteRefused
    (audit profile) is deliberately not caught.
    """
    if len(target.primary_key) != 1:
        return list(seeded)
    pk_col = target.primary_key[0]
    url = rest_url(supabase_url, target)
    left: list[SeededRow] = []
    for row in seeded:
        token = sessions.tokens.get(row.owner)
        if token is None:
            left.append(row)
            continue
        headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
        try:
            await client.request("DELETE", url, headers={**headers, "Prefer": "return=minimal"},
                                 params={pk_col: f"eq.{row.pk}"})
            if not await _gone(client, url, headers, pk_col, row.pk):
                left.append(row)
        except httpx.HTTPError:
            left.append(row)
    return left
