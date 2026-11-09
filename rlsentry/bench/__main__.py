"""`python -m rlsentry.bench`: run the lab benchmark and print the SPEC §9 summary."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from rlsentry.bench.run import run_bench
from rlsentry.contracts.ground_truth import SCENARIO_IDS, BenchReport
from rlsentry.contracts.models import Profile


def _summary(rep: BenchReport) -> list[str]:
    """One screen of raw counts beside each ratio, then the things a reader must not miss."""
    lines = [
        f"recall {rep.tp}/{rep.tp + rep.fn} = {rep.recall:.3f}",
        f"precision {rep.tp}/{rep.tp + rep.fp} = {rep.precision:.3f}",
        f"fpr {rep.fp_safe}/{rep.fp_safe + rep.tn} = {rep.fpr:.3f}",
        (f"coverage = {rep.coverage:.3f}  inconclusive_ratio = {rep.inconclusive_ratio:.3f}"
         f"  safe_decided_ratio = {rep.safe_decided_ratio:.3f}"),
        f"tp {rep.tp}  fn {rep.fn}  fp {rep.fp}  tn {rep.tn}  fp_safe {rep.fp_safe}",
    ]
    if rep.runtime:
        lines.append("runtime: " + ", ".join(f"{k} tables {v}s" for k, v in rep.runtime.items()))
    for sid, ids in rep.probe_only.items():
        lines.append(f"probe-only {sid}: {', '.join(ids)}")
    for s in rep.scenarios:
        if s.splinter_match is False:
            lines.append(f"splinter mismatch {s.scenario}: measured {s.splinter}")
        if s.profile == Profile.AUDIT and s.db_writes != 0:
            lines.append(f"AUDIT db_writes {s.scenario}: {s.db_writes}")
        for c in s.cases:
            if c.verdict == "inconclusive_violation":
                lines.append(f"inconclusive_violation {s.scenario}/{s.profile.value} "
                             f"{c.case_id}: {c.detail}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Parse options, run the bench, print the summary; 1 if an AUDIT run wrote (NFR-01)."""
    ap = argparse.ArgumentParser(prog="python -m rlsentry.bench")
    ap.add_argument("--scenario", action="append", metavar="ID")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--no-runtime", action="store_true")
    args = ap.parse_args(argv)
    ids: list[str] = args.scenario or list(SCENARIO_IDS)
    bad = [s for s in ids if s not in SCENARIO_IDS]
    if bad:
        print(f"unknown scenario: {', '.join(bad)}", file=sys.stderr)
        return 2
    rep = run_bench(ids, runtime=not (args.no_runtime or args.scenario))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rep.model_dump_json(indent=2), "utf-8")
    print("\n".join(_summary(rep)))
    return 1 if any(s.profile == Profile.AUDIT and s.db_writes != 0 for s in rep.scenarios) else 0


if __name__ == "__main__":
    raise SystemExit(main())
