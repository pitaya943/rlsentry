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

## Commands
- `python3 harness/tickets.py status|ready|start|accept|validate|vc-check`
- `make check TESTS="tests/x.py"`  lint + the ticket's tests + full test suite
- `make verify-milestone MS=MS3`   what the human runs at each gate
- `make acceptance`                final delivery check

## Style
Python 3.12, type hints everywhere, ruff-clean, small modules (one responsibility per file),
docstrings on public functions explaining *why*. Pydantic v2 models for data crossing modules.
Human-facing documents (checklists, logs, ADRs, USAGE.md) are written in Traditional Chinese.
