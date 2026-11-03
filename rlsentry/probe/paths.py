"""Shared URL builder for PostgREST targets."""
from rlsentry.contracts.models import Target


def rest_url(supabase_url: str, target: Target) -> str:
    """Why: one place decides table vs RPC paths so every probe hits the same endpoint."""
    base = supabase_url.rstrip("/")
    prefix = "/rest/v1/rpc/" if target.kind == "rpc" else "/rest/v1/"
    return f"{base}{prefix}{target.name}"
