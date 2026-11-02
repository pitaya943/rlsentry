#!/usr/bin/env python3
"""PreToolUse hook for the Agent tool: only ticketed, unlocked work may be dispatched.

Rules
* Implementers need a first line `Ticket: T-xxx` in the prompt, and the ticket must be
  in_progress, owned by that agent, and in the currently unlocked milestone.
* The auditor needs a line `Review: <milestone>`; it is read-only, so it is always allowed.
* Any other subagent type (general-purpose, Explore, Plan, ...) is refused, because it could
  do implementation work outside the ticket flow.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import tickets as T  # noqa: E402


def check(event: dict) -> str | None:
    ti = event.get("tool_input") or {}
    agent = ti.get("subagent_type") or ""
    prompt = ti.get("prompt") or ti.get("description") or ""
    if agent in C.REVIEWERS:
        return None if re.search(r"^Review:\s*\S+", prompt, flags=re.M) else \
            "auditor dispatches must contain a line `Review: <milestone>`"
    if agent not in C.IMPLEMENTERS:
        return f"subagent type {agent!r} is not allowed; dispatch one of {sorted(C.IMPLEMENTERS | C.REVIEWERS)}"
    m = re.search(r"^Ticket:\s*(T-[\w.-]+)", prompt, flags=re.M)
    if not m:
        return "implementer dispatches must start with a line `Ticket: T-xxx`"
    ok, msg = T.dispatch_check(m.group(1), agent)
    return None if ok else msg


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    reason = check(event)
    if reason:
        C.log_event("dispatch_blocked", reason=reason,
                    agent=(event.get("tool_input") or {}).get("subagent_type"))
        print(f"Blocked by RLSentry harness: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
