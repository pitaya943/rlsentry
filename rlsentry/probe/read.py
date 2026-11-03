"""probe/read.py (FR-06): HEAD + count, never a body. Contract: rlsentry/contracts/probe.py."""
import re

import httpx

from rlsentry.contracts.models import Target
from rlsentry.contracts.probe import CONTENT_RANGE_TOTAL_RE, CountResult
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
