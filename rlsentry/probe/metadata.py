"""probe/metadata.py (L03 USER_METADATA_ESCALATION; ADR-029). Contract: rlsentry/contracts/probe.py.

⚠ writes to the test user's OWN Auth record (dev/ci only; refused in audit by the SafeClient gate).
"""
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


async def restore_user_metadata(client: SafeClientContract, supabase_url: str, anon_key: str,
                                 token: str) -> None:
    """Clear the `role` set by `escalate_user_metadata`, leaving the test account as found.

    Best effort: a non-200 response is ignored, since the caller already recorded the escalation.
    """
    url = _user_url(supabase_url)
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}
    await client.request("PUT", url, headers=headers, json={"data": {"role": None}})
