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


def _heading_indices(lines: list[str]) -> list[int]:
    """Indices of real Markdown headings.

    Lines inside ``` fences are skipped: a YAML or shell comment such as `# Expected access
    policy` is not a heading, and treating it as one silently truncates the section an agent
    asked for (SPEC.md:342 cut §6 short and hid tables/defaults/fail_on).
    """
    out: list[int] = []
    fence = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
        elif not fence and re.match(r"^#+\s", ln):
            out.append(i)
    return out


def toc() -> str:
    lines = _lines()
    return "\n".join(f"{i + 1:4d}  {lines[i]}" for i in _heading_indices(lines))


def section(query: str) -> str:
    """Return the first section whose heading contains `query` (case-insensitive)."""
    lines = _lines()
    q = query.lower().lstrip("§").strip()
    idx = _heading_indices(lines)
    heads = [(i, m) for i in idx if (m := re.match(r"^(#+)\s+(.*)", lines[i]))]
    exact = [h for h in heads if h[1].group(2).lower().startswith((q + ".", q + " "))]
    fuzzy = [h for h in heads if q in h[1].group(2).lower()]
    for i, m in exact[:1] or fuzzy[:1]:
        level = len(m.group(1))
        end = next((j for j in idx if j > i and re.match(rf"^#{{1,{level}}}\s", lines[j])), len(lines))
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
