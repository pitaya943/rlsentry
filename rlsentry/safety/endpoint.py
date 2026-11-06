"""Supabase API URL selection (S4; ADR-043): the endpoint is named by the user, never inferred."""
from __future__ import annotations

from urllib.parse import urlsplit

from rlsentry.contracts.pipeline import EndpointRefused
from rlsentry.contracts.policy import ScanConfig
from rlsentry.recon.links import report_url

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _refuse(url: str, reason: str) -> EndpointRefused:
    return EndpointRefused(f"invalid Supabase URL {report_url(url)}: {reason}")


def normalize_api_url(url: str) -> str:
    """Canonical base URL used for every comparison.

    Why: two spellings of one host must compare equal, and a URL carrying userinfo, query or a
    path must never be accepted as an API base (it could smuggle credentials or redirect probes).
    """
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise _refuse(url, "cannot be parsed") from None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise _refuse(url, "scheme must be http or https")
    if not host:
        raise _refuse(url, "host is missing")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise _refuse(url, "credentials are not allowed")
    if parts.query or "?" in url:
        raise _refuse(url, "a query string is not allowed")
    if parts.fragment or "#" in url:
        raise _refuse(url, "a fragment is not allowed")
    if parts.path not in ("", "/"):
        raise _refuse(url, "a path is not allowed")
    shown = f"[{host}]" if ":" in host else host
    suffix = "" if port is None or port == _DEFAULT_PORTS[scheme] else f":{port}"
    return f"{scheme}://{shown}{suffix}"


def resolve_endpoint(config: ScanConfig, cli_supabase_url: str | None,
                     recon_url: str | None) -> tuple[str, str]:
    """Pick the API endpoint from the config or the CLI flag; a bundle URL is never enough.

    Why: a URL found in a frontend bundle is attacker-influenced data; requiring the user to
    name it keeps requests from going to a host nobody authorized (NFR-02, MS5 note 6).
    """
    if (config.supabase_url and cli_supabase_url
            and normalize_api_url(config.supabase_url) != normalize_api_url(cli_supabase_url)):
        raise EndpointRefused("--supabase-url and supabase_url in the config disagree")
    if config.supabase_url:
        return normalize_api_url(config.supabase_url), "config"
    if cli_supabase_url:
        return normalize_api_url(cli_supabase_url), "cli_flag"
    if recon_url is not None:
        shown = report_url(recon_url)
        raise EndpointRefused(
            f"the frontend bundle points at {shown}; to scan it, add `supabase_url: {shown}` "
            f"to the config or pass --supabase-url {shown}")
    raise EndpointRefused("no Supabase URL: set supabase_url in the config or pass --supabase-url")
