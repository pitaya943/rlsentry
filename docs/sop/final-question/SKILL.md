---
name: final-question
description: Milestone close-out. List every decision the human still has to make for the milestone awaiting review (or say there is none), then turn the human's answers into approval notes in the standard format for host/approve.py. Use when the human types /final-question.
---

# /final-question — pending decisions → approval notes

Read-only until the human answers. Never write to the `rlsentry-approvals` branch and never sign:
only the human signs (host/approve.py).

## 1. Find the milestone
- `python3 harness/tickets.py status` → the milestone in state `awaiting_human` (or
  `changes_requested`). If there is none, say so in one line and stop.
- `ls docs/verification/<MS>-v*.md` → the highest N is the checklist under review.

## 2. Collect what is still undecided (read only these)
- The checklist: section 4 items marked 「需要你決定」, and section 3 items tagged 【本機】 that ask
  for a decision.
- `docs/DECISIONS.md`: ADRs of this milestone that say 交人類決定 / 交人工判斷 / 待人類確認.
- `PRODUCTION_LOG.md` (this milestone's section): anything marked 待人類確認 / 待確認.
- Questions you asked the human in this conversation that are still unanswered.
Deduplicate. Do not invent questions to look thorough.

## 3. Ask (Traditional Chinese, following the user's chat preferences)
- None found → reply exactly 「沒有待決事項。」 plus the checklist path, then stop.
- Otherwise a numbered list. Each item: one-line background with its source (`file:line` or
  ADR id), the options (A/B/…), your recommendation and why, and what breaks with each option.
  Ask the human to answer per number, then wait.

## 4. After the human answers: write the approval notes
Output ONE fenced `text` block the human pastes at host/approve.py's 「Notes」 prompt. That
prompt ends at the first empty line, so the block must not contain empty lines:

```text
<MS> 核准。以下意見請在下一個 session 開始時處理，並套用到之後每一個 milestone。
  1. <decision 1: what was chosen, as an instruction to the architect; cite the ADR / checklist item>
  2. <decision 2 …>
  N. <anything the human added>
```

Rules: one line per decision; imperative and testable where possible (「以測試證明…」); keep the
human's own wording for anything they wrote; include every answered item, including "accept as
is" (「接受…（ADR-0xx）」). If the human chose changes instead of approval, start with
「<MS> 要求修改。」 and tell them to answer `n` at the Approve prompt.

Then print the exact local command (fill in <MS>; the key path is the human's own):

```bash
python3 host/approve.py --ms <MS> --key ~/.ssh/rlsentry_approval_ed25519
```

Remind: run it only after `make verify-milestone MS=<MS>` (or the Actions run) shows ALL PASSED
and the 簽章前提 mutations are done; after signing, type `/approved <MS>` in the cloud session.
