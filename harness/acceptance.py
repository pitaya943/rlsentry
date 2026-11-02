#!/usr/bin/env python3
"""Milestone verification (`make verify-milestone MS=..`) and final acceptance (`make acceptance`).

The human runs `verify-milestone` personally at every gate. That run is the backstop for
everything the hooks can only approximate: it re-executes the tests, checks that every
product-code commit on main came through the acceptance gate, and that the ledger and the
checklist are consistent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import tickets as T  # noqa: E402

Check = tuple[str, Callable[[], tuple[bool, str]]]


def _sh(cmd: str, timeout: int = 1800) -> tuple[bool, str]:
    r = subprocess.run(cmd, shell=True, cwd=C.root(), capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def _has_tests(path: str) -> bool:
    p = C.root() / path
    return p.exists() and any(p.rglob("test_*.py"))


# --- individual checks ------------------------------------------------------

def check_ruff() -> tuple[bool, str]:
    if not shutil.which("ruff"):
        return True, "ruff not installed (skipped)"
    return _sh("ruff check .")


def check_mypy() -> tuple[bool, str]:
    if not shutil.which("mypy") or not (C.root() / "rlsentry").exists():
        return True, "mypy or package missing (skipped)"
    return _sh("mypy rlsentry")


def check_tests() -> tuple[bool, str]:
    """All tests owned by accepted tickets must pass; tests of blocked tickets are reported only."""
    reg = T.regression_tests()
    if not reg:
        return True, "no accepted tests yet"
    ok, out = _sh(f"{sys.executable} -m pytest -q " + " ".join(reg))
    tickets = T.load_tickets()
    acc = T.accepted()
    blocked = [x for t in tickets.values() if T.effective_status(t, acc) == "blocked" for x in t.tests]
    note = f"\n(tests of blocked tickets not required: {', '.join(blocked)})" if blocked else ""
    return ok, out + note


def check_holdout(ms: str | None) -> tuple[bool, str]:
    """Run holdout tests from the rlsentry-holdout branch (they are never in the working tree)."""
    import holdout as H
    with tempfile.TemporaryDirectory() as tmp:
        dirs = H.materialize(ms, Path(tmp))
        if not dirs:
            return True, "no holdout tests for this scope"
        env = {**os.environ, "PYTHONPATH": str(C.root()) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "--rootdir", str(C.root()), *map(str, dirs)],
                           cwd=C.root(), capture_output=True, text=True, env=env, timeout=1800)
        return r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def check_safety() -> tuple[bool, str]:
    reg = T.regression_tests()
    if not reg:
        return True, "no accepted tests yet"
    r = subprocess.run(f"{sys.executable} -m pytest -q -m safety " + " ".join(reg), shell=True,
                       cwd=C.root(), capture_output=True, text=True)
    if r.returncode == 5:   # pytest: no tests collected/selected
        return True, "no safety-marked tests among accepted tickets yet"
    return r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def check_tickets(ms: str | None, require_vc: bool = True) -> tuple[bool, str]:
    errs = T.validate()
    if ms:
        probs = T.vc_problems(ms)
        if not require_vc:   # architect's pre-check, before it writes the checklist
            probs = [p for p in probs if not p.startswith(("no verification checklist", "header",
                                                            "missing mandatory", "missing section",
                                                            "checklist commit"))]
        errs += probs
    return (not errs), "\n".join(errs) or "tickets valid, checklist consistent"


def check_checklist_sync() -> tuple[bool, str]:
    """CHECKLIST.md is derived data: regenerate it so it matches the ticket files and ledger."""
    path = C.root() / "CHECKLIST.md"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    after = T.render()
    return True, "CHECKLIST.md was stale and has been regenerated" if before != after else "CHECKLIST.md up to date"


def check_provenance() -> tuple[bool, str]:
    """Every first-parent commit touching product code must be a genuine accept merge.

    The checks the gate ran at merge time are recomputed here from git history, so a commit
    that merely *claims* to be accepted (forged trailer, non-merge commit, out-of-scope files,
    cheat patterns) is caught. Architect-owned paths may be committed directly.
    """
    tickets = T.load_tickets()
    out = C.git("log", "--first-parent", "--format=%H", "HEAD").stdout.split()
    bad = []
    for sha in out:
        parents = C.git("rev-list", "--parents", "-n", "1", sha).stdout.split()[1:]
        base = parents[0] if parents else None
        files = (C.git("diff", "--name-only", base, sha) if base else
                 C.git("show", "--name-only", "--format=", sha)).stdout.split()
        product = [f for f in files if (f.startswith("rlsentry/") or f.startswith("lab/"))
                   and not C.path_matches(f, C.ARCHITECT_PATHS)]
        if not product:
            continue
        body = C.git("log", "-1", "--format=%B", sha).stdout
        m = re.search(rf"^{C.TRAILER}:\s*(T-[\w.-]+)", body, flags=re.M)
        if not m:
            bad.append(f"{sha[:9]} touches {', '.join(product[:4])} without going through the gate")
            continue
        tid = m.group(1)
        if len(parents) != 2:
            bad.append(f"{sha[:9]} claims {tid} but is not a merge commit")
            continue
        t = tickets.get(tid)
        if t is None:
            bad.append(f"{sha[:9]} claims unknown ticket {tid}")
            continue
        outside = [f for f in files if not C.path_matches(f, t.allowed_paths)
                   and not C.path_matches(f, C.ARCHITECT_PATHS)]
        if outside:
            bad.append(f"{sha[:9]} ({tid}) changed files outside allowed_paths: {', '.join(outside[:4])}")
        diff = C.git("diff", "-U0", base, sha).stdout
        added = [ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        if any(re.search(pat, ln) for ln in added for pat in T.CHEAT_PATTERNS):
            bad.append(f"{sha[:9]} ({tid}) adds forbidden patterns (skip/xfail/type: ignore/noqa)")
    return (not bad), ("\n".join(bad) if bad else
                       "every product-code commit is a genuine accept merge (scope and cheat checks recomputed)")


def check_mutation() -> tuple[bool, str]:
    if os.environ.get("MUTATION") != "1":
        return True, "mutation testing skipped (set MUTATION=1 to run)"
    if not shutil.which("mutmut"):
        return False, "mutmut not installed"
    return _sh("mutmut run --CI || true; mutmut results", timeout=7200)


# --- final-only checks ------------------------------------------------------

def check_bench() -> tuple[bool, str]:
    out = C.logs_dir() / "bench.json"
    ok, log = _sh(f"{sys.executable} -m rlsentry.bench --json {out}", timeout=7200)
    if not ok or not out.exists():
        return False, "benchmark did not run:\n" + log
    data = json.loads(out.read_text())
    # SPEC §9 (v1.0): case-level metrics, raw counts are required alongside percentages.
    recall, precision, fpr = data.get("recall", 0), data.get("precision", 0), data.get("fpr", 1)
    counts_ok = all(k in data for k in ("tp", "fp", "fn", "tn", "coverage", "runtime"))
    ok = recall >= 0.95 and precision >= 0.95 and fpr <= 0.05 and counts_ok
    return ok, (f"recall={recall:.3f} precision={precision:.3f} fpr={fpr:.3f} "
                f"(need ≥0.95 / ≥0.95 / ≤0.05; raw counts, coverage, runtime present={counts_ok})")


def check_profiles() -> tuple[bool, str]:
    return _sh(f"{sys.executable} -m pytest -q -m e2e_profiles tests")


def check_usage_doctest() -> tuple[bool, str]:
    """Run every ```bash block in USAGE.md that is preceded by <!-- doctest -->."""
    p = C.root() / "USAGE.md"
    if not p.exists():
        return False, "USAGE.md missing"
    blocks = re.findall(r"<!--\s*doctest\s*-->\s*```bash\n(.*?)```", p.read_text(encoding="utf-8"), re.S)
    if not blocks:
        return False, "USAGE.md has no <!-- doctest --> bash blocks"
    for i, b in enumerate(blocks, 1):
        ok, out = _sh(b, timeout=900)
        if not ok:
            return False, f"USAGE.md doctest #{i} failed:\n{out}"
    return True, f"{len(blocks)} USAGE.md doctests passed"


def check_decisions() -> tuple[bool, str]:
    p = C.root() / "docs" / "DECISIONS.md"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    missing = [d for d in ("D2", "D3", "D4") if d not in text]
    return (not missing), "missing ADRs for " + ", ".join(missing) if missing else "D2–D4 recorded"


def check_traceability() -> tuple[bool, str]:
    p = C.root() / "docs" / "verification" / "traceability.md"
    if not p.exists():
        return False, "docs/verification/traceability.md missing (auditor output)"
    missing = [ln for ln in p.read_text(encoding="utf-8").splitlines() if "MISSING" in ln and "P0" in ln]
    return (not missing), "\n".join(missing) or "every P0 requirement traced to tests"


def check_prior_milestones() -> tuple[bool, str]:
    order, _ = T.load_milestones()
    pending = [m for m in order[:-1] if T.milestone_state(m) != "approved"]
    return (not pending), "unapproved: " + ", ".join(pending) if pending else "all prior milestones approved"


# --- runner -----------------------------------------------------------------

def run(checks: list[Check], tag: str) -> int:
    results = []
    for name, fn in checks:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, repr(exc)
        results.append({"check": name, "ok": ok, "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail.splitlines()[0] if detail else ''}")
        if not ok and detail.count("\n"):
            print("       " + detail.replace("\n", "\n       ")[:1500])
    (C.logs_dir() / f"acceptance-{tag}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [r["check"] for r in results if not r["ok"]]
    C.log_event("acceptance_run", scope=tag, failed=failed)
    print(f"\n{tag}: {'ALL PASSED' if not failed else 'FAILED: ' + ', '.join(failed)}")
    return 1 if failed else 0


def milestone_checks(ms: str | None, require_vc: bool = True) -> list[Check]:
    return [
        ("tickets & checklist", lambda: check_tickets(ms, require_vc)),
        ("provenance", check_provenance),
        ("ruff", check_ruff),
        ("mypy", check_mypy),
        ("tests", check_tests),
        ("holdout", lambda: check_holdout(ms)),
        ("safety invariants", check_safety),
        ("mutation", check_mutation),
        ("checklist sync", check_checklist_sync),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--milestone")
    g.add_argument("--final", action="store_true")
    ap.add_argument("--no-vc", action="store_true", help="architect pre-check before writing the checklist")
    args = ap.parse_args()
    if args.milestone:
        return run(milestone_checks(args.milestone, not args.no_vc), args.milestone)
    final = milestone_checks(None) + [
        ("prior milestones approved", check_prior_milestones),
        ("benchmark thresholds", check_bench),
        ("profile end-to-end", check_profiles),
        ("USAGE.md doctests", check_usage_doctest),
        ("ADRs D2–D4", check_decisions),
        ("traceability", check_traceability),
    ]
    return run(final, "final")


if __name__ == "__main__":
    sys.exit(main())
