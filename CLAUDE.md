# RLSentry — shared rules for every agent

RLSentry verifies Supabase authorization from an attacker's point of view. The full spec is
docs/SPEC.md; the development process is SPEC §16. This repository is developed autonomously by
an architect agent and implementer subagents, with one human approving each milestone.

## Hard rules
- Only localhost (the local Supabase lab), package registries and GitHub may be contacted. Never scan, probe
  or fetch any other website, even "just to test". (Taiwan Criminal Code art. 358–362; SPEC §7.)
- Read-only is the default. Writes against a Supabase project only in lab mode, only on localhost.
- Never weaken a test, add skips/xfail/`type: ignore`/`noqa`, or special-case test inputs.
- Never store real user data values; record counts, column names and primary keys only.
- harness/, .claude/, CLAUDE.md, Makefile, docs/SPEC.md, host/, tests/toy/ and logs/ are frozen. Do not try to
  change them: the human compares them against a frozen git tag before every approval.
- Never write to the `rlsentry-approvals` branch; approvals are SSH-signed by the human.

## Layout
- rlsentry/contracts/  types and signatures (architect)
- rlsentry/            implementation (implementers, via tickets)
- tests/               visible tests (architect)      lab/  benchmark scenarios
- docs/tickets/        ticket files                   docs/verification/  milestone checklists
- docs/DECISIONS.md    ADRs                           logs/  harness-written logs (read-only)

## Token rules (every agent)
Most of this project's cost is agents talking to each other and re-reading context. These rules
cut that cost WITHOUT lowering quality. If a rule ever conflicts with correctness, a required
check, or a document the human must review, correctness wins.

1. **One language, no repetition.** Human-facing documents (checklists, ADRs, PRODUCTION_LOG,
   USAGE) are written once, in Traditional Chinese with English technical terms. Never bilingual.
   Agent-to-agent messages are terse bullet points. Never restate what a file already says.
2. **Reference, don't paste.** Point to `path:line-range`, ticket ids, commit shas, and
   logs/events.jsonl event ids. Never paste whole files, diffs or full test output into messages.
3. **Read only what you need.** SPEC: `python3 harness/spec.py "<section>"` or
   `python3 harness/spec.py FR-08`, never the whole file. Grep before Read; Read with a line
   range; do not re-read a file that is already in your context unchanged.
4. **Quiet tools.** `pytest -q`, run only the ticket's tests plus the regression set; on failure
   use the compact summary the harness prints (full output is in logs/).
5. **Edit, don't rewrite.** Change files with targeted edits, not full rewrites.
6. **Never trade checks for tokens.** Tests, holdout, auditor review, acceptance, ADRs and the
   verification checklist keep their full required content.

## Environment
- Docker may not be running in a fresh cloud VM. Before anything that needs the Supabase lab:
  `docker info >/dev/null 2>&1 || (sudo dockerd >/tmp/dockerd.log 2>&1 &); sleep 5; docker info`

## Commands
- `python3 harness/tickets.py status|ready|start|accept|validate|vc-check`
- `make check TESTS="tests/x.py"`  lint + the ticket's tests + full test suite
- `make verify-milestone MS=MS3`   what the human runs at each gate
- `make acceptance`                final delivery check

## Style
Python 3.12, type hints everywhere, ruff-clean, small modules (one responsibility per file),
docstrings on public functions explaining *why*. Pydantic v2 models for data crossing modules.
Human-facing documents (checklists, logs, ADRs, USAGE.md) are written in Traditional Chinese.
