# MS4 高風險 ticket 審查說明（ADR-005 補記：分級＋合併）

本 milestone 以 worktree accept 合併（未另推 `review/T-xxx` 分支）。要看單張 diff：`git show <sha>`，或 `https://github.com/pitaya943/rlsentry/compare/<sha>~1...<sha>`（`<sha>` 換成下表的 accept commit）。

## 清單與預估閱讀時間（約 50 分鐘）
**逐張審查**（第 2 類：DB 連線／寫入 body；第 4 類：什麼算漏洞、計分）：
- T-160 `whitebox/db.py`＋`splinter.py`（唯讀連線、雜湊鎖定、`set_config('pgrst.db_schemas', %s, true)`），約 6 分鐘 — 58f883a
- T-161 `whitebox/policies.py`（唯讀讀 pg_policies），約 3 分鐘 — c31e9a4
- T-162 `whitebox/correlate.py`＋`run.py`（confirmed／probe_only／lint_only、SECURITY DEFINER 只給 warning），約 8 分鐘 — 13433de
- T-163 `bench/score.py`（TP／FP／FN／TN、coverage、0/0、probe_only），約 10 分鐘 — 3172431
- T-167 `probe/fill.py`＋`seed.py`＋`write.py`（必填欄位填值；無法填就不送），約 6 分鐘 — 78e5c6d
- T-172 `probe/run.py` 的 `pick_text_column`（依型別挑文字欄位，修 L05），約 3 分鐘 — 9f2d872
- T-176 `probe/write.py`（INSERT 的其他 uuid 欄位填攻擊者 id，稽核 P1-1），約 2 分鐘 — 93e0344

**建議抽查**：
- 合約與 ADR：T-151（ADR-032）0865d44、T-152（ADR-033）8717707、T-153（ADR-034）7902773、T-171 76e82c7、T-173 eed1aa4、T-175 9cb48af
- T-165 `bench/run.py`、`__main__.py` 1284d41；T-174（空 lint 也算量測、audit 也跑 M4）40de13e；T-164 `labctl.apply_synthetic` b2aa5ba；T-166 `discovery/openapi.py` 610111b
- 第 5 類（ground truth）：T-170 b4a8bdc 只改 16 個 `splinter_expected`，請抽查 L02、L07、L12 三個（實測依據見 BENCHMARK_REPORT.md §3，`tests/lab/test_splinter_expected.py` 逐情境重測）。

MS4 沒有第 1 類（safety 未動）的程式變更。

## 重點
- **M4 只讀**：連線帶 `default_transaction_read_only=on`＋psycopg `read_only=True`，每次 rollback、從不 commit；lab 測試以 SQLSTATE 25006 與 DB log 證明。
- **M4 不產生 confirmed**：correlate 只註記 M3 finding、新增 LINT_ONLY／SECURITY_DEFINER_EXECUTABLE（皆 vulnerability=False），所以 M4 無法改變 recall／precision／FPR。
- **SECURITY DEFINER**：L07 `get_all_accounts`（實測拿到他人列）→ confirmed；`ping_definer`（可執行但無資料）→ 只有 config_warning。
- **填值只有 canary／擁有者 id／常數**，型別不支援就整列不送（not_tested／inconclusive，不誤報為 denied）。
