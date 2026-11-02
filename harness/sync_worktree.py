#!/usr/bin/env python3
"""Bring a subagent's worktree to the architect's current commit before it starts work.

Why: Claude Code creates subagent worktrees from the repository's DEFAULT branch, but in a cloud
session the architect works on its own session branch. Without this step a subagent would not
see the contracts, tests and tickets the architect committed for the current milestone.

Run as the first command of every ticket:  python3 harness/sync_worktree.py
Only works inside a linked worktree with no local changes; never touches the main checkout.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def main() -> int:
    here = Path.cwd()
    r = git("rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir", cwd=here)
    if r.returncode != 0:
        print("not inside a git checkout", file=sys.stderr)
        return 1
    git_dir, common = (Path(p).resolve() for p in r.stdout.split())
    if git_dir == common:
        print("this is the main checkout, not a subagent worktree: nothing to do")
        return 0
    main_checkout = common.parent                                # non-bare repo: <main>/.git
    target = git("rev-parse", "HEAD", cwd=main_checkout).stdout.strip()
    if git("status", "--porcelain", "--untracked-files=no", cwd=here).stdout.strip():
        print("worktree has uncommitted changes; refusing to move it", file=sys.stderr)
        return 1
    own = git("rev-list", "--count", f"{target}..HEAD", cwd=here).stdout.strip()
    if own not in ("", "0") and git("merge-base", "--is-ancestor", "HEAD", target, cwd=here).returncode != 0:
        print(f"worktree already has {own} commit(s) of its own; refusing to discard them", file=sys.stderr)
        return 1
    res = git("reset", "-q", "--hard", target, cwd=here)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return 1
    print(f"worktree synced to architect HEAD {target[:9]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
