#!/usr/bin/env python3
"""Stop hook for the architect session.

Allowed to stop (exit 0):
  * every milestone approved and `acceptance.py --final` passes        -> delivered
  * the current milestone is awaiting_human (checklist produced)       -> pause for the human
  * the stop-attempt budget is exhausted                               -> writes logs/INCOMPLETE.md
Otherwise exit 2 with concrete next steps, which Claude Code feeds back to the architect.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import tickets as T  # noqa: E402

MAX_BLOCKED_STOPS = 30


def _counter() -> Path:
    return C.logs_dir() / "stop_attempts.json"


def _bump() -> int:
    p = _counter()
    n = json.loads(p.read_text())["count"] if p.exists() else 0
    p.write_text(json.dumps({"count": n + 1}))
    return n + 1


def next_steps(st: dict) -> list[str]:
    ms, state = st["current_milestone"], st["state"]
    steps = [f"Milestone {ms} is {state}."]
    if st["validation_errors"]:
        steps.append("Fix ticket validation errors: " + "; ".join(st["validation_errors"][:5]))
    if state == "changes_requested":
        steps.append(f"Read the notes in the approval file for {ms}, turn each into a ticket "
                     "(origin: human-review), then run them.")
    if st["ready"]:
        steps.append("Start and dispatch ready tickets: " + ", ".join(st["ready"]))
    if st["in_progress"]:
        steps.append("Collect results and run `accept` for in-progress tickets: " + ", ".join(st["in_progress"]))
    if not st["ready"] and not st["in_progress"] and st["vc_problems"]:
        steps.append("Produce/repair the verification checklist: " + "; ".join(st["vc_problems"]))
    steps.append("Run `python3 harness/tickets.py status` to see the full state.")
    return steps


def main() -> int:
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass
    st = T.status()
    T.render()
    if st["current_milestone"] is None:
        res = subprocess.run([sys.executable, str(C.harness_dir() / "acceptance.py"), "--final"],
                             cwd=C.root(), capture_output=True, text=True)
        if res.returncode == 0:
            C.log_event("stop_allowed", reason="delivered")
            T.sync_state("delivered")
            return 0
        st = {**st, "state": "final acceptance failing", "vc_problems": [res.stdout[-1500:]]}
    elif st["state"] == "awaiting_human":
        C.log_event("stop_allowed", reason="awaiting_human", milestone=st["current_milestone"])
        _counter().write_text(json.dumps({"count": 0}))  # a human gate resets the budget
        T.sync_state(f"{st['current_milestone']} awaiting human review")
        return 0

    n = _bump()
    if n > MAX_BLOCKED_STOPS:
        (C.logs_dir() / "INCOMPLETE.md").write_text(
            "# 未完成\n\n停止嘗試次數已達上限，以下為當時狀態：\n\n```json\n"
            + json.dumps(st, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
        C.log_event("stop_allowed", reason="budget_exhausted", attempts=n)
        T.sync_state("stop budget exhausted")
        return 0
    C.log_event("stop_blocked", attempt=n, state=st["state"], milestone=st["current_milestone"])
    print("Not done yet (attempt %d/%d).\n- " % (n, MAX_BLOCKED_STOPS) + "\n- ".join(next_steps(st)),
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
