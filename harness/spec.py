#!/usr/bin/env python3
"""Print only the SPEC sections an agent needs, instead of reading all ~640 lines.

  python3 harness/spec.py                 # table of contents (headings with line numbers)
  python3 harness/spec.py "M3 Probe"      # the section whose heading contains the text
  python3 harness/spec.py FR-08 NFR-01    # just the table rows for these requirement ids
  python3 harness/spec.py "§8"            # a whole top-level section

Token rule: agents must use this rather than reading docs/SPEC.md in full (CLAUDE.md).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def _lines() -> list[str]:
    return (C.root() / "docs" / "SPEC.md").read_text(encoding="utf-8").splitlines()


def toc() -> str:
    return "\n".join(f"{i + 1:4d}  {ln}" for i, ln in enumerate(_lines()) if ln.startswith("#"))


def section(query: str) -> str:
    """Return the first section whose heading contains `query` (case-insensitive)."""
    lines = _lines()
    q = query.lower().lstrip("§").strip()
    heads = [(i, m) for i, ln in enumerate(lines) if (m := re.match(r"^(#+)\s+(.*)", ln))]
    exact = [h for h in heads if h[1].group(2).lower().startswith((q + ".", q + " "))]
    fuzzy = [h for h in heads if q in h[1].group(2).lower()]
    for i, m in exact[:1] or fuzzy[:1]:
        level = len(m.group(1))
        end = next((j for j in range(i + 1, len(lines))
                    if re.match(rf"^#{{1,{level}}}\s", lines[j])), len(lines))
        return "\n".join(lines[i:end]).rstrip()
    return f"(no section matching {query!r}; run without arguments for the table of contents)"


def requirement_rows(ids: list[str]) -> str:
    wanted = {i.upper() for i in ids}
    rows = [ln for ln in _lines() if ln.startswith("|") and
            (m := re.match(r"\|\s*~*([A-Z]+-\d+)", ln)) and m.group(1) in wanted]
    return "\n".join(rows) or "(no matching requirement rows)"


def main(argv: list[str]) -> int:
    if not argv:
        print(toc())
        return 0
    if all(re.fullmatch(r"(?i)N?FR-\d+", a) for a in argv):
        print(requirement_rows(argv))
        return 0
    print("\n\n".join(section(a) for a in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
