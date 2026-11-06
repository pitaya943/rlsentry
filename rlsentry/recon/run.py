"""recon/run.py: M1 entry point wiring fetch, extract and classify (T-187; FR-01..03, NFR-03)."""
from __future__ import annotations

from rlsentry.contracts.models import KeyFinding, ReconResult
from rlsentry.contracts.recon import (
    MAX_FILE_BYTES,
    MAX_FILES,
    Candidate,
    CandidateForm,
    FetchedFile,
    ReconOutput,
)
from rlsentry.contracts.safety import JWT_RE, SafeClientContract
from rlsentry.recon.classify import classify_key, findings_from_keys, key_finding
from rlsentry.recon.extract import client_pairs, key_candidates, supabase_hosts
from rlsentry.recon.fetch import fetch_bundle


def _pair_form(key: str) -> CandidateForm:
    """Form of a client-pair key (already known to match JWT_RE or SB_KEY_RE)."""
    if JWT_RE.fullmatch(key):
        return "jwt"
    return "sb_secret" if key.startswith("sb_secret_") else "sb_publishable"


def _collect_keys(files: list[FetchedFile]) -> list[KeyFinding]:
    """Why: one KeyFinding per (raw value, file); the raw value never leaves this function."""
    keys: list[KeyFinding] = []
    seen: set[tuple[str, str]] = set()
    for f in files:
        for c in key_candidates(f.text):
            if (c.value, f.url) in seen:
                continue
            seen.add((c.value, f.url))
            keys.append(key_finding(c, f.url))
    return keys


def _pick_url_and_anon(files: list[FetchedFile]) -> tuple[str | None, str | None]:
    """supabase_url and anon_key by the contract's priority order (built files outrank maps)."""
    built = [f for f in files if f.kind in ("html", "js")]
    sources = [f for f in files if f.kind == "map_source"]
    pairs: list[tuple[str, str]] = []
    for group in (built, sources):
        for f in group:
            pairs.extend(client_pairs(f.text))
    url: str | None = pairs[0][0] if pairs else None
    if url is None:
        for group in (built, sources):
            for f in group:
                hosts = supabase_hosts(f.text)
                if hosts:
                    url = hosts[0]
                    break
            if url is not None:
                break
    anon: str | None = None
    if url is not None:
        for u, k in pairs:
            if u == url and classify_key(Candidate(k, _pair_form(k)))[0] == "publishable":
                anon = k
                break
    if anon is None:
        for f in files:
            for c in key_candidates(f.text):
                if classify_key(c)[0] == "publishable":
                    return url, c.value
    return url, anon


async def recon(client: SafeClientContract, target_url: str, *, max_files: int = MAX_FILES,
                max_bytes: int = MAX_FILE_BYTES) -> ReconOutput:
    """Fetch the target's bundle and report Supabase URL, keys and scan scope.

    Why: the report must show what was scanned and skipped, and keys only in masked form.
    """
    fetched = await fetch_bundle(client, target_url, max_files=max_files, max_bytes=max_bytes)
    files = fetched.files
    keys = _collect_keys(files)
    supabase_url, anon_key = _pick_url_and_anon(files)
    result = ReconResult(
        supabase_url=supabase_url,
        keys=keys,
        chunks_scanned=[f.url for f in files if f.kind in ("html", "js", "map")],
        chunks_skipped=fetched.skipped,
    )
    return ReconOutput(
        result=result,
        findings=findings_from_keys(keys),
        sources=[f.text for f in files if f.kind in ("html", "js", "map_source")],
        anon_key=anon_key,
    )
