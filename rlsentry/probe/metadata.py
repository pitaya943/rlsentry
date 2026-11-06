"""probe/metadata.py (L03 USER_METADATA_ESCALATION; ADR-029). Contract: rlsentry/contracts/probe.py.

⚠ writes to the test user's OWN Auth record (dev/ci only; refused in audit by the SafeClient gate).
"""
import httpx

from rlsentry.contracts.safety import SafeClientContract


def _user_url(supabase_url: str) -> str:
    return supabase_url.rstrip("/") + "/auth/v1/user"


async def escalate_user_metadata(client: SafeClientContract, supabase_url: str, anon_key: str,
                                  token: str) -> tuple[str, bool]:
    """Set `user_metadata.role` to "admin" on the caller's own Auth record (SPEC §5 M3, L03).

    Why: some RLS policies trust `auth.jwt() -> 'user_metadata' -> 'role'`, which a user can set
    on themselves via the Auth API. Re-login (to pick up the new JWT claim) is the caller's job.
    """
    url = _user_url(supabase_url)
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
    resp = await client.request("PUT", url, headers=headers, json={"data": {"role": "admin"}})
    return resp.reason_phrase, resp.status_code == 200


async def read_user_metadata_role(client: SafeClientContract, supabase_url: str, anon_key: str,
                                  token: str) -> tuple[bool, object]:
    """Read the caller's own `user_metadata.role` before escalating (MS7, ADR-051 #3).

    Why: the MS6 restore always cleared the role to null (ADR-047 known limit). MS7 instead puts
    back the value the account had before escalation, so this reads it first. The value is kept
    only in memory by the caller; it must never be written to a note, finding or report.
    """
    url = _user_url(supabase_url)
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
    try:
        resp = await client.request("GET", url, headers=headers)
    except httpx.HTTPError:
        return False, None
    if resp.status_code != 200:
        return False, None
    try:
        body = resp.json()
    except ValueError:
        return False, None
    if not isinstance(body, dict):
        return False, None
    user_metadata = body.get("user_metadata")
    if user_metadata is None:
        return True, None
    if not isinstance(user_metadata, dict):
        return False, None
    return True, user_metadata.get("role")


async def restore_user_metadata(client: SafeClientContract, supabase_url: str, anon_key: str,
                                 token: str, original: object = None) -> bool:
    """Put back `role` (default None, clearing it) on the caller's own Auth record.

    Why a bool: a failed restore must be reportable by the caller (ADR-047), so a transport error
    returns False instead of raising, and any non-200 answer is also False. Known limit: the
    Auth API merges user_metadata, so a role that was absent before comes back as null, not
    absent.
    """
    url = _user_url(supabase_url)
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
    try:
        resp = await client.request("PUT", url, headers=headers,
                                    json={"data": {"role": original}})
    except httpx.HTTPError:
        return False
    return resp.status_code == 200
