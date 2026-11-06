"""probe/read.py (FR-06): HEAD + count, never a body. Contract: rlsentry/contracts/probe.py."""
import re

import httpx

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import CONTENT_RANGE_TOTAL_RE, CountResult, VisibleResult
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.probe.evidence import curl_command
from rlsentry.probe.paths import rest_url


def _literal(value: str) -> str:
    """Why: a double-quoted PostgREST literal keeps commas and quotes in a pk from splitting the list."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


async def count_visible(client: SafeClientContract, supabase_url: str, anon_key: str,
                        target: Target, token: str, pks: list[str]) -> CountResult:
    """Count how many of `pks` the token can see using one HEAD request.

    Why: HEAD with count=exact answers "visible or not" without downloading any row.
    """
    if not pks or len(target.primary_key) != 1:
        raise ValueError("count_visible needs non-empty pks and a single-column primary key")
    pk = target.primary_key[0]
    url = rest_url(supabase_url, target)
    params = {"select": pk, pk: "in.(" + ",".join(_literal(v) for v in pks) + ")"}
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}", "Prefer": "count=exact"}
    final_url = str(httpx.URL(url).copy_merge_params(params))
    curl = curl_command("HEAD", final_url, headers)
    try:
        resp = await client.request("HEAD", url, headers=headers, params=params)
    except httpx.HTTPError:
        return CountResult(queried=len(pks), status=None, total=None, curl=curl)
    match = re.match(CONTENT_RANGE_TOTAL_RE, resp.headers.get("Content-Range", ""))
    total = int(match.group(1)) if match else None
    return CountResult(queried=len(pks), status=resp.status_code, total=total, curl=curl)


async def visible_pks(client: SafeClientContract, supabase_url: str, anon_key: str,
                      target: Target, token: str, pks: list[str]) -> VisibleResult:
    """One GET of primary keys only: which of `pks` the token can see (ADR-040).

    Why: one request per (target, role) replaces two HEADs; a row outside the queried set
    means the filter was not applied, so the result is untrustworthy (ADR-023 #3).
    """
    if not pks or len(target.primary_key) != 1:
        raise ValueError("visible_pks needs non-empty pks and a single-column primary key")
    pk = target.primary_key[0]
    url = rest_url(supabase_url, target)
    params = {"select": pk, pk: "in.(" + ",".join(_literal(v) for v in pks) + ")",
              "limit": str(len(pks))}
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
    curl = curl_command("GET", str(httpx.URL(url).copy_merge_params(params)), headers)
    try:
        resp = await client.request("GET", url, headers=headers, params=params)
    except httpx.HTTPError:
        return VisibleResult(queried=len(pks), status=None, visible=None, curl=curl)
    visible: list[str] | None = None
    if resp.status_code in (200, 206):
        try:
            body = resp.json()
        except ValueError:
            body = None
        if isinstance(body, list) and all(isinstance(i, dict) and i.get(pk) is not None for i in body):
            seen = list(dict.fromkeys(str(i[pk]) for i in body))
            if set(seen) <= set(pks):
                visible = seen
    return VisibleResult(queried=len(pks), status=resp.status_code, visible=visible, curl=curl)


def observation_counts(res: VisibleResult | None, forbidden: list[str],
                       permitted: list[str]) -> tuple[CountResult | None, CountResult | None]:
    """Split one VisibleResult back into the forbidden / permitted CountResults (pure, ADR-040)."""
    def one(pks: list[str]) -> CountResult | None:
        if not pks:
            return None
        if res is None:
            raise ValueError("observation_counts needs a VisibleResult for non-empty pk lists")
        total = len(set(res.visible) & set(pks)) if res.visible is not None else None
        return CountResult(queried=len(pks), status=res.status, total=total, curl=res.curl)
    return one(forbidden), one(permitted)
