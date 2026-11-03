#!/usr/bin/env python3
"""Generate docs/progress.html (function inventory + branch status) and docs/branch-log.md.

Why generated (ADR-015): a hand-maintained progress file drifts from the code and costs agent
tokens every round; this script derives everything from sources that are already authoritative
— the AST of rlsentry/**, the accept ledger (git first-parent history), logs/events.jsonl and
the branch list — so re-running it is the verification. It only reads; it writes the two docs.

Run: python3 docs/tools/progress.py      (architect: at every milestone close, after every
high-risk ticket is accepted, and before every pause for the human; then commit the outputs)
"""
from __future__ import annotations

import ast
import html
import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
T = importlib.import_module("tickets")   # frozen harness, used read-only

PROTECTED = ("main", "rlsentry-approvals", "rlsentry-holdout")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout.strip()


def events() -> list[dict]:
    p = ROOT / "logs" / "events.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# --- (A) function inventory ------------------------------------------------------------

def _sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    pre = "async " if isinstance(fn, ast.AsyncFunctionDef) else ""
    return f"{pre}{fn.name}({ast.unparse(fn.args)}){ret}"


def _purpose(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.strip().split("\n\n")[0].replace("\n", " ") if doc else "（無 docstring）"


def _introduced_by(evs: list[dict]) -> dict[str, str]:
    """File path → first ticket whose accept event listed it."""
    out: dict[str, str] = {}
    for e in evs:
        if e.get("kind") == "ticket_accepted":
            for f in e.get("files", []):
                out.setdefault(f, e["ticket"])
    return out


def inventory(evs: list[dict]) -> list[dict]:
    intro = _introduced_by(evs)
    tests = {p: p.read_text(encoding="utf-8") for p in (ROOT / "tests").rglob("test_*.py")}
    rows = []
    for py in sorted((ROOT / "rlsentry").rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        mod = rel[:-3].replace("/", ".")
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                members = [n.target.id for n in node.body
                           if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
                methods = [_sig(n) for n in node.body
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and (not n.name.startswith("_") or n.name == "__call__")]
                struct = f"class {node.name}({bases})"
                if members:
                    struct += "；欄位：" + ", ".join(members)
                if methods:
                    struct += "；方法：" + "；".join(methods)
                kind = "class"
            else:
                struct, kind = _sig(node), "function"
            covered = sorted(p.relative_to(ROOT).as_posix() for p, src in tests.items()
                             if mod in src and node.name in src)
            rows.append({"module": mod, "name": node.name, "kind": kind, "line": node.lineno,
                         "layer": "合約" if ".contracts." in mod else "實作",
                         "struct": struct, "purpose": _purpose(node),
                         "ticket": intro.get(rel, "—"), "tests": covered, "path": rel})
    return rows


# --- (B) branches ------------------------------------------------------------------------

def branches(evs: list[dict]) -> list[dict]:
    head = git("rev-parse", "HEAD")
    current = git("branch", "--show-current")
    tips = {}   # branch tip sha → ticket, from accept merge messages
    for e in T.ledger():
        body = git("log", "-1", "--format=%B", e["commit"])
        for line in body.splitlines():
            if line.startswith("RLSentry-Branch-Tip:"):
                tips[line.split(":", 1)[1].strip()] = (e["ticket"], e["commit"])
    status = {t.id: T.effective_status(t, T.accepted()) for t in T.load_tickets().values()}
    out = []
    refs = git("for-each-ref", "--format=%(refname:short)|%(objectname)|%(committerdate:short)",
               "refs/heads", "refs/remotes/origin").splitlines()
    seen: set[str] = set()
    for ref in refs:
        name, sha, date = ref.split("|")
        short = name.removeprefix("origin/")
        if short in seen or short == "HEAD" or name == "origin":
            continue
        seen.add(short)
        merged = subprocess.run(["git", "merge-base", "--is-ancestor", sha, head], cwd=ROOT,
                                check=False).returncode == 0
        if short in PROTECTED:
            cat, note = "受保護", {"main": "只由人類 merge（session 分支 → main）",
                                "rlsentry-approvals": "人類 SSH 簽章核准，architect 不可寫",
                                "rlsentry-holdout": "holdout 測試，由 harness 寫入"}[short]
            if short == "main":
                ahead = git("rev-list", "--count", f"{sha}..{head}")
                note += f"；session 分支領先 {ahead} 個 commit，等待你 merge"
        elif short == current or short.startswith("claude/"):
            cat = "active" if short == current else "其他 session"
            note = "目前的 session 分支（ticket 經 accept 合併到這裡）" if short == current else ""
        elif short.startswith("review/"):
            cat, note = "review-only", "高風險 ticket 的審查分支，永不合併（ADR-005）"
        else:
            tid, mc = tips.get(sha, (None, None))
            if tid:
                cat, note = "finished", f"{tid} 已驗收，合併於 {mc[:9]}"
            elif merged:
                cat, note = "finished", "已包含在 session 分支中"
            else:
                tk = next((t for t in status if short.endswith(t) or f"/{t}" in short), None)
                live = tk and status[tk] == "in_progress"
                cat = "active" if live else "未合併"
                note = f"{tk} 進行中" if live else "未被驗收（例如失敗的嘗試）；可刪除"
        out.append({"name": short, "sha": sha[:9], "date": date, "cat": cat, "note": note})
    order = {"active": 0, "受保護": 1, "review-only": 2, "finished": 3, "未合併": 4, "其他 session": 5}
    return sorted(out, key=lambda b: (order.get(b["cat"], 9), b["name"]))


def branch_log(evs: list[dict]) -> str:
    rows = ["# 分支紀錄（自動產生，請勿手改；`python3 docs/tools/progress.py`）", "",
            ("來源：logs/events.jsonl（只增不改）與 git。合併方向一律是 ticket 分支 → session 分支"
             "（`tickets.py accept`）；session 分支 → main 只由人類 merge。"), "",
            "| 時間 | ticket | 動作 | 分支／commit | 說明 |", "| --- | --- | --- | --- | --- |"]
    for e in evs:
        k = e.get("kind")
        if k == "ticket_start":
            rows.append(f"| {e['ts']} | {e['ticket']} | 開始（第 {e.get('attempt')} 次） | "
                        f"{e.get('agent')} | 建立 ticket 分支 |")
        elif k == "ticket_accepted":
            rows.append(f"| {e['ts']} | {e['ticket']} | 驗收並合併 | {e['commit'][:9]} | "
                        f"ticket 分支 → session 分支 |")
        elif k == "ticket_fail":
            reason = str(e.get("reason", "")).splitlines()[0][:80].replace("|", "/")
            rows.append(f"| {e['ts']} | {e['ticket']} | 驗收失敗 | — | {reason} |")
    return "\n".join(rows) + "\n"


# --- render ------------------------------------------------------------------------------

CSS = ("body{font-family:system-ui,sans-serif;margin:2rem;max-width:1200px}"
       "table{border-collapse:collapse;width:100%;margin:1rem 0}td,th{border:1px solid #ccc;"
       "padding:4px 6px;vertical-align:top;font-size:13px}th{background:#f3f3f3}"
       "code{font-size:12px}.c-active{background:#e6ffed}.c-未合併{background:#fff5e6}")


def render(fns: list[dict], brs: list[dict]) -> str:
    e = html.escape
    st = T.status()
    last = T.ledger()[-1]["commit"][:9] if T.ledger() else "—"
    ms = "".join(f"<tr><td>{e(m)}</td><td>{e(s)}</td></tr>" for m, s in st["milestones"].items())
    fn_rows = "".join(
        f"<tr><td>{e(r['layer'])}</td><td><code>{e(r['module'])}</code></td><td>{e(r['kind'])}</td>"
        f"<td><code>{e(r['struct'])}</code><br><small>{e(r['path'])}:{r['line']}</small></td>"
        f"<td>{e(r['purpose'])}</td><td>{e(r['ticket'])}</td>"
        f"<td>{'<br>'.join(e(t) for t in r['tests']) or '—'}</td></tr>" for r in fns)
    br_rows = "".join(
        f"<tr class='c-{e(b['cat'])}'><td>{e(b['cat'])}</td><td><code>{e(b['name'])}</code></td>"
        f"<td>{e(b['sha'])}</td><td>{e(b['date'])}</td><td>{e(b['note'])}</td></tr>" for b in brs)
    n_impl = sum(r["layer"] == "實作" for r in fns)
    return f"""<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>RLSentry 進度</title><style>{CSS}</style>
<h1>RLSentry 進度</h1>
<p>自動產生（ADR-015），請勿手改。依據：最後一個 accept commit <code>{last}</code>；
目前 milestone <b>{e(str(st['current_milestone']))}</b>，狀態 <b>{e(st['state'])}</b>；
進行中 ticket：{e(', '.join(st['in_progress']) or '無')}。分支紀錄見 docs/branch-log.md。</p>
<h2>Milestone</h2><table><tr><th>MS</th><th>狀態</th></tr>{ms}</table>
<h2>(A) 已完成的函式與類別（合約 {len(fns) - n_impl}、實作 {n_impl}）</h2>
<p>「目的」取自 docstring 第一段；「加入於」是第一次把該檔案驗收進來的 ticket。</p>
<table><tr><th>層</th><th>模組</th><th>種類</th><th>結構</th><th>目的</th><th>加入於</th><th>涵蓋的測試</th></tr>
{fn_rows}</table>
<h2>(B) 分支現況</h2>
<p>合併方向：ticket 分支（<code>arch/T-xxx</code>、<code>worktree-agent-*</code>）→ 經
<code>tickets.py accept</code> → session 分支；session 分支 → <code>main</code> 只由人類 merge。</p>
<table><tr><th>類別</th><th>分支</th><th>tip</th><th>日期</th><th>說明</th></tr>{br_rows}</table>
</html>
"""


def main() -> int:
    evs = events()
    (ROOT / "docs" / "progress.html").write_text(render(inventory(evs), branches(evs)), encoding="utf-8")
    (ROOT / "docs" / "branch-log.md").write_text(branch_log(evs), encoding="utf-8")
    print("wrote docs/progress.html and docs/branch-log.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
