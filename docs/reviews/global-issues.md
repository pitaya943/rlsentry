# 全域問題清單（現有系統）

由 architect 在 Management session 記錄；**只記錄、不修正**。全部審核結束後，與 `arena/issues.md`（rlsentry-arena）、`review/issues.md` 合併，交人類規劃修正。

- 嚴重度：**高**＝上線前必須處理（安全結論錯誤或 CI 靜默通過）；**中**＝影響正確性、營運或可信度；**低**＝文件、可用性、發佈準備。
- 「待人類判定」＝ SPEC 層級的產品決定，不是實作錯誤。
- 行號以 claude/busy-darwin-asvox3 的 c29ca17 為準。

| ID | 嚴重度 | 標題 | 來源 |
| --- | --- | --- | --- |
| GI-01 | 低 | SPEC §8／NFR-01 仍寫 `log_statement = mod` 可驗證 0 次寫入 | architect（處理 Rival 001 時） |
| GI-02 | 高 | ci 在掃描不完整時 exit 0（fail-open） | Auditor-PM 001 Q1 |
| GI-03 | 高 | profile 被「較嚴者勝」靜默改為 audit，Action 永遠綠燈 | Auditor-PM 001 Q2 |
| GI-04 | 低 | dev／audit 接受 `fail_on` 卻忽略，無警告 | Auditor-PM 001 Q3 |
| GI-05 | 中 | benchmark 只量測 dev＋ground-truth policy，報告未揭露前提 | Auditor-PM 001 Q4 |
| GI-06 | 中（待人類判定） | ci 不跑 M1，service_role key 進 bundle 在 CI 永遠抓不到 | Auditor-PM 001 Q5 |
| GI-07 | 中（待人類判定） | CROSS_TENANT_READ 固定 Medium，預設 `fail_on` 下 L04 在 ci 通過 | Auditor-PM 001 Q6 |
| GI-08 | 高 | FR-05 覆蓋率與「未發現不代表安全」聲明沒有實作 | Auditor-PM 001 Q7 |
| GI-09 | 中 | INSERT 探測植入的列沒有 canary 標記 | Auditor-PM 001 Q8(b) |
| GI-10 | 中 | 有 DB 連線時不代為清理；CLEANUP_FAILED 不列殘留主鍵；exit 1 蓋過 exit 4 | Auditor-PM 001 Q8(a)(c) |
| GI-11 | 中 | CLEANUP_FAILED 同一 Finding.id 重複出現 | Auditor-PM 001 Q9 |
| GI-12 | 低 | 發佈準備：版本、`--version`、LICENSE、README、CI、action 固定方式 | Auditor-PM 001 Q10 |
| GI-13 | 低 | `rlsentry init` 的錯誤訊息、必要欄位與 RPC 草稿 | Auditor-PM 001 Q11 |
| GI-14 | 低 | CI 中授權紀錄 `confirmed_by` 多為 unknown | Auditor-PM 001 Q13 |
| GI-15 | 中 | 對外「audit 永遠不寫」未揭露登入造成的 GoTrue `auth.*` 寫入 | Auditor-PM 001 Q14 |

## 明細

### GI-01 SPEC §8／NFR-01 的 0 次寫入驗證方式與實測不符（低）
- 證據：`docs/SPEC.md:140`（NFR-01）、`:441`（§8「所有寫入都留在資料庫 log」）；ADR-019（`docs/DECISIONS.md:226-228`）實測 PostgREST 以 `WITH pgrst_source AS (INSERT …) SELECT …` 送出寫入，`log_statement = mod` 不記錄；實作已改為 authenticator 記錄全部語句（`rlsentry/contracts/lab.py:84-93`）。交給 Rival 的 kit/LAB_FACTS.md 沿用 SPEC 的錯誤說法（已在 arena inbox 001 更正）。
- 重現：只開 `log_statement = mod`，dev 掃描 L09 後查 DB log，找不到 PostgREST 的 INSERT。
- 建議：SPEC（凍結檔，需人類）與 LAB_FACTS 改寫為實際的驗證方式。

### GI-02 ci fail-open（高）
- 證據：`rlsentry/report/exit_code.py:15-24` 只依 findings 決定 exit code；exit 5 只用於例外（ADR-047 #3）。API 不可達、兩帳號登入失敗、0 個 target 都不拋例外。
- 重現（Auditor-PM）：L01、`profile: ci`，`supabase_url: http://127.0.0.1:1` → 全部 inconclusive、exit 0；密碼錯誤 → user 格 not_tested、exit 0；L11 → 空矩陣、exit 0。architect 未重跑。
- 建議：新增「掃描不完整」exit code 與門檻（例如登入失敗、0 target、not_tested／inconclusive 比例超標）。

### GI-03 profile 靜默變更（高）
- 證據：`rlsentry/pipeline.py:48-54`（ADR-014 #4）、ADR-010（省略時為 audit）；ADR-047／ADR-051 #7 只在 USAGE 揭露。
- 重現：設定檔省略 `profile`，`rlsentry scan --profile ci` → 實際 audit，有 Critical 仍 exit 0，終端無提示。
- 建議：CLI 與設定檔不一致時印警告；Action 在實際 profile ≠ 輸入時失敗。

### GI-04 `fail_on` 在 dev／audit 被忽略且無警告（低）
- 證據：`rlsentry/report/exit_code.py:15-16`；ADR-044 #4。
- 建議：印警告；audit 是否可用 `fail_on` 交人類（SPEC §2）。

