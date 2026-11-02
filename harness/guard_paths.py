#!/usr/bin/env python3
"""PreToolUse guard. Exit code 2 blocks the tool call and shows stderr to the agent.

Usage (from hooks):
  guard_paths.py global              # settings.json: applies to every agent, architect included
  guard_paths.py subagent <name>     # subagent frontmatter: extra rules for implementers/auditor

Threat model (be honest about it):
* Edit/Write/NotebookEdit/Read/Grep/Glob carry explicit paths, so they are checked exactly.
* Bash is free text. The Bash check is a best-effort heuristic that catches the common ways
  of writing to protected files or bypassing the acceptance gate. It is NOT the guarantee.
* The guarantees are: SSH-signed approvals (only the human has the key), the human's
  `git diff harness-frozen` before each approval, the provenance check in
  `make verify-milestone` (which recomputes every gate check from git history), and the human
  running that verification outside the agents' session at every milestone gate.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
READ_TOOLS = {"Read", "Grep", "Glob"}
# Shell fragments that modify files or move code around outside the acceptance gate.
# Commands whose *arguments* may be write targets.
WRITE_CMDS = re.compile(r"^\s*(sudo\s+)?(rm|mv|cp|chmod|chown|truncate|ln|install|dd|touch|"
                        r"sed\s+-i|perl\s+-[pi]|python3?\s+-c|git\s+apply|patch)\b")
REDIRECT = re.compile(r"(?:>>?|\btee(?:\s+-a)?)\s*([^\s;|&<>]+)")
ANY_WRITE = re.compile(r">>?|\btee\b|" + WRITE_CMDS.pattern[4:])
BASH_GIT_BYPASS = re.compile(r"\bgit\s+(merge|cherry-pick|rebase|reset|update-ref|filter-branch|replace|"
                             r"notes|tag|commit\s+.*--no-verify|push\s+.*(--force|-f\b|\+|--delete|"
                             r"rlsentry-approvals))")
BASH_GIT_RESTORE = re.compile(r"\bgit\s+(checkout|restore)\b[^|;&]*\s--\s")


def _repo_rel(path_str: str, cwd: str) -> str:
    """Path relative to the checkout (main or worktree) that contains it."""
    p = Path(path_str)
    if not p.is_absolute():
        p = Path(cwd or ".") / p
    p = p.resolve()
    for parent in [p, *p.parents]:
        if (parent / ".git").exists():
            try:
                return str(p.relative_to(parent))
            except ValueError:
                break
    return str(p)


def _is_holdout(path_str: str, cwd: str = "") -> bool:
    """Any path that names holdout material, in any checkout or as a git ref."""
    if not path_str:
        return False
    if "holdout" in path_str.lower():
        return True
    try:
        return Path(path_str).resolve().is_relative_to(C.holdout_dir().resolve())
    except (OSError, ValueError):
        return False


def _bash_write_target(cmd: str, protected: list[str]) -> str | None:
    """Return a protected path that the command seems to write to.

    Only redirect/tee targets and arguments of known file-modifying commands count, so read-only
    commands such as `python3 harness/tickets.py status > /tmp/s` are not blocked.
    """
    targets = [m.group(1) for m in REDIRECT.finditer(cmd)]
    for segment in re.split(r"&&|\|\||;|\|", cmd):
        if WRITE_CMDS.search(segment):
            targets += re.findall(r"[\w./\-*]+", segment)
    root = str(C.root()) + "/"
    for tok in targets:
        if C.approvals_dir() is not None and tok.startswith(str(C.approvals_dir())):
            return tok
        rel = tok[len(root):] if tok.startswith(root) else tok
        rel = rel[2:] if rel.startswith("./") else rel
        if rel and not rel.startswith("/") and C.path_matches(rel, protected):
            return rel
    return None


def check(event: dict, mode: str, agent: str | None) -> str | None:
    """Return a reason string if the call must be blocked, else None."""
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    cwd = event.get("cwd", "")
    # If the hook payload identifies a subagent, apply subagent rules even from settings.json.
    agent = agent or event.get("agent_type") or event.get("subagent_type")
    # Identity: per-agent frontmatter hooks did not fire in cloud sessions (Stage 0), so the
    # global hook decides. Implementers always work in a linked worktree; the architect never does.
    is_sub = (mode == "subagent" or agent in C.IMPLEMENTERS | C.REVIEWERS
              or C.in_linked_worktree(cwd))

    protected = list(C.HARNESS_PROTECTED)
    if is_sub:
        protected += C.SUBAGENT_PROTECTED

    if tool in WRITE_TOOLS:
        if agent in C.REVIEWERS:
            return "auditor is read-only"
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        if _is_holdout(target, cwd) and is_sub:
            return "holdout tests are off-limits to subagents"
        rel = _repo_rel(target, cwd)
        if C.path_matches(rel, protected):
            return f"{rel} is protected. Only the harness (or the architect, for its own files) may change it."
        if C.approvals_dir() is not None and str(Path(target).resolve()).startswith(str(C.approvals_dir())):
            return "approvals are written by the human on the host only"

    if tool in READ_TOOLS and is_sub:
        for key in ("file_path", "path", "pattern", "glob"):
            if _is_holdout(str(ti.get(key) or ""), cwd):
                return "holdout tests are off-limits to subagents"

    if tool == "Bash":
        cmd = ti.get("command", "")
        if BASH_GIT_BYPASS.search(cmd):
            return ("this git operation is reserved for the harness or the human (merges, history rewrites, "
                    "tags, force pushes, the approvals branch). Use `python3 harness/tickets.py accept <ID> "
                    "--branch <branch>` to merge work.")
        if BASH_GIT_RESTORE.search(cmd) and not is_sub:
            return "copying files between branches bypasses the acceptance gate"
        if is_sub and ("holdout" in cmd.lower() or str(C.holdout_dir()) in cmd):
            return "holdout tests are off-limits to subagents"
        if agent in C.REVIEWERS and ANY_WRITE.search(cmd):
            return "auditor is read-only"
        hit = _bash_write_target(cmd, protected)
        if hit:
            return f"shell command appears to modify protected path {hit}"
    return None


def _save_sample(event: dict) -> None:
    """Keep the first raw payload per (role, tool) so Stage 0 can confirm what hooks receive."""
    try:
        role = "sub" if C.in_linked_worktree(event.get("cwd", "")) else "main"
        d = C.logs_dir() / "raw-hook-samples"
        d.mkdir(exist_ok=True)
        p = d / f"guard-{role}-{event.get('tool_name', 'unknown')}.json"
        if not p.exists():
            p.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "global"
    agent = sys.argv[2] if len(sys.argv) > 2 else None
    raw = sys.stdin.read()
    try:
        event = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return 0
    _save_sample(event)
    reason = check(event, mode, agent)
    if reason:
        C.log_event("guard_block", agent=agent or event.get("agent_type"), tool=event.get("tool_name"),
                    reason=reason)
        print(f"Blocked by RLSentry harness: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
