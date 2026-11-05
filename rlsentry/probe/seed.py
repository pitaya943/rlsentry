"""Canary rows seeded by their owners before dev/ci probing (FR-09, ADR-029)."""
import uuid

import httpx

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import (
    CANARY_PREFIX,
    USER_ROLES,
    WRITE_NO_OWNER_REASON,
    SeededRow,
    Sessions,
)
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.probe.paths import rest_url


async def seed_known_rows(client: SafeClientContract, supabase_url: str, anon_key: str,
                          target: Target, owner_column: str | None, public_column: str | None,
                          text_column: str | None, sessions: Sessions) -> tuple[list[SeededRow], list[str]]:
    """Why: owners create the rows themselves so the scanner knows pk and owner without reading
    real data, and can delete them later. Only tables are seeded; the safety layer's lab-mode
    check still gates every POST."""
    if len(target.primary_key) != 1 or owner_column is None or target.kind != "table":
        return [], [WRITE_NO_OWNER_REASON]
    pk_col = target.primary_key[0]
    url = rest_url(supabase_url, target)
    rows: list[SeededRow] = []
    notes: list[str] = []
    variants = [False] if public_column is None else [False, True]
    for role in USER_ROLES:
        token = sessions.tokens.get(role)
        uid = sessions.user_ids.get(role)
        if not token or not uid:
            continue
        for public in variants:
            pk = str(uuid.uuid4())
            marker = CANARY_PREFIX + uuid.uuid4().hex
            body: dict[str, object] = {pk_col: pk, owner_column: uid}
            if public_column is not None:
                body[public_column] = public
            if text_column is not None:
                body[text_column] = marker
            headers = {"apikey": anon_key, "Authorization": f"Bearer {token}",
                       "Prefer": "return=minimal", "Content-Type": "application/json"}
            try:
                resp = await client.request("POST", url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                notes.append(f"{role.value}: seed {type(exc).__name__}")
                continue
            if 200 <= resp.status_code < 300:
                rows.append(SeededRow(target=target.name, pk=pk, owner=role, marker=marker,
                                      public=public, text_column=text_column))
            else:
                notes.append(f"{role.value}: seed HTTP {resp.status_code}")
    return rows, notes