### GI-05 benchmark 前提未揭露（中）
- 證據：`rlsentry/bench/run.py:30-44` 以 expected.yaml 的 `policy` 組設定；ADR-011 #7、ADR-042 #7 以 dev 計分。
- 重現（Auditor-PM，architect 未重跑）：`rlsentry init` 草稿＋`profile: ci`＋DB URL，16 情境 recall 27/32；漏 L07-V1..V3、L08-V1、L12-V1。
- 建議：BENCHMARK_REPORT 首段加註前提；另列「init 草稿＋ci」與「audit」的指標。

### GI-06 ci 不跑 M1（中，待人類判定）
- 證據：`rlsentry/contracts/pipeline.py:40-44`；SPEC §2 表格；ADR-042 #2。M1 只對同源發 GET（唯讀）。
- 建議：target 可達時 ci 跑唯讀 M1，或在 USAGE 明示 CI 不檢查前端 key。

### GI-07 跨租戶讀取的嚴重度（中，待人類判定）
- 證據：`rlsentry/rules/severity.py:25-30`（只有設 `escalates_to` 的規則會因敏感欄位升級）；SPEC §5 M5 嚴重度表；預設 `fail_on` severity high。
- 重現：USAGE 的 L04 情境改用 ci → exit 0。
- 建議：CROSS_TENANT_READ 對敏感欄位升級，或預設 `fail_on.severity: medium`。

### GI-08 FR-05 覆蓋率與聲明未實作（高）
- 證據：traceability.md:56 與 ADR-023 補記延到 MS6；MS6／MS7 驗證清單未追蹤；`grep -rn -i -E 'coverage|不代表安全' rlsentry/report` 無結果。Auditor-PM：L11 報告 `grep -c 不代表安全` = 0。
- 影響：使用者會把「沒有 finding」讀成「安全」，例如 L11 Storage、OpenAPI 關閉時未被 bundle 引用的表。
- 建議：報告列出探索覆蓋率（openapi_available、各 target confidence、未涵蓋的面向如 Storage）與固定聲明；流程上補「延後項目必須在目標 milestone 關閉」的檢查。

### GI-09 INSERT 探測的列沒有 canary 標記（中）
- 證據：`rlsentry/probe/write.py:62-64` 建立 INSERT WritePlan 時不傳 `text_column`，`write.py:137-138` 因此不放標記；可為 NULL 的欄位不會被 `fill_required` 填值。
- 重現（architect 實測）：`python -m lab._shared apply L09`，以 ci 範例設定換成 L09 policy 掃描 → `public.feedback` 新增 13 列，其中 3 列 `body IS NULL`（正是 anon、user_a、user_b 的 INSERT 探測）。
- 建議：INSERT 探測同樣帶 `rlsentry_canary_` 標記。

### GI-10 清理不完整且不可操作（中）
- 證據：SPEC §5 M3「lab 中有 DB 連線時代為清理」未實作（`rlsentry/probe/cleanup.py` 無 DB 路徑；`db_url` 只用於 M4，`pipeline.py:99-100、172-177`）；T-138 補記：報告不含殘留列；`exit_code.py:19-23` 檢查順序使 exit 1 蓋過 exit 4。
- 重現：同 GI-09；提供 `db_url_env` 仍殘留 13 列，重跑仍 +13。
- 建議：有 DB 連線時代為清理；CLEANUP_FAILED 列出殘留主鍵與 `DELETE … WHERE pk IN (…)` 範本；exit code 能同時表達兩種狀態（或 notes 明示）。

### GI-11 Finding.id 重複（中）
- 證據：`rlsentry/contracts/models.py:185-191`；讀取植入清理（ADR-042 #5）與寫入探測清理各自產生 CLEANUP_FAILED，未合併。
- 重現（architect 實測）：同 GI-09 的掃描，`d49f4406f71fed8f`、`6172264dd663da7d` 各出現 2 次。
- 影響：SARIF `partialFingerprints` 與「新問題／舊問題」判斷（SPEC §6）不可靠。
- 建議：報告層依 id 合併；加入「findings id 唯一」的測試。L07 的 SECURITY_DEFINER_EXECUTABLE role=None／anon 兩筆語意重複，一併檢查（architect 未重跑）。

### GI-12 發佈準備不足（低）
- 證據：`pyproject.toml:7` version 0.0.0；無 `--version`、LICENSE、產品 README；`.github/workflows/` 只有 verify-milestone；`action/action.yml:22、43` 以 tag 固定第三方 action。
- 建議：建立發佈清單；授權條款由人類決定。

### GI-13 `rlsentry init` 可用性（低）
- 證據：`rlsentry/cli.py:64` 的錯誤訊息提到 TARGET，但 init 不接受（ADR-042 補記 2）；init 需要 `anon_key_env`；草稿只有 `target`、`tables`；`rlsentry/policy/init.py:21-23` 對 RPC 產生 `deny/deny` 且無 `primary_key`，L07 因此永遠 inconclusive。
- 建議：修正訊息；草稿含完整表頭；RPC 草稿標 TODO 並提示 `primary_key`。

### GI-14 授權紀錄的確認者（低）
- 證據：`rlsentry/contracts/pipeline.py:52` CONFIRMER_ENV；Action（ADR-044 #7）未帶 `GITHUB_ACTOR`。
- 建議：Action 帶入 `GITHUB_ACTOR` 與 repo；audit 報告中 `unknown` 是否可接受交人類。

### GI-15 audit「不寫入」的對外說法不精確（中）
- 證據：ADR-014 #2（GoTrue 的 `auth.*` 寫入不計入 NFR-01）；`docs/verification/traceability.md:12`；`USAGE.md:84` 只寫「永遠不寫（只送 GET／HEAD 與登入的 POST）」。
- 建議：USAGE 與報告寫明「不經資料 API 寫入；登入會使 Auth 服務更新 last_sign_in_at、refresh token、audit log」。
