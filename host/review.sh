#!/usr/bin/env bash
# Review one milestone on YOUR machine: sync, tamper check, independent verification, approval.
#
#   bash host/review.sh MS3 <session-branch>        # e.g. claude/rlsentry-ms3-xyz
#
# Steps 1–4 can be run by you or a local Claude Code session (opened in the PARENT folder).
# Step 5 (signing) needs your key passphrase, so only you can complete it.
set -euo pipefail

MS="${1:?usage: review.sh <MS> <session-branch>}"
BRANCH="${2:?usage: review.sh <MS> <session-branch>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY="${RLSENTRY_KEY:-$HOME/.ssh/rlsentry_approval_ed25519}"
FROZEN=(harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud .gitattributes)

pick_python() {
  for c in python3 python "py -3"; do
    if $c -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  return 1
}

step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }
die()  { printf '  ✗ %s\n' "$1" >&2; exit 1; }
cd "$REPO"
PY="$(pick_python)" || die "Python 3.10+ not found"
[[ "${CLAUDE_PROJECT_DIR:-}" == "$REPO" ]] && die "open Claude Code in the PARENT folder, not inside the repo"
git rev-parse -q --verify harness-frozen >/dev/null || die "no local harness-frozen tag; run host/bootstrap.sh first"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || die "working tree has uncommitted changes; commit or stash them first"

step 1 "Sync the session branch"
git fetch -q origin
git switch -q "$BRANCH" 2>/dev/null || git switch -q -c "$BRANCH" --track "origin/$BRANCH"
git pull -q --ff-only origin "$BRANCH"
echo "  at $(git rev-parse --short HEAD) on $BRANCH"

step 2 "Tamper check against YOUR local harness-frozen tag"
if ! git diff --quiet harness-frozen HEAD -- "${FROZEN[@]}"; then
  git diff --stat harness-frozen HEAD -- "${FROZEN[@]}"
  die "frozen files changed in the session branch. Do NOT approve; investigate the diff above."
fi
echo "  ✓ no changes to frozen files"

step 3 "Independent verification"
CHECKLIST="$(ls docs/verification/${MS}-v*.md 2>/dev/null | sort -V | tail -1 || true)"
[[ -n "$CHECKLIST" ]] || die "no docs/verification/${MS}-vN.md on this branch yet"
if command -v make >/dev/null && command -v docker >/dev/null && docker info >/dev/null 2>&1 && command -v supabase >/dev/null; then
  make verify-milestone MS="$MS"
else
  cat <<TXT
  Docker or the Supabase CLI is not available here, so verification cannot run locally.
  Open a NEW session at claude.ai/code on branch $BRANCH (same environment) and send only:

    只執行 make verify-milestone MS=$MS，不要修改任何檔案，回報完整輸出。

  Continue below only after that run ends with ALL PASSED.
TXT
fi

step 4 "Your checklist"
echo "  $CHECKLIST — work through section 3 item by item before approving."
$PY harness/tickets.py status || true

step 5 "Sign your decision (human only)"
if [[ ! -t 0 ]]; then
  cat <<TXT
  Not an interactive terminal, so this step is left for you. In your own terminal run:

    cd "$REPO" && $PY host/approve.py --ms $MS --key "$KEY"

  It asks for your decision, notes and your key passphrase, then pushes the signed approval.
TXT
  exit 0
fi
$PY host/approve.py --ms "$MS" --key "$KEY"
echo
echo "Now send 繼續 in the original cloud session."
