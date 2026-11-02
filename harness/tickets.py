#!/usr/bin/env python3
"""Ticket scheduler, milestone gates and acceptance ledger for RLSentry.

Single source of truth
----------------------
* Ticket files (docs/tickets/*.md) hold plan data: deps, owner, allowed paths, attempts.
* The acceptance ledger is git history: merge commits with a `RLSentry-Accepted` trailer.
  A ticket file saying ``status: done`` means nothing on its own.
* SSH-signed approval files on the `rlsentry-approvals` branch decide which milestones are
  unlocked. Only the human holds the private key.

CLI (run from the repo root):
  status [--json] | validate | ready | start ID | fail ID --reason TEXT
  accept ID --branch BRANCH | render | vc-check MS | dispatch-check ID AGENT
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MAX_ATTEMPTS = 5
MAX_PARALLEL = 6
MAX_VC_ITEMS = 16          # 15 items + the mandatory "run verify-milestone yourself" item
CHEAT_PATTERNS = [r"pytest\.mark\.skip", r"pytest\.skip\(", r"\bxfail\b", r"type:\s*ignore",
                  r"\bnoqa\b", r"pragma:\s*no\s*cover"]
TERMINAL = {"done", "blocked"}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class Ticket:
    id: str
    title: str
    milestone: str
    agent: str
    depends_on: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    status: str = "todo"
    attempts: int = 0
    blocked_reason: str | None = None
    origin: str = "plan"
    path: Path | None = None
    body: str = ""

    def meta(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("id", "title", "milestone", "agent", "depends_on",
                                              "allowed_paths", "tests", "status", "attempts",
                                              "blocked_reason", "origin")}

    def save(self) -> None:
        assert self.path is not None
        self.path.write_text(C.dump_frontmatter(self.meta(), self.body), encoding="utf-8")


def load_milestones() -> tuple[list[str], dict[str, dict[str, Any]]]:
    data = C.load_yaml(C.harness_dir() / "milestones.yaml")
    return list(data["order"]), dict(data["milestones"])


def load_tickets() -> dict[str, Ticket]:
    out: dict[str, Ticket] = {}
    d = C.tickets_dir()
    if not d.exists():
        return out
    for p in sorted(d.glob("T-*.md")):
        meta, body = C.parse_frontmatter(p.read_text(encoding="utf-8"))
        known = {k: meta[k] for k in Ticket.__dataclass_fields__ if k in meta and k not in ("path", "body")}
        t = Ticket(**{"title": "", "milestone": "", "agent": "", **known})
        t.depends_on = list(t.depends_on or [])
        t.allowed_paths = list(t.allowed_paths or [])
        t.tests = list(t.tests or [])
        t.path, t.body = p, body
        out[t.id] = t
    return out


# ---------------------------------------------------------------------------
# Ledger: derived from git history, so it survives cloud VM resets
# ---------------------------------------------------------------------------
# Every accepted ticket is a merge commit on the main line whose message carries a
# `RLSentry-Accepted: T-xxx` trailer. A forged trailer gains nothing: the human's
# `make verify-milestone` recomputes scope, cheat and test checks for every such commit.

def ledger() -> list[dict[str, Any]]:
    """Chronological list of {ticket, commit} for accept commits on the first-parent line."""
    out = C.git("log", "--first-parent", "--reverse", "--format=%H%x1f%B%x1e", "HEAD")
    if out.returncode != 0:
        return []
    entries = []
    for rec in out.stdout.split("\x1e"):
        if "\x1f" not in rec:
            continue
        sha, body = rec.strip("\n").split("\x1f", 1)
        for m in re.finditer(rf"^{C.TRAILER}:\s*(T-[\w.-]+)\s*$", body, flags=re.M):
            entries.append({"ticket": m.group(1), "commit": sha.strip()})
    return entries


def accepted() -> dict[str, str]:
    """ticket id -> latest accept commit on the main line."""
    return {e["ticket"]: e["commit"] for e in ledger()}


def effective_status(t: Ticket, acc: dict[str, str]) -> str:
    if t.id in acc:
        return "done"
    return t.status if t.status != "done" else "todo"   # a self-declared 'done' is ignored


def sync_state(message: str, push: bool = True) -> None:
    """Commit the harness-owned bookkeeping (tickets, checklist, logs) and push if possible.

    Cloud VMs are reclaimed when idle, so anything not pushed is lost. Failures are logged,
    never raised: a missing remote (tests, offline work) must not break the run.
    """
    try:
        paths = [p for p in ("docs/tickets", "CHECKLIST.md", "logs") if (C.root() / p).exists()]
        if not paths:
            return
        C.git("add", "-A", "--", *paths)
        if C.git("diff", "--cached", "--quiet").returncode != 0:
            C.git("commit", "-q", "-m", f"rlsentry: {message}")
        if push and C.git("remote").stdout.strip():
            r = C.git("push", "-q", "-u", "origin", "HEAD")
            if r.returncode != 0:
                C.log_event("push_failed", error=r.stderr[-500:])
    except Exception as exc:  # noqa: BLE001
        C.log_event("sync_failed", error=repr(exc)[:500])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(tickets: dict[str, Ticket] | None = None) -> list[str]:
    tickets = tickets if tickets is not None else load_tickets()
    order, _ = load_milestones()
    errs: list[str] = []
    agents = C.IMPLEMENTERS | {"architect"}
    for t in tickets.values():
        if t.path and t.path.stem.split("-", 2)[:2] != t.id.split("-")[:2]:
            errs.append(f"{t.id}: file name {t.path.name} does not start with its id")
        if t.milestone not in order:
            errs.append(f"{t.id}: unknown milestone {t.milestone!r}")
        if t.agent not in agents:
            errs.append(f"{t.id}: unknown agent {t.agent!r}")
        if not t.allowed_paths:
            errs.append(f"{t.id}: allowed_paths is empty")
        for ap in t.allowed_paths:
            if C.path_matches(ap, C.HARNESS_PROTECTED):
                errs.append(f"{t.id}: allowed path {ap} is harness-protected")
            if t.agent in C.IMPLEMENTERS and C.path_matches(ap, C.SUBAGENT_PROTECTED):
                errs.append(f"{t.id}: allowed path {ap} is not writable by subagents")
        for d in t.depends_on:
            if d not in tickets:
                errs.append(f"{t.id}: depends on missing ticket {d}")
            elif t.milestone in order and tickets[d].milestone in order and \
                    order.index(tickets[d].milestone) > order.index(t.milestone):
                errs.append(f"{t.id}: depends on {d} from a later milestone")
    # cycle detection (iterative DFS with colours)
    colour: dict[str, int] = {}
    for start in tickets:
        stack = [(start, iter(tickets[start].depends_on))]
        colour[start] = colour.get(start, 0) or 1
        if colour[start] == 2:
            continue
        while stack:
            node, it = stack[-1]
            nxt = next((d for d in it if d in tickets), None)
            if nxt is None:
                colour[node] = 2
                stack.pop()
            elif colour.get(nxt, 0) == 1:
                errs.append(f"dependency cycle through {node} -> {nxt}")
                return errs
            elif colour.get(nxt, 0) == 0:
                colour[nxt] = 1
                stack.append((nxt, iter(tickets[nxt].depends_on)))
    return errs


# ---------------------------------------------------------------------------
# Verification checklists and approvals
# ---------------------------------------------------------------------------

def latest_vc(ms: str) -> tuple[Path | None, int]:
    best: tuple[Path | None, int] = (None, 0)
    for p in C.verification_dir().glob(f"{ms}-v*.md"):
        m = re.fullmatch(rf"{re.escape(ms)}-v(\d+)\.md", p.name)
        if m and int(m.group(1)) > best[1]:
            best = (p, int(m.group(1)))
    return best


def milestone_last_commit(ms: str, tickets: dict[str, Ticket], acc: dict[str, str]) -> str | None:
    """Most recent ledger commit belonging to a ticket of this milestone."""
    ids = {t.id for t in tickets.values() if t.milestone == ms}
    last = None
    for e in ledger():
        if e["ticket"] in ids and acc.get(e["ticket"]) == e["commit"]:
            last = e["commit"]
    return last


def vc_problems(ms: str, tickets: dict[str, Ticket] | None = None) -> list[str]:
    tickets = tickets if tickets is not None else load_tickets()
    acc = accepted()
    p, _ = latest_vc(ms)
    if p is None:
        return [f"no verification checklist docs/verification/{ms}-vN.md"]
    text = p.read_text(encoding="utf-8")
    probs = []
    m = re.search(r"main @ ([0-9a-f]{7,40})", text)
    last = milestone_last_commit(ms, tickets, acc)
    if not m:
        probs.append("header must contain 'main @ <commit>'")
    elif last and not last.startswith(m.group(1)):
        probs.append(f"checklist commit {m.group(1)} is not the milestone's last accepted commit {last[:9]}")
    if f"make verify-milestone MS={ms}" not in text:
        probs.append(f"missing mandatory item: run `make verify-milestone MS={ms}` yourself")
    if "## 3." not in text:
        probs.append("missing section '## 3.' (manual verification items)")
    n_items = len(re.findall(r"^\s*- \[ \]", text, flags=re.M))
    if n_items > MAX_VC_ITEMS:
        probs.append(f"{n_items} checklist items; keep it to at most {MAX_VC_ITEMS}")
    open_t = [t.id for t in tickets.values()
              if t.milestone == ms and effective_status(t, acc) not in TERMINAL]
    if open_t:
        probs.append(f"tickets not terminal: {', '.join(open_t)}")
    return probs


_fetched = False


def _approval_texts(ms: str) -> tuple[str, str] | None:
    """(yaml, signature) for a milestone, from a local folder or the approvals git ref."""
    d = C.approvals_dir()
    if d is not None:
        y, sig = d / f"{ms}.yaml", d / f"{ms}.yaml.sig"
        if y.exists() and sig.exists():
            return y.read_text(encoding="utf-8"), sig.read_text(encoding="utf-8")
        return None
    global _fetched
    ref = C.approvals_ref()
    if ref.startswith("origin/") and not _fetched:
        C.git("fetch", "-q", "origin", ref.split("/", 1)[1])
        _fetched = True
    y = C.git("show", f"{ref}:{ms}.yaml")
    sig = C.git("show", f"{ref}:{ms}.yaml.sig")
    if y.returncode != 0 or sig.returncode != 0:
        return None
    return y.stdout, sig.stdout


def signers_problem() -> str | None:
    p = C.allowed_signers()
    if not p.exists() or "REPLACE_WITH_YOUR_PUBLIC_KEY" in p.read_text():
        return "harness/allowed_signers is not configured: approvals cannot be verified"
    if not shutil.which("ssh-keygen"):
        return "ssh-keygen is not installed: approvals cannot be verified"
    return None


def verify_signature(text: str, signature: str) -> bool:
    """Check an SSH signature against the frozen allowed_signers file (ssh-keygen -Y verify)."""
    if signers_problem():
        return False
    lines = [ln for ln in C.allowed_signers().read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    principal = lines[0].split()[0]
    with tempfile.TemporaryDirectory() as tmp:
        sig_path = Path(tmp) / "a.sig"
        sig_path.write_text(signature)
        r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(C.allowed_signers()), "-I", principal,
                            "-n", C.APPROVAL_NAMESPACE, "-s", str(sig_path)],
                           input=text, capture_output=True, text=True)
    return r.returncode == 0


def approval(ms: str) -> dict[str, Any] | None:
    """A milestone approval, or None if absent, unparsable or not signed by the human."""
    texts = _approval_texts(ms)
    if texts is None:
        return None
    text, sig = texts
    if not verify_signature(text, sig):
        C.log_event("approval_rejected", milestone=ms, reason="bad or missing signature")
        return None
    try:
        import yaml
        return yaml.safe_load(text) or None
    except Exception:  # noqa: BLE001
        return None


def milestone_state(ms: str, tickets: dict[str, Ticket] | None = None) -> str:
    """locked | active | awaiting_human | changes_requested | approved"""
    tickets = tickets if tickets is not None else load_tickets()
    order, _ = load_milestones()
    for earlier in order[: order.index(ms)]:
        if milestone_state(earlier, tickets) != "approved":
            return "locked"
    acc = accepted()
    mine = [t for t in tickets.values() if t.milestone == ms]
    if not mine or any(effective_status(t, acc) not in TERMINAL for t in mine):
        return "active"
    vc, _ = latest_vc(ms)
    if vc is None or vc_problems(ms, tickets):
        return "active"
    ap = approval(ms)
    if ap and ap.get("checklist_sha256") == C.sha256_file(vc):
        return "approved" if ap.get("decision") == "approve" else "changes_requested"
    return "awaiting_human"


def current_milestone(tickets: dict[str, Ticket] | None = None) -> str | None:
    tickets = tickets if tickets is not None else load_tickets()
    order, _ = load_milestones()
    for ms in order:
        if milestone_state(ms, tickets) != "approved":
            return ms
    return None


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _critical_lengths(tickets: dict[str, Ticket]) -> dict[str, int]:
    dependents: dict[str, list[str]] = {k: [] for k in tickets}
    for t in tickets.values():
        for d in t.depends_on:
            dependents.setdefault(d, []).append(t.id)
    memo: dict[str, int] = {}

    def length(tid: str) -> int:
        if tid not in memo:
            memo[tid] = 1 + max((length(c) for c in dependents.get(tid, [])), default=0)
        return memo[tid]
    return {k: length(k) for k in tickets}


def _overlap(a: list[str], b: list[str]) -> bool:
    return any(C.path_matches(x, b) or C.path_matches(y, a) for x in a for y in b)


def ready(tickets: dict[str, Ticket] | None = None, limit: int = MAX_PARALLEL) -> list[Ticket]:
    tickets = tickets if tickets is not None else load_tickets()
    ms = current_milestone(tickets)
    if ms is None or milestone_state(ms, tickets) not in ("active", "changes_requested"):
        return []
    acc = accepted()
    running = [t for t in tickets.values() if effective_status(t, acc) == "in_progress"]
    crit = _critical_lengths(tickets)
    cands = [t for t in tickets.values()
             if t.milestone == ms and effective_status(t, acc) == "todo"
             and all(d in acc for d in t.depends_on)]
    cands.sort(key=lambda t: (-crit[t.id], t.id))
    chosen: list[Ticket] = []
    for t in cands:
        if len(running) + len(chosen) >= limit:
            break
        if any(_overlap(t.allowed_paths, o.allowed_paths) for o in running + chosen):
            continue
        chosen.append(t)
    return chosen


def start(tid: str) -> str:
    tickets = load_tickets()
    if tid not in {t.id for t in ready(tickets, limit=10_000)}:
        raise SystemExit(f"{tid} is not ready (deps, milestone gate, conflicts or parallel limit)")
    t = tickets[tid]
    t.status, t.attempts = "in_progress", t.attempts + 1
    t.save()
    C.log_event("ticket_start", ticket=tid, agent=t.agent, attempt=t.attempts)
    return f"{tid} started (attempt {t.attempts})"


def fail(tid: str, reason: str) -> str:
    tickets = load_tickets()
    t = tickets[tid]
    if t.attempts >= MAX_ATTEMPTS:
        _block(tickets, tid, f"failed {t.attempts} attempts: {reason}")
        msg = f"{tid} blocked after {t.attempts} attempts"
    else:
        t.status = "todo"
        t.save()
        msg = f"{tid} back to todo ({t.attempts}/{MAX_ATTEMPTS} attempts used)"
    C.log_event("ticket_fail", ticket=tid, reason=reason[:2000], attempts=t.attempts)
    return msg


def _block(tickets: dict[str, Ticket], tid: str, reason: str) -> None:
    queue = [(tid, reason)]
    while queue:
        cur, why = queue.pop()
        t = tickets[cur]
        if t.status == "blocked":
            continue
        t.status, t.blocked_reason = "blocked", why
        t.save()
        C.log_event("ticket_blocked", ticket=cur, reason=why)
        queue += [(o.id, f"dependency {cur} blocked") for o in tickets.values() if cur in o.depends_on]


# ---------------------------------------------------------------------------
# Acceptance gate (the only path into main for ticket work)
# ---------------------------------------------------------------------------

def _changed_files(rev_range: str) -> list[str]:
    out = C.git("diff", "--name-only", rev_range)
    return [line for line in out.stdout.splitlines() if line]


def _cheats(rev_range: str) -> list[str]:
    diff = C.git("diff", "-U0", rev_range).stdout
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    return [ln.strip() for ln in added for pat in CHEAT_PATTERNS if re.search(pat, ln)]


def regression_tests(tickets: dict[str, Ticket] | None = None) -> list[str]:
    """Tests owned by already-accepted tickets. These must keep passing on every merge.

    Tests of tickets that are not accepted yet are expected to fail (TDD: the architect writes
    them first), so they are not part of the regression set.
    """
    tickets = tickets if tickets is not None else load_tickets()
    acc = accepted()
    out: list[str] = []
    for t in tickets.values():
        if t.id in acc:
            out += [x for x in t.tests if (C.root() / x).exists() and x not in out]
    return out


def _run_checks(t: Ticket) -> subprocess.CompletedProcess[str]:
    cmd = os.environ.get("RLSENTRY_CHECK_CMD", "make check")
    env = {**os.environ, "TESTS": " ".join(t.tests), "TICKET": t.id,
           "REGRESSION": " ".join(regression_tests())}
    return subprocess.run(cmd, shell=True, cwd=C.root(), capture_output=True, text=True, env=env)


def compact_failure(output: str, limit: int = 1500) -> str:
    """Keep only what a fix needs: failing test ids, assertion/error lines, lint codes.

    Full output is written to logs/ for the human; agents get the compact form, which keeps the
    architect's context (re-read every turn) small and the resume message to a subagent short.
    """
    keep = [ln for ln in output.splitlines()
            if ln.startswith(("FAILED", "ERROR", "E ", "E\t")) or re.match(r"^\S+:\d+:\d+: [A-Z]+\d+", ln)
            or "Error:" in ln or "error:" in ln]
    text = "\n".join(dict.fromkeys(keep)) or output[-limit:]
    return text[:limit] + ("\n… (truncated; full output in logs/)" if len(text) > limit else "")


def accept(tid: str, branch: str) -> tuple[bool, str]:
    """Merge a ticket branch into main only if every gate passes; otherwise abort and count a failure.

    Architect-owned tickets use the same path (work on a branch, then accept), with the extra
    rule that they may only touch ARCHITECT_PATHS. There is deliberately no way to mark a
    ticket done without going through this function.
    """
    tickets = load_tickets()
    t = tickets[tid]
    if t.status != "in_progress":
        return False, f"{tid} is {t.status}, not in_progress (run `start` first)"
    if C.git("rev-parse", "--verify", branch).returncode != 0:
        return False, f"unknown branch or commit {branch!r}"
    rev_range = f"HEAD...{branch}"
    files = _changed_files(rev_range)
    if not files:
        return False, "no changes found on the branch"
    bad = [f for f in files if not C.path_matches(f, t.allowed_paths)
           or (t.agent == "architect" and not C.path_matches(f, C.ARCHITECT_PATHS))]
    if bad:
        reason = "files outside allowed_paths: " + ", ".join(bad)
        return False, fail(tid, reason) + "\n" + reason
    cheats = _cheats(rev_range)
    if cheats:
        reason = "forbidden patterns added: " + " | ".join(cheats[:5])
        return False, fail(tid, reason) + "\n" + reason
    m = C.git("merge", "--no-ff", "--no-commit", branch)
    if m.returncode != 0:
        C.git("merge", "--abort")
        reason = "merge conflict:\n" + m.stdout + m.stderr
        return False, fail(tid, reason) + "\n" + reason
    res = _run_checks(t)
    if res.returncode != 0:
        C.git("merge", "--abort")
        full = res.stdout + res.stderr
        (C.logs_dir() / f"check-{tid}-attempt{t.attempts}.log").write_text(full, encoding="utf-8")
        reason = "checks failed:\n" + compact_failure(full)
        return False, fail(tid, reason) + "\n" + reason
    tip = C.git("rev-parse", branch).stdout.strip()
    C.git("commit", "-q", "-m", f"accept {tid}: {t.title}\n\n{C.TRAILER}: {tid}\nRLSentry-Branch-Tip: {tip}",
          check=True)
    commit = C.git("rev-parse", "HEAD").stdout.strip()
    t.status = "done"
    t.save()
    C.log_event("ticket_accepted", ticket=tid, commit=commit, files=files)
    render()
    sync_state(f"{tid} accepted")
    return True, f"{tid} accepted at {commit[:9]}"


def dispatch_check(tid: str, agent: str) -> tuple[bool, str]:
    tickets = load_tickets()
    if tid not in tickets:
        return False, f"unknown ticket {tid}"
    t = tickets[tid]
    if t.agent != agent:
        return False, f"{tid} belongs to {t.agent}, not {agent}"
    if t.status != "in_progress":
        return False, f"{tid} is {t.status}; run `python3 harness/tickets.py start {tid}` first"
    ms = current_milestone(tickets)
    if t.milestone != ms or milestone_state(ms, tickets) not in ("active", "changes_requested"):
        return False, f"{tid} is in {t.milestone}, which is not the unlocked milestone ({ms})"
    return True, "ok"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

STATE_LABEL = {"locked": "鎖定", "active": "進行中", "awaiting_human": "等待你審查",
               "changes_requested": "你要求修改", "approved": "已核准"}


def render() -> str:
    tickets = load_tickets()
    order, meta = load_milestones()
    acc = accepted()
    done = sum(1 for t in tickets.values() if effective_status(t, acc) == "done")
    blocked = [t for t in tickets.values() if effective_status(t, acc) == "blocked"]
    running = sum(1 for t in tickets.values() if effective_status(t, acc) == "in_progress")
    lines = ["# RLSentry 生產檢核清單", "",
             f"自動產生，請勿手改 · 完成 {done}/{len(tickets)} · 進行中 {running} · blocked {len(blocked)}", ""]
    for ms in order:
        st = milestone_state(ms, tickets)
        mark = "x" if st == "approved" else " "
        lines.append(f"## [{mark}] {ms} {meta[ms]['title']}（{STATE_LABEL[st]}）")
        for t in sorted((t for t in tickets.values() if t.milestone == ms), key=lambda t: t.id):
            es = effective_status(t, acc)
            box = "x" if es == "done" else " "
            extra = ""
            if es == "blocked":
                extra = f" ⚠ blocked：{t.blocked_reason}"
            elif es != "done" and t.depends_on:
                deps = " ".join(f"{d}{'✓' if d in acc else '…'}" for d in t.depends_on)
                extra = f" ← 依賴 {deps}"
            lines.append(f"- [{box}] {t.id} {t.title}（{t.agent}，{es}，{t.attempts} 次）{extra}")
        vc, n = latest_vc(ms)
        if vc:
            lines.append(f"- 驗證清單：{vc.relative_to(C.root())}（v{n}）")
        lines.append("")
    text = "\n".join(lines)
    (C.root() / "CHECKLIST.md").write_text(text, encoding="utf-8")
    return text


def _spec_problems() -> list[str]:
    spec = C.root() / "docs" / "SPEC.md"
    if not spec.exists() or spec.read_text(encoding="utf-8").startswith("SPEC-PLACEHOLDER"):
        return ["docs/SPEC.md is missing or still the placeholder: the human must export the SPEC first"]
    return []


def status() -> dict[str, Any]:
    tickets = load_tickets()
    order, _ = load_milestones()
    acc = accepted()
    ms = current_milestone(tickets)
    return {
        "current_milestone": ms,
        "state": milestone_state(ms, tickets) if ms else "all_approved",
        "milestones": {m: milestone_state(m, tickets) for m in order},
        "ready": [t.id for t in ready(tickets)],
        "in_progress": [t.id for t in tickets.values() if effective_status(t, acc) == "in_progress"],
        "blocked": {t.id: t.blocked_reason for t in tickets.values() if effective_status(t, acc) == "blocked"},
        "vc_problems": vc_problems(ms, tickets) if ms else [],
        "validation_errors": validate(tickets) + _spec_problems() + ([signers_problem()] if signers_problem() else []),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tickets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").add_argument("--json", action="store_true")
    sub.add_parser("validate")
    sub.add_parser("ready")
    sub.add_parser("render")
    sub.add_parser("start").add_argument("id")
    f = sub.add_parser("fail"); f.add_argument("id"); f.add_argument("--reason", required=True)
    a = sub.add_parser("accept"); a.add_argument("id"); a.add_argument("--branch", required=True)
    sub.add_parser("vc-check").add_argument("ms")
    d = sub.add_parser("dispatch-check"); d.add_argument("id"); d.add_argument("agent")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        s = status()
        print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else
              f"current={s['current_milestone']} state={s['state']} ready={s['ready']} "
              f"in_progress={s['in_progress']} blocked={list(s['blocked'])}\n"
              + "".join(f"  vc: {p}\n" for p in s["vc_problems"])
              + "".join(f"  invalid: {e}\n" for e in s["validation_errors"]))
        return 0
    if args.cmd == "validate":
        errs = validate()
        print("\n".join(errs) or "ok")
        return 1 if errs else 0
    if args.cmd == "ready":
        print("\n".join(f"{t.id}\t{t.agent}\t{t.title}" for t in ready()) or "(none)")
        return 0
    if args.cmd == "render":
        render()
        print("CHECKLIST.md rendered")
        return 0
    if args.cmd == "start":
        print(start(args.id))
        render()
        return 0
    if args.cmd == "fail":
        print(fail(args.id, args.reason))
        render()
        return 0
    if args.cmd == "accept":
        ok, msg = accept(args.id, args.branch)
        print(msg)
        render()
        return 0 if ok else 1
    if args.cmd == "vc-check":
        probs = vc_problems(args.ms)
        print("\n".join(probs) or "ok")
        return 1 if probs else 0
    if args.cmd == "dispatch-check":
        ok, msg = dispatch_check(args.id, args.agent)
        print(msg)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
