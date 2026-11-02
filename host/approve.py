#!/usr/bin/env python3
"""Approve or reject a milestone. Run this on YOUR machine, never inside the agents' environment.

What it does
1. Refuses to continue if any frozen harness file differs from your local `harness-frozen` tag
   (the agents could have edited the harness in the cloud; git itself is the trusted judge).
2. Finds the latest checklist docs/verification/<MS>-vN.md on the branch you checked out.
3. Writes <MS>.yaml (bound to the checklist's sha256), signs it with your SSH key
   (`ssh-keygen -Y sign`), commits both to the `rlsentry-approvals` branch and pushes it.
The private key never leaves your machine, so no agent can produce a valid approval.

Usage:
  git fetch && git switch <the session's branch> && git pull
  git diff --stat harness-frozen -- harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud .gitattributes
  python3 host/approve.py --ms MS3 --key ~/.ssh/id_ed25519
Only the Python standard library, git and ssh-keygen are needed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FROZEN_PATHS = ["harness", ".claude", "CLAUDE.md", "Makefile", "docs/SPEC.md", "host", "tests/toy", "cloud", ".gitattributes"]
BRANCH = "rlsentry-approvals"
NAMESPACE = "rlsentry-approval"


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def latest_checklist(repo: Path, ms: str) -> tuple[int, Path] | None:
    best = None
    for p in (repo / "docs" / "verification").glob(f"{ms}-v*.md"):
        m = re.fullmatch(rf"{re.escape(ms)}-v(\d+)\.md", p.name)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), p)
    return best


def yaml_block(text: str) -> str:
    return "|\n" + "".join(f"  {line}\n" for line in (text or "").splitlines() or [""])


def open_approvals_worktree(repo: Path, tmp: Path, remote: bool) -> Path:
    wt = tmp / "approvals"
    if remote:
        git("fetch", "-q", "origin", BRANCH, cwd=repo, check=False)
    has_remote = remote and git("rev-parse", "--verify", "-q", f"origin/{BRANCH}", cwd=repo, check=False).returncode == 0
    has_local = git("rev-parse", "--verify", "-q", BRANCH, cwd=repo, check=False).returncode == 0
    if has_remote:
        git("worktree", "add", "-q", "-B", BRANCH, str(wt), f"origin/{BRANCH}", cwd=repo)
    elif has_local:
        git("worktree", "add", "-q", str(wt), BRANCH, cwd=repo)
    else:  # first approval ever: create an orphan branch with no project files
        git("worktree", "add", "-q", "--detach", str(wt), cwd=repo)
        git("checkout", "-q", "--orphan", BRANCH, cwd=wt)
        git("rm", "-rq", "--cached", ".", cwd=wt, check=False)
        for child in wt.iterdir():   # portable cleanup (no `rm` on plain Windows)
            if child.name == ".git":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    return wt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ms", required=True)
    ap.add_argument("--key", required=True, help="private SSH key used for signing, e.g. ~/.ssh/id_ed25519")
    ap.add_argument("--frozen-ref", default="harness-frozen")
    ap.add_argument("--decision", choices=["approve", "changes_requested"])
    ap.add_argument("--reviewer")
    ap.add_argument("--notes")
    ap.add_argument("--yes", action="store_true", help="confirm you ran verify-milestone yourself")
    ap.add_argument("--no-push", action="store_true", help="commit locally only (tests, offline)")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()

    # 1. Tamper check against the human's own frozen tag.
    if git("rev-parse", "--verify", "-q", a.frozen_ref, cwd=repo, check=False).returncode != 0:
        print(f"Tag {a.frozen_ref!r} not found. Create it once on the frozen harness commit: "
              f"git tag {a.frozen_ref} <commit>")
        return 1
    diff = git("diff", "--name-only", a.frozen_ref, "HEAD", "--", *FROZEN_PATHS, cwd=repo, check=False).stdout
    if diff.strip():
        print("REFUSING: frozen harness files changed since", a.frozen_ref, "\n" + diff)
        return 1

    # 2. Checklist and its hash.
    found = latest_checklist(repo, a.ms)
    if not found:
        print(f"No checklist docs/verification/{a.ms}-vN.md on this branch.")
        return 1
    version, path = found
    # Hash the committed blob, not the working-tree file: on Windows the working copy may have
    # CRLF line endings, while the cloud harness hashes the LF content stored in git.
    rel = path.relative_to(repo).as_posix()
    blob = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=repo, capture_output=True, check=False)
    if blob.returncode != 0:
        print(f"{rel} is not committed on this branch; pull the session branch first.")
        return 1
    digest = hashlib.sha256(blob.stdout).hexdigest()
    print(f"Reviewing {path.relative_to(repo)} (v{version}) sha256 {digest}")
    if not a.yes and input(f"Did you run `make verify-milestone MS={a.ms}` yourself and see ALL PASSED? [y/N] "
                           ).strip().lower() != "y":
        print("Run it first; it is the independent check behind every approval.")
        return 1
    decision = a.decision or ("approve" if input("Approve? [y = approve / n = request changes] ")
                              .strip().lower() == "y" else "changes_requested")
    reviewer = a.reviewer or input("Reviewer name: ").strip()
    notes = a.notes
    if notes is None:
        print("Notes (end with an empty line):")
        lines = []
        while (line := input()) != "":
            lines.append(line)
        notes = "\n".join(lines)
    record = (f"milestone: {a.ms}\nchecklist: {path.relative_to(repo)}\nchecklist_sha256: {digest}\n"
              f"decision: {decision}\nreviewer: {reviewer}\ndate: {time.strftime('%Y-%m-%d %H:%M')}\n"
              f"notes: {yaml_block(notes)}")

    # 3. Sign and commit to the approvals branch.
    remote = not a.no_push and bool(git("remote", cwd=repo, check=False).stdout.strip())
    with tempfile.TemporaryDirectory() as tmp:
        wt = open_approvals_worktree(repo, Path(tmp), remote)
        try:
            y = wt / f"{a.ms}.yaml"
            y.write_text(record)
            sig = wt / f"{a.ms}.yaml.sig"
            sig.unlink(missing_ok=True)
            subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(Path(a.key).expanduser()), "-n", NAMESPACE,
                            str(y)], check=True, capture_output=True)
            hist = wt / "history"
            hist.mkdir(exist_ok=True)
            (hist / f"{a.ms}-v{version}-{time.strftime('%Y%m%d%H%M%S')}.yaml").write_text(record)
            git("add", "-A", cwd=wt)
            git("commit", "-q", "-m", f"{a.ms} v{version}: {decision}", cwd=wt)
            if remote:
                git("push", "-q", "origin", f"HEAD:{BRANCH}", cwd=wt)
        finally:
            git("worktree", "remove", "--force", str(wt), cwd=repo, check=False)
    print(f"{a.ms}: {decision} signed and {'pushed to' if remote else 'committed on'} {BRANCH}.")
    print("Then tell the cloud session to continue (e.g. send: 繼續).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
