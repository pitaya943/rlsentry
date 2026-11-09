# MS3 高風險 ticket 審查說明（ADR-005 補記：分級＋合併）

本 milestone 以 worktree accept 合併（未另推 `review/T-xxx` 分支）。要看單張 diff，對其 accept merge commit 執行
`git show <sha>` 或 `https://github.com/pitaya943/rlsentry/compare/<sha>~1...<sha>`。

## 清單與預估閱讀時間（約 45 分鐘）
**逐張審查**（第 2 類：寫入／非 GET；第 4 類：判定）：
- T-127 `probe/write.py`（plan_writes、seed_work_row、send_write、read_back、after_filter），約 10 分鐘 — 334414c
- T-128 `probe/verdict.py`＋`diff.py`＋`cleanup.py`＋`rules/severity.py`（三態判定、清理、規則），約 10 分鐘 — ab9d318
- T-130 `probe/run.py`（串接：seed→plan→work row→write→read_back→verdict→cleanup），約 10 分鐘 — 1436632
- T-137 `probe/verdict.py`（write_cell 依 HTTP 狀態分類），約 4 分鐘 — 522926e
- T-126 `probe/seed.py`（canary 植入），約 4 分鐘 — fe87da6
- T-129 `probe/metadata.py`（L03 提權；MS3 未串接，延後 MS6），約 3 分鐘 — e00e9e8

**建議抽查**（合約，第 4／6 類）：
- ADR-029 合約與修訂：T-123 ead52cc、T-132（work row）、T-133（text_column）、T-135 b8f16d9（狀態分類）、T-139 22de6ab（只對 table）
- T-140 24b3473：NFR-01 流量證據測試

MS3 沒有第 1 類（safety 未動）與第 5 類（無新情境；變異測試 SQL 見 test_write_mutations.py）的程式變更。

## 重點
- **寫入只對 localhost／lab、只在 dev／ci**：所有寫入經 `SafeClient.request` → `require_write_allowed`（MS1，未變）。audit 的寫入路徑整段跳過（run.py），RPC 路徑一律拒絕。
- **只動自己植入的 canary**：每個破壞性探測各自新植入 work row（ADR-029 補記），讀回後清理；刪不掉回報 CLEANUP_FAILED。seed.sql 既有列永不被動到（T-140 以直接讀 DB 證明）。
- **判定保守**：2xx 但讀回未變＝denied；INSERT 非授權失敗（400 等）＝inconclusive，絕不誤報為安全（T-135／T-137）。
