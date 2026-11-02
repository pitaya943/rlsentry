#!/usr/bin/env python3
"""Holdout tests live on their own branch (`rlsentry-holdout`), never in the working tree.

Why: Stage 0 showed that committed holdout files are copied into every subagent worktree, so
path-based guards cannot hide them. A separate branch is simply absent from the worktrees,
which branch from main.

  python3 harness/holdout.py add MS2 /tmp/holdout-src   # architect: commit a folder, then delete it
  python3 harness/holdout.py list
  python3 harness/holdout.py materialize MS2 /tmp/out    # used by acceptance.py

`add` uses git plumbing (hash-object / update-index / write-tree / commit-tree) with a private
index file, so it never checks out the branch and never touches the working tree.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

REF = f"refs/heads/{C.HOLDOUT_BRANCH}"


def _git(*args: str, env: dict[str, str] | None = None, input: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=C.root(), capture_output=True, env=env, input=input)


def _ensure_local_ref() -> bool:
    """Make sure the branch exists locally (fetch it in a fresh VM or on the human's machine)."""
    if _git("rev-parse", "--verify", "-q", REF).returncode == 0:
        return True
    if _git("remote").stdout.strip():
        _git("fetch", "-q", "origin", f"{C.HOLDOUT_BRANCH}:{C.HOLDOUT_BRANCH}")
    return _git("rev-parse", "--verify", "-q", REF).returncode == 0


def add(ms: str, src: Path) -> list[tuple[str, str]]:
    files = sorted(p for p in src.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"no files under {src}")
    parent = _git("rev-parse", "--verify", "-q", REF).stdout.decode().strip() if _ensure_local_ref() else ""
    hashes = []
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        if parent:
            _git("read-tree", parent, env=env)
        for f in files:
            rel = f"{ms}/{f.relative_to(src).as_posix()}"
            blob = _git("hash-object", "-w", str(f), env=env).stdout.decode().strip()
            _git("update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}", env=env)
            hashes.append((rel, hashlib.sha256(f.read_bytes()).hexdigest()))
        tree = _git("write-tree", env=env).stdout.decode().strip()
        args = ["commit-tree", tree, "-m", f"holdout {ms}"] + (["-p", parent] if parent else [])
        commit = _git(*args, env=env).stdout.decode().strip()
    _git("update-ref", REF, commit)
    shutil.rmtree(src)  # the source copy must not linger where subagents could read it
    if _git("remote").stdout.strip():
        r = _git("push", "-q", "origin", f"{C.HOLDOUT_BRANCH}:{C.HOLDOUT_BRANCH}")
        if r.returncode != 0:
            C.log_event("holdout_push_failed", error=r.stderr.decode()[-500:])
    C.log_event("holdout_added", milestone=ms, commit=commit, files=dict(hashes))
    return hashes


def materialize(ms: str | None, dest: Path) -> list[Path]:
    """Extract the holdout tests (one milestone, or all) into dest; return dirs that contain tests."""
    if not _ensure_local_ref():
        return []
    args = ["archive", "--format=tar", REF] + ([ms] if ms else [])
    r = _git(*args)
    if r.returncode != 0:
        return []
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        tar.extractall(dest, filter="data")
    return sorted({p.parent for p in dest.rglob("test_*.py")})


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("ms"); a.add_argument("src")
    sub.add_parser("list")
    m = sub.add_parser("materialize"); m.add_argument("ms"); m.add_argument("dest")
    args = ap.parse_args()
    if args.cmd == "add":
        for rel, h in add(args.ms, Path(args.src)):
            print(f"{h}  {rel}")
        print(f"committed to {C.HOLDOUT_BRANCH}; source folder deleted. Record these hashes in PRODUCTION_LOG.md.")
        return 0
    if args.cmd == "list":
        if not _ensure_local_ref():
            print("(no holdout branch yet)")
            return 0
        print(_git("ls-tree", "-r", "--name-only", REF).stdout.decode())
        return 0
    dirs = materialize(None if args.ms == "ALL" else args.ms, Path(args.dest))
    print("\n".join(str(d) for d in dirs) or "(no holdout tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
