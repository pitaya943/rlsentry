# MS2 驗證清單 v1（main @ bd79ce026）

## 1. 本模組做了什麼
- ticket：18 張（T-090–T-093、T-100–T-113），全部 done，每張 1 次，沒有 blocked。
  - architect（5 張）：
    - T-090 合約
    - T-091 可見測試
    - T-093 變異測試與設計前提測試（ADR-022 #3）
    - T-111 lab 整合測試
    - T-112 稽核修正
  - probe-dev（11 張）：
    - discovery：openapi、bundle、merge＋discover
    - probe：session、evidence、cross_tenant、read、verdict、severity＋diff、run
    - `policy/init.py`
  - lab-dev（2 張）：
    - T-092：`labctl.execute`、唯讀的 `query`
    - T-113：`write_command` 與 flush sentinel
  - 第一批 ticket 依你的要求包含 ADR-022 第 3 點：
    - `labctl.execute`（T-092）
    - oracle 變異測試與設計前提測試（T-093）
    - holdout 變異版本：`MS2/test_holdout_lab_mutations.py`
- ADR：
  - **023**：讀取 cell 的判定。已知列是每位使用者自己的主鍵；只有「forbidden 已知列可見數 = 0，且回應是可信的 200／206」才算 denied，其餘一律 inconclusive。另外：
    - OpenAPI 無法區分 view 與 table
    - bundle 推測與 OpenAPI 取聯集
    - Discover／Probe 改以 SafeClient 作為第一個參數
  - **024**：DB log 寫入分類時排除引號內的內容。這修訂了 ADR-019，並變更 MS1 已核准的 labctl（見第 4 段）。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS2 --no-vc`：ALL PASSED。
  - 回歸測試、holdout（含 MS2 的 25 項）、safety、provenance、ruff、mypy 皆通過
  - mutation：略過
- lab 整合（`tests/lab/test_scan_reads.py`）：
  - 15 個情境以 audit 掃描，所有 audit SELECT case 都符合 ground truth
  - confirmed 誤報為 0
  - PostgREST 角色寫入為 0
  - GET 只下載主鍵
- auditor 分兩部分：
  - 第 1 部分（discovery、probe）：沒有 P0／P1
  - 第 2 部分（lab 與測試）：P1 ×1（F1）、P2 ×5
  - 全部在 T-112、T-113 處理，或列入第 5 段；見 `docs/verification/traceability.md` 的 MS2 段
  - 兩位 auditor 執行 pytest 都被 harness 擋下（「auditor is read-only」），所以執行面的結果只來自 acceptance。第 3 段第 6–8 項是它們要求人工確認的項目。
- 高風險審查分支：`docs/reviews/MS2-high-risk.md`。逐張：T-092、T-103、T-113；合併抽查：`review/MS2-probe`；合約：T-090。

## 3. 請你親手驗證（逐項打勾）
- [ ] 在容器內執行 `make verify-milestone MS=MS2`，並依 ADR-022 的三段信任鏈進行：
      (a) 在本機執行 `host/review.sh` 第 1、2 步（同步與防竄改）；
      (b) 以 `ref=claude/busy-darwin-asvox3` 觸發 GitHub Actions 的 `verify-milestone`；
      (c) 執行 `git diff --stat <本機 sha> <Actions sha> -- . ':!logs'`。
      預期：防竄改 diff 為空；Actions 最後一行為 `MS2: ALL PASSED`；(c) 沒有任何輸出。
- [ ] `python3 -m pytest -q tests/lab/test_scan_reads.py`（需 Docker）
      預期：`15 passed`。這是 MS2 的焦點：inconclusive 沒被當成安全、沒有下載資料、差分正確，全部在真實 lab 上驗證。
- [ ] 閱讀 `rlsentry/probe/verdict.py:29-53`（`read_cell`）
      確認：只有第 47–49 行（200／206、有總數、總數不超過查詢數）會產生 allowed 或 denied，其他路徑一律 inconclusive，known_rows_checked 為 0。
- [ ] 親手變異：把 `rlsentry/probe/verdict.py:47` 的 `(200, 206)` 改成 `(200, 206, 401, 403)`，再執行 `python3 -m pytest -q tests/probe/test_verdict.py`，最後用 `git restore` 還原。
      預期：`test_no_trustworthy_count_is_inconclusive_never_denied` 有參數失敗。把 401 當成 denied（也就是「安全」）的實作過不了測試。
- [ ] `python3 -m pytest -q tests/lab/test_design_assumptions.py -k "empty_table or volatile or stable"`
      預期：3 passed。這三項分別證明：
      - RLS 擋住的列與空表回應相同（`*/0`）
      - VOLATILE RPC 對 GET 回 405 且沒有寫入
      - STABLE RPC 內的 INSERT 被拒絕
      第 2、3 點說明了為什麼以 GET 呼叫 RPC 不會寫入（稽核 S1）。
- [ ] 確認稽核 F1（auditor 的手動項目 1）：先執行 `python3 -m pytest -q tests/lab/test_shared_execute.py::test_openapi_fetch_logs_no_write`，再執行 `docker logs --since 2m supabase_db_rlsentry-lab 2>&1 | grep -B1 "TRUNCATE 'quoted'"`。
      預期：這段文字只出現在 `DETAIL:  parameters:` 行。這就是為什麼字串移除改由 `tests/lab/test_shared_classify.py` 以純函式測試。
- [ ] `python3 -m pytest -q tests/lab/test_shared_classify.py tests/lab/test_shared_execute.py`（auditor 手動項目 2）
      預期：全部通過。其中 `"o'x"`、`$$it's$$` 之後的寫入仍能被抓到；`query()` 寫入時錯誤訊息含 `read-only transaction`。
