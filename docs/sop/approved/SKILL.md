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

## 3. Report (Traditional Chinese)
1. Two short lines: the approval (reviewer, date, decision, checklist path, sha256 matched) and
   the commit sha you pushed with the three files. Do NOT repeat the approval notes: the next
   session reads them itself at §0.
2. Then the **kickoff prompt for the next milestone** (<NEXT> = the milestone harness status now
   shows as active), as ONE fenced `text` block the human pastes into a fresh session. Build it
   from: docs/PLAN.md's <NEXT> section; the approval notes of <MS> (every numbered item) and of
   earlier milestones that say they still have work for <NEXT>; the deferred items and known
   limits in the <MS> checklist sections 4–5 and PRODUCTION_LOG that name <NEXT>; SPEC §11's
   focus for <NEXT> (`python3 harness/spec.py "Milestone"`). Structure (same as the human's
   own MS6 kickoff prompt):
   - 「繼續 <NEXT>。開始前先做以下檢查，任何一項不符就停下來回報，不要自行變通：」 then the four
     start checks: (1) `git fetch --unshallow origin 2>/dev/null; git fetch origin
     claude/busy-darwin-asvox3 main && git switch claude/busy-darwin-asvox3 && git pull
     --ff-only origin claude/busy-darwin-asvox3`, report `git log -1 --format='%h %s'` and that
     `git rev-parse --is-shallow-repository` is false; (2) `git rev-list --count origin/main
     ^HEAD` must be 0 (ADR-027), never set-head or merge; (3) `pip install -e ".[dev]"`
     succeeds and docker is available (CLAUDE.md; after a forced stop, `supabase stop
     --no-backup` in lab/_shared first); (4) harness status shows current=<NEXT> state=active.
   - 「接著依 §0 讀取：」 the approval notes to read (`git show origin/rlsentry-approvals:<MS>.yaml`
     and any earlier ones with open items), the ADRs that matter for <NEXT>, the <MS> checklist
     sections 4–5, PLAN's <NEXT> row, and the SPEC sections to read via harness/spec.py.
   - 「<NEXT> 第一批 ticket 必須先處理 <MS> 核准意見：」 one bullet per approval-note item
     (restate it briefly; items that are pure acceptance → 「無需動作」).
   - 「<NEXT> 範圍：」 the PLAN items, the deferred items, and the SPEC focus, ending with the
     network rule 「只可連線 localhost、PyPI、GitHub。」
   - The standing efficiency rules: reference run in the lab before dispatch (scratch, not
     committed); merge small architect fixes into one ticket; every implementer ticket says
     「只跑本 ticket 的測試，通過即提交；lab 回歸由 architect 驗收時負責」; the auditor reads code
     only (「不得執行 pytest、bench 或任何會碰 lab 的指令」, ≤ 20 tool calls per part) and no bench
     while it runs; long commands in the background with enough timeout (acceptance ≥ 2 h);
     no working-tree edits during accept; `git add` only listed files, never `commit -a`.
   - The checklist rules (ADR-025/026/030 with addenda): four tags per item; 「Codespaces 準備」
     first; at least one mandatory mutation as a signing precondition; every command its own
     single-line ```bash block, run on the lab with real output, mutation and restore in
     separate blocks, only the local and Actions sha as fill-ins.
   - Closing: ADR-015/031 (system_overview.html, progress.py, verification_steps.html if the
     process changed), auditor with `Base: <MS's last accept commit, 9 chars>`, then
     acceptance, checklist, vc-check, push, stop for review; at the end `/final-question`.
3. Last line: 「下一步：開新 session，貼上上面的 prompt。」
If the SKILL.md under .claude/skills differs from docs/sop (`diff -q`), say so: the human must
copy it again and refreeze.
