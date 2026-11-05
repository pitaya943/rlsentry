"""M1 Recon contracts (SPEC §5 M1; FR-01, FR-02, FR-03; NFR-03). Owned by the architect.

Design: ADR-036 (fetch scope, extraction, classification, masking); D2 (no headless browser):
ADR-037. Implementations live in rlsentry/recon/<file>.py with exactly these names and
signatures and import the constants below instead of redefining them.

    fetch_bundle (fetch.py)      HTML → <script src>/modulepreload → JS → chunk paths in JS,
      uses links.py, sourcemap.py   Next.js _buildManifest, webpack chunk map, source maps
    key_candidates / client_pairs / supabase_hosts (extract.py)   regex + entropy, raw values
    classify_key / key_finding / findings_from_keys (classify.py) JWT decoded without verifying
    recon (run.py)               = all of the above → ReconOutput

Why the heuristics look the way they do: they were measured on real production builds
(tests/recon/fixtures/: Next.js 15 pages router, Vite 8, Create React App 5; SPEC §9 測試層級).
Minified bundles call createClient as `(0,t(8033).UU)("https://…","eyJ…")`, so the URL is found
as a string literal immediately followed by a key literal, not by the name `createClient`.
Vite 8 emits template literals (backticks), so every literal regex accepts ', " and `.
Source maps embed supabase-js's own documentation (`https://xyzcompany.supabase.co`,
"your-publishable-key"), so URLs from built files outrank URLs from map sources.

Safety (NFR-03, CLAUDE.md): the raw value of a key exists only in memory. It is never stored in
a model that reaches the report (KeyFinding keeps `masked`), never in an exception message and
never in a repr. Recon sends only GET requests through the SafeClient it is given, never sends
credentials to the target, and fetches only URLs on the target's own origin (ADR-036 #1).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rlsentry.contracts.models import Finding, KeyFinding, ReconResult
from rlsentry.contracts.safety import SafeClientContract

# --- limits (ADR-036 #2) -------------------------------------------------------------------------

MAX_FILES = 200
"""At most this many HTTP fetches (HTML + JS + source maps) per recon. Further URLs are listed in
`chunks_skipped` with reason "file limit": the scope the report shows stays honest."""

MAX_FILE_BYTES = 10_000_000
"""A response body larger than this is not scanned ("too large"). The Vite fixture's map is
2.2 MB, so real maps fit."""

# --- extraction constants (ADR-036 #3, #4) -------------------------------------------------------

LITERAL_RE = re.compile(r"""(["'`])([^"'`\\\s]{1,2048})\1""")
"""A JS string literal without whitespace or escapes, quoted by ', " or ` (group 1 = quote,
group 2 = content). Used for chunk paths and generic key candidates."""

CHUNK_PATH_RE = re.compile(r"^(?:\./|\.\./|/)?[\w@%+~-][\w@%+~.-]*(?:/[\w@%+~.-]+)*\.m?js$")
"""Literal content that names a JS file by relative or root path. A bare file name without any
"/" (e.g. "react-dom.production.min.js" in an error message) also matches this pattern but is
NOT used (see js_chunk_urls); absolute http(s) URLs are handled separately."""

WEBPACK_CHUNK_URL_RE = re.compile(
    r"""\.u\s*=\s*(?:function\s*\(\s*\w+\s*\)\s*\{\s*return\s*|\(?\s*\w+\s*\)?\s*=>\s*)"""
    r"""(["'])([^"']*)\1\s*\+\s*\w+\s*\+\s*"""
    r"""(?:(["'])\.\3\s*\+\s*\{([^{}]*)\}\s*\[\s*\w+\s*\]\s*\+\s*)?"""
    r"""(["'])([^"']*)\5""")
"""webpack's chunk-URL function `__webpack_require__.u` (minified `X.u=e=>…`). Two forms are
supported (both occur in the fixtures):
  form B (map):  "static/js/"+e+"."+{203:"e04c0c4b",453:"cfd0efe7"}[e]+".chunk.js"   (CRA)
                 group 2 = prefix, group 4 = map body, group 6 = suffix;
  form A (none): "static/chunks/"+e+".de20ce76fac57100.js"                          (Next.js)
                 group 4 is None; chunk ids come from CHUNK_LOAD_RE.
Other shapes (name maps, publicPath expressions) are not reconstructed (ADR-037 limitation)."""

WEBPACK_MAP_ENTRY_RE = re.compile(r"""["']?([\w-]+)["']?\s*:\s*["']([^"']*)["']""")
"""One `id:"hash"` entry inside the form-B map body (group 1 = id, group 2 = hash)."""

CHUNK_LOAD_RE = re.compile(r"\.e\(\s*(\d+)\s*\)")
"""`__webpack_require__.e(43)` (minified `l.e(43)`): a lazily loaded chunk id (form A)."""

SOURCE_MAP_COMMENT_RE = re.compile(r"//[#@]\s*sourceMappingURL=(\S+)")
"""The source-map comment; the LAST match in a file wins (that is where bundlers put it)."""

SOURCE_MAP_HEADERS: tuple[str, ...] = ("sourcemap", "x-sourcemap")
"""Response headers that name a source map (compared case-insensitively); they win over the
comment."""

SUPABASE_HOST_RE = re.compile(r"https://[a-z0-9-]+\.supabase\.(?:co|in)(?![\w.-])")
"""A hosted project URL. The lookahead rejects `https://x.supabase.co.evil.example` and
`*.supabase.co` (no scheme) in supabase-js itself."""

CLIENT_PAIR_RE = re.compile(r"""(["'`])(https?://[^\s"'`]+?)\1\s*,\s*(["'`])([^"'`\s]{20,})\3""")
"""Two adjacent literals "<url>","<key>": the arguments of createClient, also when minified
(group 2 = URL, group 4 = key text). Only pairs whose group 4 fully matches JWT_RE or SB_KEY_RE
count (client_pairs), so supabase-js docs ("your-publishable-key") never qualify."""

KEY_CONTEXT_RE = re.compile(
    r"(?i)(api_?key|anon_?key|supabase_?(?:anon_?|service_?)?key|publishable_?key"
    r"|service_?(?:role_?)?key|secret|token|access_?key|private_?key)")
"""A property or variable name that says "this literal is a key" (generic candidates only).
`supabaseKey` is supabase-js's own parameter name. A bare `key` is NOT a context (React list
keys would flood the report)."""

ASSIGN_TAIL_RE = re.compile(r"""([A-Za-z_$][\w$]*|"[^"]*"|'[^']*')\s*[:=]\s*$""")
"""Matched against the text just before a literal's opening quote: `name:`, `name=`,
`"name":` … (group 1 = the name, with quotes when quoted)."""

ENTROPY_MIN = 4.0
"""Shannon entropy (bits per character) a generic candidate needs. Measured: a phoenix constant
"base64url.bearer.phx." in the Vite map scores 3.52 and must be dropped; the planted 39-char
key scores 4.72. A 20-char string can score at most log2(20) ≈ 4.32."""

GENERIC_MIN_LEN = 24
GENERIC_MAX_LEN = 512
"""Length bounds of a generic candidate (a real API key is at least 24 characters)."""

SB_ENTROPY_MIN = 3.0
"""Entropy the part after `sb_publishable_` / `sb_secret_` needs, so documentation placeholders
such as sb_publishable_xxxxxxxxxxxx are not reported."""

JWT_CLAIMS_KEPT: tuple[str, ...] = ("role", "ref", "exp")
"""The only JWT claims RLSentry keeps (SPEC §5 M1 step 4). `sub`, `email` … are user data and
are dropped (CLAUDE.md: never store real user data)."""

PUBLISHABLE_JWT_ROLES: frozenset[str] = frozenset({"anon"})
SECRET_JWT_ROLES: frozenset[str] = frozenset({"service_role"})
"""FR-03. Any other role (authenticated, supabase_admin, …) is "unverified": shown as a
Configuration warning for a human to judge, never silently dropped (ADR-036 #5)."""

KEY_LABEL_RE = re.compile(r"^(jwt:[a-z_]+|sb_secret|sb_publishable|unverified)$")
"""Allowed KeyFinding.label / key Finding.target values; identical to the ground truth's
KEY_TARGET_RE (ADR-011 #9) so a benchmark key case matches by label."""

KEY_RULES: frozenset[str] = frozenset({"SECRET_KEY_IN_BUNDLE", "UNVERIFIED_KEY"})
"""Rules produced by M1. Their targets are key labels, not database objects, so these findings
never go through whitebox.correlate (ADR-036 #7): a key in the bundle is outside splinter's
scope and must not be counted as `probe_only`."""

CandidateForm = Literal["jwt", "sb_publishable", "sb_secret", "generic"]
KeyKind = Literal["publishable", "secret", "unverified"]
FileKind = Literal["html", "js", "map", "map_source"]


# --- data passed between recon modules (in memory only; never serialized) -----------------------

class FetchedFile(BaseModel):
    """One scanned text. kind "map_source" = one `sourcesContent` entry of a source map; its url
    is "<map url>#<source name>" (or "#<index>" when the name is missing). `text` may contain raw
    keys: repr=False keeps it out of reprs, tracebacks and assertion messages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    kind: FileKind
    text: str = Field(repr=False)


class BundleFetch(BaseModel):
    """fetch_bundle output. `files` in fetch order (target HTML first; each map's sources right
    after the map). `skipped` = "<url> (<reason>)" per URL not scanned, in discovery order."""

    model_config = ConfigDict(extra="forbid")

    files: list[FetchedFile] = []
    skipped: list[str] = []


@dataclass(frozen=True)
class Candidate:
    """A key-like string found by extract.key_candidates. `value` is the RAW key: it must never
    leave memory. repr shows only the masked value."""

    value: str = field(repr=False)
    form: CandidateForm

    def __repr__(self) -> str:
        from rlsentry.safety.mask import mask  # local: contracts must import without safety/
        return f"Candidate(form={self.form!r}, value={mask(self.value)!r})"


@dataclass
class ReconOutput:
    """recon() output. `result` and `findings` go into the report; `sources` (texts for M2 bundle
    inference, FR-05) and `anon_key` (the raw publishable key M2/M3 use when the config gives
    none) stay in memory. repr masks anon_key and omits sources."""

    result: ReconResult
    findings: list[Finding]
    sources: list[str] = field(default_factory=list, repr=False)
    anon_key: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        from rlsentry.safety.mask import mask
        key = mask(self.anon_key) if self.anon_key else None
        return (f"ReconOutput(result={self.result!r}, findings={self.findings!r}, "
                f"sources=<{len(self.sources)} texts>, anon_key={key!r})")


# --- recon/links.py (pure) ------------------------------------------------------------------------

def same_origin(url: str, origin_url: str) -> bool:
    """Contract only; implemented by rlsentry.recon.links.same_origin. Pure.

    True iff both are http(s) URLs with equal scheme, equal lower-cased host and equal
    effective port (missing port = 80 for http, 443 for https). Anything else (other schemes,
    unparsable URLs) → False."""
    raise NotImplementedError


def public_base(url: str) -> str:
    """Contract only; implemented by rlsentry.recon.links.public_base. Pure.

    The base that bare chunk paths ("static/chunks/x.js", "assets/x.js") are relative to:
    "<scheme>://<netloc>" + (the path up to and including the first "/_next/" when the path
    contains "/_next/", else "/"). E.g. http://h/_next/static/b/_buildManifest.js →
    http://h/_next/ ; http://h/assets/index.js → http://h/ (ADR-036 #3: bundlers' public path
    is assumed to be the site root; a non-root base is a documented limitation)."""
    raise NotImplementedError


def html_script_urls(html: str, base_url: str) -> list[str]:
    """Contract only; implemented by rlsentry.recon.links.html_script_urls. Pure (stdlib
    html.parser; FR-01, SPEC §5 M1 step 1).

    In document order, without duplicates: the `src` of every <script> that has one, the `href`
    of every <link> whose rel tokens (whitespace-separated, case-insensitive) include
    "modulepreload", or include "preload" with as="script". Each is resolved with
    urllib.parse.urljoin(base_url, value) and its fragment removed; only http(s) results are
    kept (data:, javascript: … are dropped). Malformed HTML never raises."""
    raise NotImplementedError


def js_chunk_urls(js: str, js_url: str) -> list[str]:
    """Contract only; implemented by rlsentry.recon.links.js_chunk_urls. Pure (SPEC §5 M1
    step 2: Vite imports, Next.js _buildManifest).

    For every LITERAL_RE match in order, content s:
      - s starts with http:// or https:// and its path ends in .js or .mjs → s as is;
      - s matches CHUNK_PATH_RE and starts with "./" or "../" → urljoin(js_url, s);
      - s matches CHUNK_PATH_RE and starts with "/" → urljoin(js_url, s) (root of the origin);
      - s matches CHUNK_PATH_RE, has no leading "./", "../" or "/" but contains "/" →
        urljoin(public_base(js_url), s);
      - anything else (including a bare file name without "/") → ignored.
    Result without duplicates, first occurrence order. No same-origin filtering here (the
    caller does it, so cross-origin references are listed as skipped, not silently lost)."""
    raise NotImplementedError


def webpack_chunk_urls(js_files: list[tuple[str, str]]) -> list[str]:
    """Contract only; implemented by rlsentry.recon.links.webpack_chunk_urls. Pure.

    js_files = (url, text) of every JS file fetched so far. Chunk ids for form A = the distinct
    CHUNK_LOAD_RE ids over ALL texts, ascending numerically. For every WEBPACK_CHUNK_URL_RE match
    in file (url, text), with prefix P = group 2 and suffix S = group 6:
      - form B (group 4 not None): for each WEBPACK_MAP_ENTRY_RE (id, h) in group 4, in order:
        P + id + "." + h + S;
      - form A: for each chunk id: P + id + S;
    each resolved as urljoin(public_base(url), path) when P does not start with "/", else
    urljoin(url, path). Result without duplicates, in that order (files in the given order)."""
    raise NotImplementedError


def source_map_url(js: str, js_url: str, headers: Mapping[str, str]) -> str | None:
    """Contract only; implemented by rlsentry.recon.links.source_map_url. Pure (FR-01).

    The value of the first SOURCE_MAP_HEADERS header present (header names compared
    case-insensitively), else group 1 of the LAST SOURCE_MAP_COMMENT_RE match in js, else None.
    A value starting with "data:" is returned unchanged (inline map, decoded without any
    request); any other value → urljoin(js_url, value). RLSentry never guesses "<url>.map"
    when nothing names a map (ADR-036 #2)."""
    raise NotImplementedError


# --- recon/sourcemap.py (pure) --------------------------------------------------------------------

def decode_data_url(url: str) -> str | None:
    """Contract only; implemented by rlsentry.recon.sourcemap.decode_data_url. Pure.

    "data:<mime>[;charset=…];base64,<b64>" → the base64-decoded bytes as UTF-8 (errors
    replaced); "data:<mime>,<percent-encoded>" → urllib.parse.unquote of the payload. Not a data
    URL or undecodable base64 → None. Never raises."""
    raise NotImplementedError


def map_sources(map_text: str, map_url: str) -> list[FetchedFile]:
    """Contract only; implemented by rlsentry.recon.sourcemap.map_sources. Pure (FR-01).

    Parse map_text as JSON. Not a JSON object → []. For an index map (a "sections" list), the
    result is the concatenation over sections whose "map" is an object, in order. Otherwise,
    for each i where sourcesContent[i] is a str (missing or null entries skipped): FetchedFile(
    url=f"{map_url}#{name}", kind="map_source", text=sourcesContent[i]) where name =
    sources[i] if it is a non-empty str, else str(i). Never raises."""
    raise NotImplementedError


# --- recon/fetch.py (I/O, GET only) ---------------------------------------------------------------

async def fetch_bundle(client: SafeClientContract, target_url: str, *,
                       max_files: int = MAX_FILES,
                       max_bytes: int = MAX_FILE_BYTES) -> BundleFetch:
    """Contract only; implemented by rlsentry.recon.fetch.fetch_bundle. ⚠ network (GET only).

    Every request is `client.request("GET", url)` with NO headers (no apikey, no Authorization,
    no cookies: the frontend host must never receive credentials). Steps:
    1. GET target_url. Transport error (httpx.TransportError) → reason "transport error";
       status ≠ 200 → reason "HTTP <status>" (3xx is not followed); body larger than max_bytes →
       "too large". In those cases return BundleFetch(files=[], skipped=[f"{target_url}
       ({reason})"]). Otherwise files = [FetchedFile(target_url, "html", body)] and the queue =
       html_script_urls(body, target_url).
    2. Process the queue first-in-first-out. Each URL is handled at most once (a URL already
       fetched or skipped is ignored when it reappears). For a URL:
       a. not same_origin(url, target_url) → skipped "cross-origin" (never requested);
       b. fetches already made ≥ max_files → skipped "file limit" (never requested);
       c. GET; transport error / status ≠ 200 / too large → skipped with the reasons of step 1;
       d. a body that, after stripping leading whitespace and lower-casing, starts with
          "<!doctype" or "<html" (an SPA host's fallback page) → skipped "not javascript" for a
          JS URL, "not a source map" for a map URL;
       e. JS: append FetchedFile(url, "js", body); append js_chunk_urls(body, url) to the
          queue; m = source_map_url(body, url, response headers): if m starts with "data:",
          decoded = decode_data_url(m); when not None, append FetchedFile(url + "#inline-map",
          "map", decoded) and then its map_sources(decoded, url + "#inline-map"); else append m
          (when not None) to the queue as a map URL;
       f. map URL (one that reached the queue from step e): append FetchedFile(url, "map",
          body) then map_sources(body, url). Maps are not searched for further URLs.
       The target counts as one fetch; inline maps and map sources do not count.
    3. When the queue is empty: urls = webpack_chunk_urls over all "js" files so far; the ones
       never handled go to the queue (as JS URLs) and step 2 resumes; stop when none is new.
    skipped entries go through mask_text (a URL could carry a token). Requests are sent one at a
    time; the SafeClient's limiter sets the pace (NFR-04). Never raises for HTTP-level
    problems."""
    raise NotImplementedError


# --- recon/extract.py (pure) ----------------------------------------------------------------------

def shannon_entropy(s: str) -> float:
    """Contract only; implemented by rlsentry.recon.extract.shannon_entropy. Pure.

    -Σ p·log2(p) over the character frequencies of s, in bits per character; "" → 0.0."""
    raise NotImplementedError


def supabase_hosts(text: str) -> list[str]:
    """Contract only; implemented by rlsentry.recon.extract.supabase_hosts. Pure (FR-02).

    Every SUPABASE_HOST_RE match, without duplicates, in first-occurrence order."""
    raise NotImplementedError


def client_pairs(text: str) -> list[tuple[str, str]]:
    """Contract only; implemented by rlsentry.recon.extract.client_pairs. Pure (FR-02).

    (url, key) for every CLIENT_PAIR_RE match whose group 4 fully matches JWT_RE or SB_KEY_RE
    (contracts/safety.py), in order, without duplicate pairs; url has trailing "/" removed. The
    key is a RAW value (in memory only)."""
    raise NotImplementedError


def key_candidates(text: str) -> list[Candidate]:
    """Contract only; implemented by rlsentry.recon.extract.key_candidates. Pure (FR-02; SPEC
    §5 M1 steps 3 and 5).

    Collected in three passes, then sorted by start position; a value already collected (same
    value, any form) is not added again:
    1. every JWT_RE match → form "jwt" (no entropy filter: classify decides);
    2. every SB_KEY_RE match → form "sb_secret" or "sb_publishable" by its prefix, kept iff
       shannon_entropy(the part after "sb_secret_" / "sb_publishable_") ≥ SB_ENTROPY_MIN;
    3. generic: every LITERAL_RE match whose content s does not overlap a pass-1/2 match (by
       position), with GENERIC_MIN_LEN ≤ len(s) ≤ GENERIC_MAX_LEN, s not starting with
       "http://" or "https://", s containing at least one ASCII digit and one ASCII letter,
       shannon_entropy(s) ≥ ENTROPY_MIN, AND in key context: ASSIGN_TAIL_RE matches the (up to)
       64 characters before the opening quote and KEY_CONTEXT_RE finds a match in its group 1.
       → form "generic".
    Placeholders ("your-anon-key"), hashes and identifiers outside a key context are not
    candidates; that is what keeps real bundles quiet (fixtures test it)."""
    raise NotImplementedError


# --- recon/classify.py (pure) ---------------------------------------------------------------------

def decode_jwt_claims(token: str) -> dict[str, str | int | None] | None:
    """Contract only; implemented by rlsentry.recon.classify.decode_jwt_claims. Pure (FR-03;
    SPEC §5 M1 step 4: decoded WITHOUT verifying the signature — RLSentry has no key to verify
    with, and the claims are what the server will trust).

    token must have exactly three "."-separated parts; the second is base64url-decoded (padding
    added as needed) and parsed as JSON. Not three parts, bad base64, not UTF-8, not JSON, or
    not a JSON object → None. Otherwise {claim: value} for each claim of JWT_CLAIMS_KEPT that is
    present: str and int (not bool) values kept as is, any other value → None. Claims not in
    JWT_CLAIMS_KEPT are dropped. Never raises."""
    raise NotImplementedError


def classify_key(c: Candidate) -> tuple[KeyKind, str, dict[str, str | int | None] | None]:
    """Contract only; implemented by rlsentry.recon.classify.classify_key. Pure (FR-03;
    ADR-011 #9 labels).

    Returns (kind, label, claims):
      form "jwt": claims = decode_jwt_claims(value); claims None → ("unverified", "unverified",
        None); role (claims.get("role")) in PUBLISHABLE_JWT_ROLES → ("publishable",
        "jwt:<role>", claims); in SECRET_JWT_ROLES → ("secret", "jwt:<role>", claims); a str
        role matching ^[a-z_]+$ → ("unverified", "jwt:<role>", claims); otherwise (no role,
        non-str, other characters) → ("unverified", "unverified", claims);
      form "sb_publishable" → ("publishable", "sb_publishable", None);
      form "sb_secret" → ("secret", "sb_secret", None);
      form "generic" → ("unverified", "unverified", None).
    Every label satisfies KEY_LABEL_RE."""
    raise NotImplementedError


def key_finding(c: Candidate, source_file: str) -> KeyFinding:
    """Contract only; implemented by rlsentry.recon.classify.key_finding. Pure (NFR-03).

    KeyFinding(kind, label, masked=safety.mask.mask(c.value), source_file=source_file,
    jwt_claims=claims) from classify_key(c). The raw value is not kept."""
    raise NotImplementedError


def findings_from_keys(keys: list[KeyFinding]) -> list[Finding]:
    """Contract only; implemented by rlsentry.recon.classify.findings_from_keys. Pure (FR-03).

    One Finding per distinct label among keys whose kind is not "publishable", in the order
    the label first appears: kind "secret" → rule SECRET_KEY_IN_BUNDLE, kind "unverified" →
    UNVERIFIED_KEY; evidence and severity from RULES[rule]; target = label; role = op = None;
    probes = []; correlation = None; id = finding_id(label, None, None, rule). Publishable keys
    (anon, sb_publishable) NEVER produce a finding: they are public by design (FR-03, MS5
    focus)."""
    raise NotImplementedError


# --- recon/run.py (I/O) ---------------------------------------------------------------------------

async def recon(client: SafeClientContract, target_url: str, *, max_files: int = MAX_FILES,
                max_bytes: int = MAX_FILE_BYTES) -> ReconOutput:
    """Contract only; implemented by rlsentry.recon.run.recon (interfaces.Recon). ⚠ network.

    fetched = fetch_bundle(client, target_url, max_files=..., max_bytes=...). Then:
    - keys: for each file in fetched.files order, for each c in key_candidates(file.text):
      key_finding(c, file.url), skipping a (raw value, file url) pair already seen;
    - supabase_url: the first URL among, in this priority order: client_pairs URLs of html/js
      files (file order, then text order); client_pairs URLs of map_source files; supabase_hosts
      of html/js files; supabase_hosts of map_source files. None when there is none;
    - anon_key: the key of the first client pair (same priority order) whose URL equals
      supabase_url and whose key classifies as "publishable"; else the raw value of the first
      candidate (file order) that classifies as "publishable"; else None;
    - result = ReconResult(supabase_url=supabase_url, keys=keys, chunks_scanned=[url of every
      file whose kind is html, js or map, in order], chunks_skipped=fetched.skipped);
    - findings = findings_from_keys(keys);
    - sources = [file.text for every file whose kind is html, js or map_source], in order.
    The report shows the scan scope (chunks_scanned / chunks_skipped): bundles can be split or
    loaded at run time, so the result is never claimed to be complete (SPEC §5 M1 限制)."""
    raise NotImplementedError
