"""Tests for the frozen harness. Run with `make harness-test` (Stage 0, step 1).

Each test builds a throwaway git repo and points the harness at it through environment
variables, so nothing touches the real project.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))


def sh(cmd: str, cwd: Path) -> str:
    return subprocess.run(cmd, shell=True, cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    (r / "docs" / "tickets").mkdir(parents=True)
    (r / "docs" / "verification").mkdir(parents=True)
    (r / "rlsentry").mkdir()
    (r / "rlsentry" / "__init__.py").write_text("")
    (r / "tests").mkdir()
    (r / ".gitignore").write_text("logs/\nCHECKLIST.md\n")
    sh("git init -q -b main && git config user.email t@t && git config user.name t && "
       "git add -A && git commit -qm init", r)
    approvals = tmp_path / "approvals"
    approvals.mkdir()
    monkeypatch.setenv("RLSENTRY_ROOT", str(r))
    monkeypatch.setenv("RLSENTRY_APPROVALS", str(approvals))
    monkeypatch.setenv("RLSENTRY_HOLDOUT", str(tmp_path / "holdout"))
    monkeypatch.setenv("RLSENTRY_CHECK_CMD", "true")
    key = tmp_path / "key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    signers = tmp_path / "allowed_signers"
    signers.write_text(f'me@test namespaces="rlsentry-approval" {(tmp_path / "key.pub").read_text().strip()}\n')
    monkeypatch.setenv("RLSENTRY_ALLOWED_SIGNERS", str(signers))
    monkeypatch.setenv("RLSENTRY_KEY", str(key))
    monkeypatch.chdir(r)
    import common, tickets  # noqa: E401
    importlib.reload(common)
    importlib.reload(tickets)
    return r, approvals, tickets


def write_ticket(r: Path, tid: str, ms: str = "STAGE0", agent: str = "recon-dev", deps=(), paths=("rlsentry/toy.py",)):
    import common as C
    meta = {"id": tid, "title": f"title {tid}", "milestone": ms, "agent": agent, "depends_on": list(deps),
            "allowed_paths": list(paths), "tests": [], "status": "todo", "attempts": 0,
            "blocked_reason": None, "origin": "plan"}
    (r / "docs" / "tickets" / f"{tid}.md").write_text(C.dump_frontmatter(meta, "body"))
    # The architect commits its plan to main; branches then only carry implementation files.
    sh(f"git add docs/tickets/{tid}.md && git commit -qm 'plan {tid}'", r)


def make_branch(r: Path, name: str, files: dict[str, str]) -> None:
    sh(f"git switch -q -c {name}", r)
    for f, content in files.items():
        (r / f).parent.mkdir(parents=True, exist_ok=True)
        (r / f).write_text(content)
    sh("git add " + " ".join(files) + " && git commit -qm work && git switch -q main", r)


def write_vc(r: Path, ms: str, commit: str, version: int = 1, items: int = 2) -> Path:
    body = "\n".join(f"- [ ] item {i}" for i in range(items))
    p = r / "docs" / "verification" / f"{ms}-v{version}.md"
    p.write_text(f"# {ms} 驗證清單 v{version}（main @ {commit[:9]}）\n\n## 3. 請你親手驗證\n"
                 f"- [ ] 執行 `make verify-milestone MS={ms}`\n{body}\n")
    return p


def approve(approvals: Path, ms: str, vc: Path, decision: str = "approve", sign: bool = True) -> None:
    import common as C
    y = approvals / f"{ms}.yaml"
    y.write_text(f"milestone: {ms}\nchecklist_sha256: {C.sha256_file(vc)}\ndecision: {decision}\nnotes: |\n  ok\n")
    (approvals / f"{ms}.yaml.sig").unlink(missing_ok=True)
    if sign:
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", os.environ["RLSENTRY_KEY"], "-n", "rlsentry-approval",
                        str(y)], check=True, capture_output=True)
    else:
        (approvals / f"{ms}.yaml.sig").write_text("-----BEGIN SSH SIGNATURE-----\nforged\n-----END SSH SIGNATURE-----\n")


def accept_one(r: Path, T, tid: str = "T-001") -> str:
    T.start(tid)
    make_branch(r, f"b-{tid}", {"rlsentry/toy.py": "x = 1\n"})
    ok, msg = T.accept(tid, f"b-{tid}")
    assert ok, msg
    return T.accepted()[tid]   # the accept merge (a state-sync commit may follow it)


# --- path matching ------------------------------------------------------------

def test_path_matches_handles_dot_dirs_and_globs():
    import common as C
    assert C.path_matches(".claude/settings.json", C.HARNESS_PROTECTED)
    assert C.path_matches("./harness/tickets.py", C.HARNESS_PROTECTED)
    assert C.path_matches("rlsentry/pkg/__init__.py", ["**/__init__.py"])
    assert C.path_matches("tests/m3/test_x.py", ["tests/**"])
    assert not C.path_matches("rlsentry/core/probe.py", C.SUBAGENT_PROTECTED)


# --- validation -------------------------------------------------------------

def test_validate_catches_bad_plans(repo):
    r, _, T = repo
    write_ticket(r, "T-001", deps=["T-404"])
    write_ticket(r, "T-002", deps=["T-003"], paths=["rlsentry/a.py"])
    write_ticket(r, "T-003", deps=["T-002"], paths=["rlsentry/b.py"])
    write_ticket(r, "T-004", paths=["harness/tickets.py"])
    write_ticket(r, "T-005", paths=["tests/test_x.py"])
    write_ticket(r, "T-006", ms="STAGE0", deps=["T-007"], paths=["rlsentry/c.py"])
    write_ticket(r, "T-007", ms="MS1", paths=["rlsentry/d.py"])
    errs = "\n".join(T.validate())
    assert "missing ticket T-404" in errs
    assert "cycle" in errs
    assert "harness-protected" in errs
    assert "not writable by subagents" in errs
    assert "later milestone" in errs


# --- scheduling and acceptance ----------------------------------------------

def test_only_first_milestone_is_unlocked(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    write_ticket(r, "T-101", ms="MS0", paths=["rlsentry/other.py"])
    assert T.current_milestone() == "STAGE0"
    assert [t.id for t in T.ready()] == ["T-001"]
    assert T.milestone_state("MS0") == "locked"


def test_accept_merges_and_records_ledger(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    commit = accept_one(r, T)
    assert (r / "rlsentry" / "toy.py").exists()
    assert T.accepted() == {"T-001": commit}


def test_out_of_scope_change_is_rejected_and_counted(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    T.start("T-001")
    make_branch(r, "b1", {"rlsentry/toy.py": "x = 1\n", "rlsentry/sneaky.py": "y = 2\n"})
    ok, msg = T.accept("T-001", "b1")
    assert not ok and "outside allowed_paths" in msg
    assert not (r / "rlsentry" / "toy.py").exists()
    assert T.load_tickets()["T-001"].attempts == 1


def test_cheat_patterns_are_rejected(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    T.start("T-001")
    make_branch(r, "b1", {"rlsentry/toy.py": "x = 1  # type: ignore\n"})
    ok, msg = T.accept("T-001", "b1")
    assert not ok and "forbidden patterns" in msg


def test_failing_checks_abort_the_merge(repo, monkeypatch):
    r, _, T = repo
    monkeypatch.setenv("RLSENTRY_CHECK_CMD", "false")
    write_ticket(r, "T-001")
    T.start("T-001")
    make_branch(r, "b1", {"rlsentry/toy.py": "x = 1\n"})
    ok, msg = T.accept("T-001", "b1")
    assert not ok and "checks failed" in msg
    assert not (r / "rlsentry" / "toy.py").exists()
    assert sh("git status --porcelain rlsentry", r).strip() == ""   # ticket bookkeeping may be dirty


def test_self_declared_done_is_ignored(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    t = T.load_tickets()["T-001"]
    t.status = "done"
    t.save()
    assert T.effective_status(T.load_tickets()["T-001"], T.accepted()) == "todo"


def test_dependencies_gate_readiness_and_conflicts_serialise(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    write_ticket(r, "T-002", deps=["T-001"], paths=["rlsentry/b.py"])
    write_ticket(r, "T-003", paths=["rlsentry/toy.py"])   # same file as T-001
    ids = [t.id for t in T.ready()]
    assert "T-002" not in ids
    assert len({"T-001", "T-003"} & set(ids)) == 1


def test_five_failures_block_ticket_and_dependents(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    write_ticket(r, "T-002", deps=["T-001"], paths=["rlsentry/b.py"])
    for _ in range(T.MAX_ATTEMPTS):
        T.start("T-001")
        T.fail("T-001", "nope")
    ts = T.load_tickets()
    assert ts["T-001"].status == "blocked"
    assert ts["T-002"].status == "blocked" and "T-001" in ts["T-002"].blocked_reason


# --- milestone gate ---------------------------------------------------------

def test_full_gate_cycle(repo):
    r, approvals, T = repo
    write_ticket(r, "T-001")
    write_ticket(r, "T-101", ms="MS0", agent="architect", paths=["docs/x.md"])
    commit = accept_one(r, T)
    assert T.milestone_state("STAGE0") == "active"           # no checklist yet
    vc = write_vc(r, "STAGE0", commit)
    assert T.vc_problems("STAGE0") == []
    assert T.milestone_state("STAGE0") == "awaiting_human"
    assert T.ready() == []                                  # nothing dispatchable while paused
    approve(approvals, "STAGE0", vc, sign=False)
    assert T.milestone_state("STAGE0") == "awaiting_human"  # a forged signature is not an approval
    approve(approvals, "STAGE0", vc)
    assert T.milestone_state("STAGE0") == "approved"
    assert T.current_milestone() == "MS0"
    assert [t.id for t in T.ready()] == ["T-101"]
    vc.write_text(vc.read_text() + "\n- [ ] sneaky edit\n")     # editing the checklist voids approval
    assert T.milestone_state("STAGE0") == "awaiting_human"


def test_changes_requested_reopens_work(repo):
    r, approvals, T = repo
    write_ticket(r, "T-001")
    commit = accept_one(r, T)
    vc = write_vc(r, "STAGE0", commit)
    approve(approvals, "STAGE0", vc, decision="changes_requested")
    assert T.milestone_state("STAGE0") == "changes_requested"
    write_ticket(r, "T-002", paths=["rlsentry/b.py"])
    assert [t.id for t in T.ready()] == ["T-002"]


def test_reopen_relocks_later_milestones(repo):
    r, approvals, T = repo
    write_ticket(r, "T-001")
    commit = accept_one(r, T)
    approve(approvals, "STAGE0", write_vc(r, "STAGE0", commit))
    assert T.current_milestone() == "MS0"
    write_ticket(r, "T-009", paths=["rlsentry/fix.py"])   # reopen ticket in the approved milestone
    assert T.milestone_state("STAGE0") == "active"
    assert T.milestone_state("MS0") == "locked"
    T.start("T-009")
    make_branch(r, "fix", {"rlsentry/fix.py": "z = 3\n"})
    assert T.accept("T-009", "fix")[0]
    # old checklist names an older commit, so the milestone needs a fresh review
    assert any("not the milestone's last accepted commit" in p for p in T.vc_problems("STAGE0"))


def test_checklist_item_limit_and_mandatory_item(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    commit = accept_one(r, T)
    p = write_vc(r, "STAGE0", commit, items=20)
    assert any("items" in x for x in T.vc_problems("STAGE0"))
    p.write_text(p.read_text().replace("make verify-milestone MS=STAGE0", "trust me"))
    assert any("mandatory" in x for x in T.vc_problems("STAGE0"))


# --- dispatch gate ----------------------------------------------------------

def test_dispatch_gate(repo):
    r, _, T = repo
    import gate_dispatch as G
    importlib.reload(G)
    write_ticket(r, "T-001")
    ev = lambda agent, prompt: {"tool_input": {"subagent_type": agent, "prompt": prompt}}  # noqa: E731
    assert "not allowed" in G.check(ev("general-purpose", "do stuff"))
    assert "Ticket:" in G.check(ev("recon-dev", "please work"))
    assert "start" in G.check(ev("recon-dev", "Ticket: T-001\n..."))    # not started yet
    T.start("T-001")
    assert G.check(ev("recon-dev", "Ticket: T-001\n...")) is None
    assert "belongs to" in G.check(ev("probe-dev", "Ticket: T-001\n..."))
    assert G.check(ev("auditor", "Review: STAGE0")) is None
    assert "Review" in G.check(ev("auditor", "look around"))


# --- path guard -------------------------------------------------------------

def test_guard_rules(repo):
    r, approvals, _ = repo
    import guard_paths as G
    importlib.reload(G)
    W = lambda path: {"tool_name": "Write", "tool_input": {"file_path": str(r / path)}, "cwd": str(r)}  # noqa: E731
    B = lambda cmd: {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(r)}  # noqa: E731
    assert G.check(W("harness/tickets.py"), "global", None)                 # nobody edits the harness
    assert G.check(W(".claude/settings.json"), "global", None)
    assert G.check(W("tests/test_a.py"), "global", None) is None            # architect may write tests
    assert G.check(W("tests/test_a.py"), "subagent", "probe-dev")           # implementers may not
    assert G.check(W("rlsentry/core/probe.py"), "subagent", "probe-dev") is None
    assert G.check(W("rlsentry/core/probe.py"), "subagent", "auditor")      # auditor is read-only
    assert G.check(B("echo hi >> harness/tickets.py"), "global", None)
    assert G.check(B("python3 harness/tickets.py status > /tmp/s.txt"), "global", None) is None
    assert G.check(B("git merge feature"), "global", None)
    assert G.check(B("git push -u origin HEAD"), "global", None) is None   # cloud sessions must push work
    assert G.check(B("git push --force origin main"), "global", None)
    assert G.check(B("git push origin HEAD:rlsentry-approvals"), "global", None)
    assert G.check(B("git tag -f harness-frozen"), "global", None)
    assert G.check(B("sed -i 's/a/b/' tests/test_a.py"), "subagent", "probe-dev")
    assert G.check(B("pytest -q tests/m3"), "subagent", "probe-dev") is None
    hold = str(Path(os.environ["RLSENTRY_HOLDOUT"]) / "MS1" / "test_x.py")
    assert G.check({"tool_name": "Read", "tool_input": {"file_path": hold}}, "subagent", "probe-dev")
    assert G.check({"tool_name": "Read", "tool_input": {"file_path": hold}}, "global", None) is None
    assert G.check(W(str(approvals / "MS1.yaml")), "global", None)
    # agent identity from the payload applies subagent rules even in global mode
    ev = W("tests/test_a.py") | {"agent_type": "recon-dev"}
    assert G.check(ev, "global", None)


# --- stop gate --------------------------------------------------------------

def run_hook(script: str, payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HARNESS / script)], input=json.dumps(payload),
                          capture_output=True, text=True, env={**os.environ, **env})


def test_stop_gate(repo):
    r, approvals, T = repo
    write_ticket(r, "T-001")
    res = run_hook("can_stop.py", {}, {})
    assert res.returncode == 2 and "T-001" in res.stderr
    commit = accept_one(r, T)
    write_vc(r, "STAGE0", commit)
    assert run_hook("can_stop.py", {}, {}).returncode == 0     # paused for the human
    assert (r / "CHECKLIST.md").exists()


def test_stop_budget(repo):
    r, _, T = repo
    write_ticket(r, "T-001")
    (r / "logs").mkdir(exist_ok=True)
    (r / "logs" / "stop_attempts.json").write_text(json.dumps({"count": 30}))
    assert run_hook("can_stop.py", {}, {}).returncode == 0
    assert (r / "logs" / "INCOMPLETE.md").exists()


# --- host approval script ---------------------------------------------------

def test_host_approve_script_signs_into_branch(repo, monkeypatch):
    r, approvals, T = repo
    monkeypatch.delenv("RLSENTRY_APPROVALS")                # cloud mode: approvals come from a git ref
    monkeypatch.setenv("RLSENTRY_APPROVALS_REF", "rlsentry-approvals")
    write_ticket(r, "T-001")
    sh("git tag harness-frozen", r)
    commit = accept_one(r, T)
    write_vc(r, "STAGE0", commit)
    sh("git add -A && git commit -qm vc", r)
    args = [sys.executable, str(HARNESS.parent / "host" / "approve.py"), "--repo", str(r), "--ms", "STAGE0",
            "--key", os.environ["RLSENTRY_KEY"], "--decision", "approve", "--reviewer", "me",
            "--notes", "looks good", "--yes", "--no-push"]
    subprocess.run(args, check=True, capture_output=True)
    assert T.milestone_state("STAGE0") == "approved"
    # tampering with a frozen path makes the script refuse to sign
    (r / "Makefile").write_text("tampered\n")
    sh("git add Makefile && git commit -qm tamper", r)
    res = subprocess.run(args, capture_output=True, text=True)
    assert res.returncode == 1 and "REFUSING" in res.stdout


# --- provenance -------------------------------------------------------------

def test_provenance_flags_direct_commits(repo):
    r, _, T = repo
    import acceptance as A
    importlib.reload(A)
    write_ticket(r, "T-001")
    accept_one(r, T)
    assert A.check_provenance()[0]
    (r / "rlsentry" / "direct.py").write_text("bad = True\n")
    (r / "rlsentry" / "contracts").mkdir()
    (r / "rlsentry" / "contracts" / "models.py").write_text("ok = True\n")
    sh("git add -A && git commit -qm direct", r)
    ok, detail = A.check_provenance()
    assert not ok and "rlsentry/direct.py" in detail and "contracts" not in detail


def test_provenance_rejects_forged_trailer(repo):
    r, _, T = repo
    import acceptance as A
    importlib.reload(A)
    write_ticket(r, "T-001")
    (r / "rlsentry" / "toy.py").write_text("x = 1\n")
    sh("git add -A && git commit -qm 'accept T-001: fake' -m 'RLSentry-Accepted: T-001'", r)
    assert "T-001" in T.accepted()                    # the ledger believes it ...
    ok, detail = A.check_provenance()
    assert not ok and "not a merge commit" in detail  # ... but verification does not


def test_verify_milestone_end_to_end(repo):
    r, approvals, T = repo
    write_ticket(r, "T-001")
    commit = accept_one(r, T)
    res = run_hook("acceptance.py", {}, {})  # no args -> argparse error, sanity check of entrypoint
    assert res.returncode != 0
    pre = subprocess.run([sys.executable, str(HARNESS / "acceptance.py"), "--milestone", "STAGE0", "--no-vc"],
                         capture_output=True, text=True)
    assert pre.returncode == 0, pre.stdout
    full = subprocess.run([sys.executable, str(HARNESS / "acceptance.py"), "--milestone", "STAGE0"],
                          capture_output=True, text=True)
    assert full.returncode == 1 and "no verification checklist" in full.stdout
    write_vc(r, "STAGE0", commit)
    full = subprocess.run([sys.executable, str(HARNESS / "acceptance.py"), "--milestone", "STAGE0"],
                          capture_output=True, text=True)
    assert full.returncode == 0, full.stdout


def test_stage0_toy_ticket_with_real_make_check(repo, monkeypatch):
    """The real Stage 0 ticket, accepted through the real Makefile `check` target."""
    r, approvals, T = repo
    import shutil
    monkeypatch.delenv("RLSENTRY_CHECK_CMD")
    project = HARNESS.parent
    shutil.copy(project / "Makefile", r / "Makefile")
    shutil.copytree(project / "tests" / "toy", r / "tests" / "toy")
    (r / "tests" / "__init__.py").write_text("")
    shutil.copy(project / "docs" / "tickets" / "T-000.md", r / "docs" / "tickets" / "T-000.md")
    sh("git add -A && git commit -qm 'frozen harness files'", r)
    assert T.validate() == []
    T.start("T-000")
    make_branch(r, "toy-bad", {"rlsentry/toy.py": "def add(a, b):\n    return a - b\n"})
    ok, msg = T.accept("T-000", "toy-bad")
    assert not ok and "checks failed" in msg            # wrong implementation is rejected
    T.start("T-000")
    make_branch(r, "toy-good", {"rlsentry/toy.py": "def add(a: int, b: int) -> int:\n    return a + b\n"})
    ok, msg = T.accept("T-000", "toy-good")
    assert ok, msg
    assert T.regression_tests() == ["tests/toy/test_add.py"]


# --- Stage 0 findings: identity via linked worktree, holdout on a separate branch -----------

def test_global_guard_identifies_subagents_by_worktree(repo, tmp_path):
    r, _, _ = repo
    import guard_paths as G
    importlib.reload(G)
    wt = tmp_path / "wt"
    sh(f"git worktree add -q -b sub-work {wt}", r)
    def W(path, cwd):
        return {"tool_name": "Write", "tool_input": {"file_path": str(Path(cwd) / path)}, "cwd": str(cwd)}
    # same file, same global hook: allowed for the architect (main checkout), blocked in a worktree
    assert G.check(W("docs/canary.md", r), "global", None) is None
    assert G.check(W("docs/canary.md", wt), "global", None)
    assert G.check(W("tests/test_x.py", wt), "global", None)
    assert G.check(W("rlsentry/core/x.py", wt), "global", None) is None
    # holdout material by any route
    assert G.check({"tool_name": "Read", "tool_input": {"file_path": str(wt / ".holdout/STAGE0/t.py")},
                    "cwd": str(wt)}, "global", None)
    assert G.check({"tool_name": "Glob", "tool_input": {"pattern": "**/*holdout*"}, "cwd": str(wt)},
                   "global", None)
    assert G.check({"tool_name": "Bash", "tool_input": {"command": "git show rlsentry-holdout:STAGE0/t.py"},
                    "cwd": str(wt)}, "global", None)
    assert G.check({"tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "cwd": str(wt)},
                   "global", None) is None


def test_holdout_branch_never_touches_worktrees(repo, tmp_path):
    r, _, T = repo
    import holdout as H
    import acceptance as A
    importlib.reload(H)
    importlib.reload(A)
    src = tmp_path / "holdout-src"
    src.mkdir()
    (src / "test_holdout.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    hashes = H.add("STAGE0", src)
    assert not src.exists()                                       # scratch copy removed
    assert hashes and hashes[0][0] == "STAGE0/test_holdout.py"
    assert sh("git status --porcelain", r).strip() == ""           # main working tree untouched
    assert not (r / ".holdout").exists()
    wt = tmp_path / "wt2"
    sh(f"git worktree add -q -b sub2 {wt} main", r)
    assert not list(wt.rglob("*holdout*"))                         # absent from subagent worktrees
    ok, detail = A.check_holdout("STAGE0")
    assert ok, detail
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "test_bad.py").write_text("def test_no():\n    assert False\n")
    H.add("MS0", bad)
    assert not A.check_holdout("MS0")[0]                           # failing holdout fails the check
    assert A.check_holdout("STAGE0")[0]                            # milestones are isolated


# --- token rules: enforced parts ----------------------------------------------------------

def test_dispatch_length_cap(repo):
    r, _, T = repo
    import gate_dispatch as G
    importlib.reload(G)
    write_ticket(r, "T-001")
    T.start("T-001")
    ev = lambda p: {"tool_input": {"subagent_type": "recon-dev", "prompt": p}}  # noqa: E731
    assert G.check(ev("Ticket: T-001\nRun sync, read docs/tickets/T-001.md")) is None
    assert "limit" in G.check(ev("Ticket: T-001\n" + "pasted ticket text " * 200))


def test_compact_failure_keeps_only_actionable_lines(repo):
    _, _, T = repo
    noisy = "\n".join(["collected 40 items", "." * 80] * 50 +
                      ["FAILED tests/m3/test_read.py::test_denied - assert 1 == 0",
                       "E       assert 1 == 0", "rlsentry/probe/read.py:12:5: F401 unused import"])
    out = T.compact_failure(noisy)
    assert "FAILED tests/m3/test_read.py::test_denied" in out and "F401" in out
    assert "collected 40 items" not in out and len(out) < 400


def test_spec_tool_returns_only_requested_parts(repo):
    r, _, _ = repo
    import spec as S
    importlib.reload(S)
    (r / "docs" / "SPEC.md").write_text(
        "# T\n## 3. 需求\n| 編號 | x |\n| FR-08 | cross tenant |\n| FR-09 | writes |\n"
        "## 5. 模組設計\n### M3 Probe\nprobe text\n### M4 Whitebox\nwb text\n## 8. Lab\nlab text\n")
    m3 = S.section("M3 Probe")
    assert "probe text" in m3 and "wb text" not in m3
    assert "lab text" in S.section("§8") and "probe text" not in S.section("§8")
    assert S.requirement_rows(["FR-08"]).count("\n") == 0 and "cross tenant" in S.requirement_rows(["FR-08"])

def test_spec_tool_ignores_hash_lines_inside_code_fences(repo):
    r, _, _ = repo
    import spec as S
    importlib.reload(S)
    (r / "docs" / "SPEC.md").write_text(
        "# T\n## 6. 設定\n```yaml\n# a yaml comment\nkey: 1\n```\ntail text\n## 7. Next\nx\n")
    s6 = S.section("6")
    assert "key: 1" in s6 and "tail text" in s6 and "Next" not in s6
    assert "a yaml comment" not in S.toc()


def test_sync_worktree_brings_subagent_to_architect_head(repo, tmp_path):
    r, _, _ = repo
    wt = tmp_path / "wt-sync"
    sh(f"git worktree add -q -b sub-sync {wt} main", r)
    (r / "rlsentry" / "contracts").mkdir(exist_ok=True)
    (r / "rlsentry" / "contracts" / "api.py").write_text("X = 1\n")
    sh("git add -A && git commit -qm 'architect contract'", r)   # architect moves ahead after the worktree exists
    head = sh("git rev-parse HEAD", r).strip()
    res = subprocess.run([sys.executable, str(HARNESS / "sync_worktree.py")], cwd=wt, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert sh("git rev-parse HEAD", wt).strip() == head
    assert (wt / "rlsentry" / "contracts" / "api.py").exists()
    res = subprocess.run([sys.executable, str(HARNESS / "sync_worktree.py")], cwd=r, capture_output=True, text=True)
    assert "main checkout" in res.stdout                            # no-op outside worktrees