- [ ] `python3 -m pytest -q -m safety tests/lab tests/probe`（auditor 手動項目 3）
      預期：全部通過；變異測試沒有出現 `oracle failed for another reason`。
- [ ] 閱讀 `lab/_shared/labctl.py:296-360`（`write_command`、`db_writes_since`）
      確認：分類只經過 `write_command`；sentinel 之後的記錄不會回傳。這是 NFR-01 的驗證工具，屬第 2 類逐張審查（T-113）。
- [ ] 閱讀 `rlsentry/probe/session.py` 中的 `login`（`review/T-103` 的 diff）
      確認：例外訊息只有狀態碼或例外類別名稱；只捕捉 `httpx.HTTPError`，所以 `WriteRefused` 不會被吞掉。
- [ ] `git show origin/rlsentry-holdout:MS2/test_holdout_lab_mutations.py | sha256sum`
      預期：`863087565b8c35f43163d188d103eeeb2083e076dee64b67509b70e20b340517`（與 PRODUCTION_LOG 派工前紀錄相同）。
- [ ] 開啟 `docs/system_overview.html`（ADR-021）
      確認：第 8 節「MS2 的過程」與第 2 節架構圖的狀態色和實際一致：M2 為綠色，M3 為綠色虛線（只有讀取）。
- [ ] 閱讀 ADR-024 的「為什麼不是 reopen MS1」，並**做出決定**：是否接受在 MS2 內修改 MS1 已核准的 `lab/_shared/labctl.py`。
      若你要求改走 reopen，請寫在核准意見中。

## 4. 與 SPEC 的偏差與假設
- **§5 M2「OpenAPI 關閉時改從 bundle 推測」**：實作在 OpenAPI 可用時也加入 bundle 推測到的目標，也就是兩者取聯集（ADR-023 #2）。
- **§5 M2 的 `kind: view`**：M2 不回報 view，因為 PostgREST 的 OpenAPI 無法區分 view 與 table（ADR-023 #1，已在 lab 實測）。
- **FR-05「報告列出覆蓋率並聲明未發現不代表安全」**：延到 MS6 的報告。MS2 只提供 `openapi_available` 與每個目標的 confidence。
- **FR-06「不下載資料內容」**：audit 的已知列會以 GET 下載主鍵值，每位使用者最多 50 筆。SPEC §5 M3 的「主鍵交集」需要這一步。
- **§5 M3 dev／ci 植入資料**：延到 MS3。MS2 在所有 profile 都使用主鍵交集，寫入 cell 一律為 not_tested。
- **介面變更**：`Discover`、`Probe` 以 SafeClient 作為第一個參數；sessions 改為 `Sessions` 模型（ADR-023 #5，修改既有合約，屬第 6 類）。
- **變更 MS1 已核准的程式**：`lab/_shared/labctl.py`（T-092、T-113）。新增 `execute`、唯讀 `query` 與 `write_command`，並修訂 ADR-019 的分類規則（ADR-024）。這是 MS2 流量暴露的限制，所以沒有走 reopen；請見第 3 段最後一項。
- **開發環境**：
  - 為了讓 subagent 的 worktree 從 session 分支建立，architect 在本機執行了 `git remote set-head origin claude/busy-darwin-asvox3`。這只改本機 metadata，沒有改任何分支或歷史。
  - 原因：main 有你新增的 workflow commit，不是 session 分支的祖先，`sync_worktree.py` 正確地拒絕覆蓋。
  - 新的雲端 session 需要重做這一步，或者由你把 workflow commit 也放進 session 分支。

## 5. 已知限制
- **主鍵值會進入 evidence curl**：若主鍵本身是個資（例如 email），報告會帶出它。由 MS6 決定是否遮罩（ADR-023 補記 S2）。
- **沒有擁有者欄位的表**：即使 anon 讀得到全部，也只回報 inconclusive，不判定為漏洞（D1）。
- **敏感欄位的判斷**：`SENSITIVE_COLUMN_PUBLIC` 與嚴重度升級依表的欄位名判斷，沒有測試欄位層級的 GRANT（D2）。
- **同名目標**：OpenAPI 只有 `/rpc/x` 時，bundle 的 `.from('x')` 會被略過（D3）。
- **公開欄位為 NULL 的列**：不會成為已知列，只會讓判定偏向 inconclusive（D4）。
- **L11 Storage（P2）**：不在 MS2 範圍，PLAN 中目前沒有 Storage 探測的 milestone。
- **`write_command` 不處理的語法**：`E'…'` 反斜線跳脫與 `--` 註解（PostgREST 不產生）。完全包在字串中的動態 SQL 不會被計為寫入（ADR-024）。
- **`query()` 的唯讀**：只防誤寫；明確執行 `SET default_transaction_read_only = off` 的語句仍可寫入（合約已註明）。
- **blocked ticket**：無。MS1 的 T-071 已由 T-080 交付。
