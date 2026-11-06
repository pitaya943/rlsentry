"""Pipeline, S4 endpoint confirmation and CLI contracts (SPEC §4, §2 profiles; FR-13, FR-15,
FR-16; NFR-01..04). Owned by the architect.

Implementations: rlsentry/safety/endpoint.py (normalize_api_url, resolve_endpoint),
rlsentry/pipeline.py (stricter_profile, modules_for, run_scan, run_init), rlsentry/cli.py (CLI).
Decisions: ADR-020 #6 (one SafeClient, built only in pipeline.py, only after authorize),
ADR-036 #7 (M1 findings never go through correlate), ADR-042 (pipeline order, profiles and
modules, seeding and escalation), ADR-043 (S4: the Supabase URL must be named by the user).

Why S4 matters: `ReconOutput.supabase_url` and `anon_key` come from the target's JavaScript,
i.e. from whoever controls the bundle. Sending the test users' passwords (login) and every probe
to that URL without the user naming it would let a malicious or compromised bundle redirect the
scan to a host the user never authorised (CLAUDE.md, SPEC §7).
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from rlsentry.contracts.models import Profile, ScanReport
from rlsentry.contracts.policy import ScanConfig


class EndpointRefused(PermissionError):
    """ADR-043: the Supabase API URL is not named by the config or the CLI flag, the two
    disagree, or a URL is malformed. Raised before any request is sent to an API host. The
    message never contains a query string, userinfo or key (URLs go through recon.report_url)."""


class ScanSetupError(ValueError):
    """A required input is missing before any request is sent (no anon key for a profile that
    does not run M1, a password env var named by the config is unreadable, …). The message names
    the setting, never a value."""


PROFILE_STRICTNESS: dict[Profile, int] = {Profile.DEV: 0, Profile.CI: 1, Profile.AUDIT: 2}
"""ADR-014 #4: the effective profile is the stricter of config.profile and the CLI profile."""

MODULES_BY_PROFILE: dict[Profile, tuple[str, ...]] = {
    Profile.DEV: ("M1", "M2", "M3", "M4", "M5"),
    Profile.CI: ("M2", "M3", "M4", "M5"),
    Profile.AUDIT: ("M1", "M2", "M3", "M4", "M5"),
}
"""SPEC §2 profile table, with ADR-042 #2: M4 is optional in every profile and runs only when
config.db_url_env names a set, non-empty variable (it is read-only, ADR-032 #2, so audit may run
it; ADR-033 補記). ci skips M1: a CI job scans a preview database, not a deployed frontend."""

M4_SKIPPED_NOTE = "M4 skipped: no database URL (db_url_env not set or empty)"
M1_SKIPPED_NOTE = "M1 skipped: the ci profile does not scan the frontend bundle (SPEC §2)"
WRITES_AUDIT_NOTE = "audit profile: no write, seed or escalation request was sent (NFR-01)"
CONFIRMER_ENV = ("RLSENTRY_CONFIRMED_BY", "USER", "USERNAME")
"""Environment variables tried, in order, for AuthorizationRecord.confirmed_by when the caller
gives none; "unknown" if all are unset (NFR-02 records who confirmed)."""


# --- safety/endpoint.py (S4; ADR-043) ---------------------------------------------------------

def normalize_api_url(url: str) -> str:
    """Contract only; implemented by rlsentry.safety.endpoint.normalize_api_url. Pure.

    Canonical form of a Supabase API base URL, used for every comparison: urllib.parse.urlsplit;
    scheme must be http or https; a hostname is required; no userinfo (user or password), no
    query, no fragment; the path must be "" or "/". Result = "<scheme>://<host>[:<port>]" with
    scheme and host lower-cased and the port omitted when it is the scheme default (80/443) or
    absent. Anything else raises EndpointRefused whose message is "invalid Supabase URL " +
    recon.report_url(url) + ": <reason>".
    """
    raise NotImplementedError


def resolve_endpoint(config: ScanConfig, cli_supabase_url: str | None,
                     recon_url: str | None) -> tuple[str, str]:
    """Contract only; implemented by rlsentry.safety.endpoint.resolve_endpoint. Pure.

    Returns (normalized URL, method) where method is "config" or "cli_flag"; it is recorded in
    AuthorizationRecord.supabase_url / supabase_url_method. Rules, first match wins:
    1. config.supabase_url and cli_supabase_url both set and their normalized forms differ →
       EndpointRefused("--supabase-url and supabase_url in the config disagree").
    2. config.supabase_url set → (normalize_api_url(config.supabase_url), "config").
    3. cli_supabase_url set → (normalize_api_url(cli_supabase_url), "cli_flag").
    4. otherwise EndpointRefused. When recon_url is not None the message names it as
       recon.report_url(recon_url) and says how to confirm it: "the frontend bundle points at
       <url>; to scan it, add `supabase_url: <url>` to the config or pass --supabase-url <url>".
       When recon_url is None: "no Supabase URL: set supabase_url in the config or pass
       --supabase-url".
    recon_url never becomes the endpoint by itself, even when it equals the target's origin
    (MS5 approval note 6). A recon_url that differs from the chosen endpoint is not an error
    (the caller adds a report note).
    """
    raise NotImplementedError


