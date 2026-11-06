---
name: approved
description: After the human has signed a milestone approval, verify it on the approvals branch and immediately regenerate docs/progress.html, docs/branch-log.md and the milestone table in docs/system_overview.html, then commit and push. Use when the human types /approved <MS>.
argument-hint: "<MS>  e.g. MS6"
---

# /approved <MS> — confirm the signed approval, then refresh the progress documents

Target milestone: `$ARGUMENTS`. If empty, use the milestone that `python3 harness/tickets.py
status` shows as most recently approved; if that is ambiguous, ask.

Never write to `rlsentry-approvals`, never sign, never start the next milestone here (that needs
the human's 「繼續」 in a fresh session, prompt §0).

## 1. Verify (stop at the first failure; report it; change nothing)
1. `git fetch -q origin rlsentry-approvals claude/busy-darwin-asvox3` (retry network errors up
   to 4 times: 2/4/8/16 s).
2. `git show origin/rlsentry-approvals:<MS>.yaml` must exist and contain `decision: approve`.
   `changes_requested` → report the notes and stop (prompt §6 handles that, not this skill).
3. `git show origin/rlsentry-approvals:<MS>.yaml.sig` must exist (the harness verifies the
   signature itself; you only check that it is there).
4. The `checklist:` path in the YAML must exist, and `sha256sum <path>` must equal
   `checklist_sha256:`. A mismatch means the signed checklist is not the one in the repo: stop.
5. `python3 harness/tickets.py status` must no longer show <MS> as `awaiting_human`
   (expected: <MS> approved, the next milestone `active`).

## 2. Refresh (only if every check passed)
1. `python3 docs/tools/progress.py`
2. `docs/system_overview.html`, section 7 table: set the <MS> row's status to 已核准
   (`<i class="dot" style="background:var(--done)"></i>已核准`). Targeted edit, nothing else.
3. Commit ONLY these files (never `commit -a`):
   `git add docs/progress.html docs/branch-log.md docs/system_overview.html`, message
   `docs: <MS> approved — progress refreshed (ADR-048)` plus the session's attribution lines.
4. `git push -u origin HEAD` (retry network errors up to 4 times).

## 3. Report (Traditional Chinese, short)
- the approval: reviewer, date, decision, checklist path, and that the sha256 matched;
- the commit sha you pushed and the three files;
- the approval notes, copied verbatim, as the to-do list for the next session;
- 「下一步：開新 session 並輸入『繼續』」.
