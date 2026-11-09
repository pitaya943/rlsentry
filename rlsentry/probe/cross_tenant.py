"""Known rows per test user for the cross-tenant comparison (FR-08)."""
import httpx

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import KNOWN_ROWS_LIMIT, USER_ROLES, KnownRow, KnownRows, Sessions
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.probe.paths import rest_url


async def collect_known_rows(client: SafeClientContract, supabase_url: str, anon_key: str,
                             target: Target, owner_column: str | None,
                             public_column: str | None, sessions: Sessions) -> KnownRows:
    """Why: each user lists only its own primary keys, so ownership is never guessed."""
    if len(target.primary_key) != 1:
        return KnownRows(notes=["needs a single-column primary key"])
    if owner_column is None:
        return KnownRows(notes=["no owner column"])
    pk = target.primary_key[0]
    url = rest_url(supabase_url, target)
    rows: list[KnownRow] = []
    notes: list[str] = []
    seen: set[str] = set()
    variants: list[tuple[str | None, bool]] = (
        [(None, False)] if public_column is None else [("is.true", True), ("is.false", False)])
    for role in USER_ROLES:
        token = sessions.tokens.get(role)
        uid = sessions.user_ids.get(role)
        if not token or not uid:
            continue
        for flt, public in variants:
            params = {"select": pk, owner_column: f"eq.{uid}", "limit": str(KNOWN_ROWS_LIMIT)}
            if public_column is not None and flt is not None:
                params[public_column] = flt
            headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
            try:
                resp = await client.request("GET", url, headers=headers, params=params)
                status = resp.status_code
                body = resp.json() if status == 200 else None
            except (httpx.HTTPError, ValueError) as exc:
                notes.append(f"{role.value}: {type(exc).__name__}")
                continue
            if status != 200 or not isinstance(body, list):
                notes.append(f"{role.value}: HTTP {status}")
                continue
            for item in body:
                if isinstance(item, dict) and item.get(pk) is not None:
                    key = str(item[pk])
                    if key not in seen:
                        seen.add(key)
                        rows.append(KnownRow(pk=key, owner=role, public=public))
    return KnownRows(rows=rows, notes=notes)
