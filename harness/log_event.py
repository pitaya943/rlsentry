#!/usr/bin/env python3
"""Logging hook: records every dispatch (architect -> subagent) and report (subagent -> architect).

* logs/events.jsonl gets one short line per event; long texts go to logs/messages/<id>-<kind>.json.
* The first raw payload of each event kind is saved to logs/raw-hook-samples/ so that Stage 0
  can confirm the real field names of this Claude Code version.
* This hook never blocks (always exits 0) and never raises.
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "event"
    try:
        raw = sys.stdin.read()
        data = json.loads(raw or "{}")
        samples = C.logs_dir() / "raw-hook-samples"
        samples.mkdir(exist_ok=True)
        sample = samples / f"{kind}.json"
        if not sample.exists():
            sample.write_text(raw, encoding="utf-8")

        ti = data.get("tool_input") or {}
        body = ti if kind == "dispatch" else data.get("tool_response") if kind == "report" else None
        text = json.dumps(body, ensure_ascii=False) if body is not None else ""
        ticket = re.search(r"Ticket:\s*(T-[\w.-]+)", text)
        review = re.search(r"Review:\s*(\S+)", text)
        eid = uuid.uuid4().hex[:8]
        rec = {"id": eid, "agent": ti.get("subagent_type") or data.get("agent_type"),
               "ticket": ticket.group(1) if ticket else None,
               "review": review.group(1) if review else None}
        if body is not None:
            msg = C.logs_dir() / "messages" / f"{eid}-{kind}.json"
            msg.parent.mkdir(exist_ok=True)
            msg.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            rec["body"] = str(msg.relative_to(C.root()))
        C.log_event(kind, **rec)

        if kind in ("report", "subagent_stop"):
            import tickets as T  # keep CHECKLIST.md in sync after every subagent finishes
            T.render()
    except Exception as exc:  # noqa: BLE001 - logging must never break the run
        C.log_event("log_hook_error", hook=kind, error=repr(exc)[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
