"""Shared utilities for the RLSentry autonomous-development harness.

Design notes
------------
* Every path is resolved lazily through functions (not module constants) so tests can
  point the harness at a temporary repo via the RLSENTRY_ROOT environment variable.
* In the cloud the harness is protected only by hooks. That is enough because tampering is
  *detected*: before every approval the human diffs the frozen paths against their own local
  `harness-frozen` tag, and approvals require the human's SSH signature.
* All state that matters (tickets, approvals, acceptance ledger) lives in files, so a fresh
  Claude Code session can always resume from disk without relying on conversation memory.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def root() -> Path:
    """Main checkout of the project (never a subagent worktree)."""
    for var in ("RLSENTRY_ROOT", "CLAUDE_PROJECT_DIR"):
        if os.environ.get(var):
            return Path(os.environ[var]).resolve()
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode == 0:
        return Path(out.stdout.strip())
    return Path.cwd()


def harness_dir() -> Path:
    return Path(__file__).resolve().parent


def tickets_dir() -> Path:
    return root() / "docs" / "tickets"


def verification_dir() -> Path:
    return root() / "docs" / "verification"


def logs_dir() -> Path:
    d = root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def approvals_dir() -> Path | None:
    """Optional local folder of approvals (tests, or a local devcontainer). None in the cloud."""
    d = os.environ.get("RLSENTRY_APPROVALS")
    return Path(d) if d else None


def approvals_ref() -> str:
    """Git ref holding signed approvals. The human pushes it; agents only read it."""
    return os.environ.get("RLSENTRY_APPROVALS_REF", "origin/rlsentry-approvals")


def allowed_signers() -> Path:
    """Public key(s) allowed to sign approvals; frozen with the harness."""
    return Path(os.environ.get("RLSENTRY_ALLOWED_SIGNERS", harness_dir() / "allowed_signers"))


APPROVAL_NAMESPACE = "rlsentry-approval"
TRAILER = "RLSentry-Accepted"


def holdout_dir() -> Path:
    p = Path(os.environ.get("RLSENTRY_HOLDOUT", ".holdout"))
    return p if p.is_absolute() else root() / p


# ---------------------------------------------------------------------------
# Protected paths (single source of truth, used by guards and provenance checks)
# ---------------------------------------------------------------------------

# Nobody (architect included) may modify these through Claude Code tools.
# In the cloud these are only protected by hooks; the human detects tampering with
# `git diff harness-frozen -- <FROZEN_PATHS>` on their own machine before every approval.
FROZEN_PATHS = ["harness", ".claude", "CLAUDE.md", "Makefile", "docs/SPEC.md", "host", "tests/toy", "cloud"]
HARNESS_PROTECTED = [
    "harness/**", ".claude/settings.json", ".claude/agents/**", "CLAUDE.md",
    "Makefile", "docs/SPEC.md", "logs/**", "host/**", "tests/toy/**", "cloud/**",
]

# Subagents additionally may not touch the architect's artefacts.
SUBAGENT_PROTECTED = [
    ".holdout/**",
    "tests/**", "rlsentry/contracts/**", "docs/**", "CHECKLIST.md",
    "PRODUCTION_LOG.md", "USAGE.md", "BENCHMARK_REPORT.md", "lab/**/expected.yaml",
    "pyproject.toml",
]

# Paths the architect may change directly (outside the subagent ticket flow).
ARCHITECT_PATHS = [
    "rlsentry/contracts/**", "**/__init__.py", "tests/**", "docs/**",
    "lab/**/expected.yaml", "USAGE.md", "PRODUCTION_LOG.md", "BENCHMARK_REPORT.md",
    "CHECKLIST.md", "pyproject.toml", ".gitignore", ".holdout/**",
]

IMPLEMENTERS = {"recon-dev", "probe-dev", "whitebox-dev", "lab-dev"}
REVIEWERS = {"auditor"}


def path_matches(rel: str, patterns: list[str]) -> bool:
    """fnmatch with '**' meaning 'any depth' and bare directories meaning their contents."""
    while rel.startswith("./"):
        rel = rel[2:]
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
        if pat.endswith("/**") and (rel == pat[:-3] or rel.startswith(pat[:-2])):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(Path(rel).name, pat[3:]):
            return True
        if not any(c in pat for c in "*?[") and rel.startswith(pat.rstrip("/") + "/"):
            return True
    return False


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 1)
    meta = yaml.safe_load(parts[0][3:]) or {}
    body = parts[1].lstrip("\n") if len(parts) > 1 else ""
    if body.startswith("-"):  # tolerate '---\n' directly followed by body
        body = body.lstrip("-\n")
    return meta, body


def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{head}\n---\n\n{body.lstrip()}"


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

def log_event(kind: str, **fields: Any) -> None:
    """Append one line to logs/events.jsonl. Never raises: logging must not break a run."""
    try:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **fields}
        with open(logs_dir() / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - logging is best effort by design
        pass


def git(*args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd or root(), capture_output=True, text=True, check=check)