# --- pipeline.py ------------------------------------------------------------------------------

def stricter_profile(config_profile: Profile, cli_profile: Profile | None) -> Profile:
    """Contract only; implemented by rlsentry.pipeline.stricter_profile. Pure.

    cli_profile None → config_profile; else the one with the higher PROFILE_STRICTNESS.
    """
    raise NotImplementedError


def modules_for(profile: Profile, db_url: str | None) -> list[str]:
    """Contract only; implemented by rlsentry.pipeline.modules_for. Pure.

    MODULES_BY_PROFILE[profile] in order, without "M4" when db_url is None or empty.
    """
    raise NotImplementedError


async def run_scan(config: ScanConfig, *, cli_confirmed: bool = False,
                   cli_profile: Profile | None = None, cli_supabase_url: str | None = None,
                   confirmed_by: str | None = None, env: Mapping[str, str] | None = None,
                   transport: Any = None, now: datetime | None = None) -> ScanReport:
    """Contract only; implemented by rlsentry.pipeline.run_scan (interfaces.RunScan; FR-16).

    The single entry point shared by the CLI, the Python API and the GitHub Action. `env`
    defaults to os.environ (tests pass a dict); `transport` is for tests only (httpx
    MockTransport / a recording transport) and is passed to the SafeClient. Steps, in order;
    nothing is sent before step 4:
    1. profile = stricter_profile(config.profile, cli_profile). confirmed_by = the argument, else
       the first non-empty env value among CONFIRMER_ENV, else "unknown".
       record = safety.gate.authorize(config, cli_confirmed=cli_confirmed,
       confirmed_by=confirmed_by, profile=profile, now=now). AuthorizationRefused propagates.
    2. db_url = env.get(config.db_url_env) if config.db_url_env else None (empty → None);
       modules = modules_for(profile, db_url).
    3. Checks that need no network, in this order (each raises before any request):
       - "M1" not in modules (ci) → resolve_endpoint(config, cli_supabase_url, None) now
         (EndpointRefused propagates);
       - config.anon_key_env set and env value missing/empty → ScanSetupError naming the
         variable; "M1" not in modules and config.anon_key_env unset → ScanSetupError("ci needs
         anon_key_env: the anon key is not taken from a bundle in ci").
    4. Exactly ONE SafeClient(profile=profile, limiter=RateLimiter(rps=config.rate_limit_rps,
       concurrency=4), write_hosts=record.write_hosts, transport=transport) for the whole run
       (ADR-020 #6); closed at the end (async with), also on error.
    5. M1 (if in modules): rec = recon(client, config.target) — same-origin GETs to the
       authorised target only. Then url, method = resolve_endpoint(config, cli_supabase_url,
       rec.result.supabase_url) — EndpointRefused propagates, so a bundle pointing at an
       unconfirmed host gets ZERO requests (MS5 approval note 6). If rec.result.supabase_url is
       not None and normalize_api_url(it) != url (or it does not normalize), add the note
       "the frontend bundle points at <report_url(it)>, not the confirmed Supabase URL".
       record = record.model_copy(update={"supabase_url": url, "supabase_url_method": method}).
       anon_key = env[config.anon_key_env] if set, else rec.anon_key; None → ScanSetupError
       ("no anon key: set anon_key_env or make sure the bundle contains the anon key"), raised
       before any API request.
    6. M2: found = discover(client, url, anon_key, config.policy, rec.sources if M1 else []).
    7. M3: sessions = build_sessions(client, url, anon_key, config.test_users, env).
       dev/ci only: seeded, seed_notes = seed_reads(...) (probe/seed_pass.py).
       matrix, m3 = probe(client, url, anon_key, found.targets, sessions, config.policy, profile).
       dev/ci only: esc, esc_notes = escalation_pass(..., config.test_users, env, matrix);
       m3 += esc; m3 += cleanup_reads(... seeded ...). audit: none of these three is called
       and the note WRITES_AUDIT_NOTE is added.
       When any matrix cell's reason starts with probe.WRITE_REFUSED_REASON, add one note
       "<n> write cells inconclusive: writes to <host> refused by the safety gate (ADR-041)".
    8. M4 (if in modules): lints = run_splinter(db_url, config.db_schemas);
       m3 = correlate(m3, lints, config.db_schemas); policies = read_policies(db_url,
       config.db_schemas). Any exception in M4 → note "M4 failed: <exception class name>"
       (never the message: it may contain the DB URL) and the scan continues without M4
       results (M4 is optional); "M4" is then removed from modules. Without M4, note
       M4_SKIPPED_NOTE.
    9. findings = m3 + (rec.findings if M1 else []) — M1 key findings are appended AFTER
       correlate and never pass through it (ADR-036 #7).
       report = ScanReport(tool_version=TOOL_VERSION, target=config.target, profile=profile,
       authorization=record, started_at, finished_at (UTC), recon=rec.result if M1 else None,
       discovery=found, matrix=matrix, findings=findings, policies=policies, modules=modules,
       notes=notes, timings={"M1","M2","M3","M4": seconds, only for modules that ran}).
       M5: return report.enrich(report, config) (adds title, repro, fix_sql, references, sorts).
    Test seams (tests monkeypatch these names on the rlsentry.pipeline module, so import them
    there by name and call them through the module globals): SafeClient, RateLimiter, recon,
    discover, build_sessions, probe, seed_reads, cleanup_reads, escalation_pass, run_splinter,
    read_policies, correlate, enrich, resolve_endpoint, authorize.
    WriteRefused is never expected to escape (probe and the dev/ci passes convert it); if it
    does, it propagates (fail closed). Sends no request in audit other than GET/HEAD and the
    login POST (NFR-01; the SafeClient gate enforces it again).
    """
    raise NotImplementedError


async def run_init(config: ScanConfig, *, cli_confirmed: bool = False,
                   cli_supabase_url: str | None = None, confirmed_by: str | None = None,
                   env: Mapping[str, str] | None = None, transport: Any = None) -> str:
    """Contract only; implemented by rlsentry.pipeline.run_init (FR-15 `rlsentry init`).

    Same steps 1 and 4 as run_scan with profile AUDIT (init never writes): authorize, then
    url, _ = resolve_endpoint(config, cli_supabase_url, None) (no M1: the URL must be named);
    anon key from env[config.anon_key_env] (unset/empty → ScanSetupError); one SafeClient;
    found = discover(client, url, anon_key, config.policy, []); return
    "target: <config.target>\\n" + draft_policy(found.targets). Only GET requests are sent.
    """
    raise NotImplementedError


# --- cli.py (Typer; FR-13, FR-15, FR-16) --------------------------------------------------------
#
# `rlsentry scan [TARGET] [options]` and `rlsentry init [options]`; entry point
# `rlsentry = "rlsentry.cli:main"` (pyproject). The module exposes `app` (the typer.Typer with the
# two commands) and main() (runs app). Test seams: cli imports run_scan, run_init (from
# rlsentry.pipeline), load_config, render_json, render_html, render_sarif, exit_code by name and
# calls them through its module globals, so tests can monkeypatch rlsentry.cli.<name>.
# The config file is read as UTF-8 text and parsed with load_config.
#
# scan options:
#   --config/-c PATH        default "rlsentry.yaml"; when the file does not exist and TARGET is
#                           given, the config is ScanConfig(target=TARGET) (all defaults);
#                           a missing file without TARGET → exit EXIT_USAGE.
#   TARGET                  optional; when the file sets a different target → exit EXIT_USAGE
#                           ("TARGET and config target differ"), never silently replaced.
#   --profile {dev,ci,audit} cli_profile (stricter one wins).
#   --i-own-this-target     cli_confirmed (NFR-02).
#   --supabase-url URL      cli_supabase_url (S4, ADR-043).
#   --out DIR               default "rlsentry-report"; created if missing.
#   --format LIST           comma list of json,html,sarif; default by effective profile:
#                           DEFAULT_FORMATS (dev html; ci json,sarif; audit html,json).
#   Files written: <out>/rlsentry-report.json | .html | .sarif (REPORT_FILE_STEM).
#   Terminal: one summary line per evidence level with counts per severity, then each finding
#   at Confirmed level as "<SEVERITY> <rule> <target> <role> <op>", then the written paths.
#   Never prints a key, password or DB URL; everything printed passes through mask_text.
#   Exit code: report.exit_code(report, config.fail_on); ConfigError/ScanSetupError/
#   EndpointRefused/AuthorizationRefused/WriteRefused → message on stderr (mask_text) and
#   EXIT_USAGE for ConfigError/ScanSetupError, EXIT_REFUSED for the three refusals.
# init options: --config/-c, --i-own-this-target, --supabase-url, --out FILE (default
#   "rlsentry.draft.yaml"; refuses to overwrite an existing file → EXIT_USAGE).
#   Writes run_init's text; exit EXIT_OK.
# Passwords and keys come from the environment variables the config names; the CLI never
# accepts a password or key as an argument (it would land in shell history and CI logs).
