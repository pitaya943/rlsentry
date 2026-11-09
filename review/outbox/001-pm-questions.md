# 001 PM 問題（第一輪）— Auditor-PM → architect

背景：上線前審核。盲測證據見 `review/blind.html`（commit 67c5cca）。每題附證據與「我會用答案決定什麼」。
請逐題回覆於 `review/inbox/001-answer.md`，以題號對應；不知道就寫「不知道」，比猜測好。

## A. CI 失敗開放（fail-open）— 決定是否列為上線阻擋項（P0）
Q1. `ci` profile 下以下情況全部 exit 0，是設計還是缺陷？（重現：L01，`profile: ci`）
  (a) `supabase_url` 連不上（127.0.0.1:1）→ 所有格 inconclusive，exit 0；
  (b) 兩個測試帳號都登入失敗（HTTP 400）→ user 格 not_tested，exit 0；
  (c) M2 發現 0 個 target（L11）→ 空矩陣，exit 0。
  SPEC §2 使用者故事「PR 引入新的可存取表時 CI 失敗」；目前一個壞掉的 secret 就讓 CI 永遠綠燈。
  → 決定：是否要求新增 exit code（例如 5 = 掃描不完整）及門檻（例如 not_tested/inconclusive 比例）。
Q2. `rlsentry scan --profile ci` 在設定檔省略 `profile` 時被「較嚴者勝」靜默改成 audit，有 critical 也 exit 0，終端沒有任何提示（`cli.py:100`、`pipeline.py:48-54`、ADR-010/014 #4）。USAGE §6 有文字提醒，但是否考慮過：(i) CLI 與設定檔不一致時印警告；(ii) Action 在實際 profile ≠ 輸入 profile 時直接失敗？
  → 決定：列 P0（Action 使用者最可能踩）或 P1（文件已說明）。
Q3. audit／dev 下 `fail_on` 被接受但完全不生效（`report/exit_code.py:15-16`），也沒有警告。這是否應改成：設定 `fail_on` 但 profile 非 ci 時印警告，或允許 audit 使用 `fail_on`（稽核也常在排程中跑）？

## B. 有效性與 benchmark 誠實度 — 決定 BENCHMARK_REPORT 能否原樣對外
Q4. Benchmark 只用 dev profile，且 policy 取自 `expected.yaml` 的手寫 `policy`（`bench/run.py:30-44`），包含使用者通常不會知道要寫的提示（L07 的 RPC `primary_key: [id]`、`ping_definer: all`）。我用「使用者真實路徑」重跑：`rlsentry init` 草稿 + `profile: ci` + DB URL，16 情境計分後 recall = **27/32（84%）**，漏掉 L07-V1..V3（RPC 需單欄主鍵 → inconclusive）、L08-V1（ci 不跑 M1）、L12-V1（ci 不掃 bundle，init 草稿為空）。
  (a) 是否同意對外指標應另列「init 草稿 + ci」與「audit」的 recall？
  (b) 是否接受在 BENCHMARK_REPORT 首段加註「指標以 ground-truth policy 量測」？
Q5. `ci` 不跑 M1，因此 service_role key 進 bundle（SPEC 定義的 Critical）在 CI 中永遠不會被抓到；audit 會抓到但 exit 0。SPEC §2 表格確實寫 ci = M2–M5。是否考慮「ci 有 target 可達時跑唯讀的 M1」？這是唯一完全不需要寫入、又最嚴重的規則。
Q6. CROSS_TENANT_READ 為 Medium、預設 `fail_on` 為 ≥ high，所以 L04（展示情境本身！）在 ci 下 exit 0。SPEC §5 嚴重度表如此規定，但 `customers` 含 email（敏感欄位）時，anon 讀升為 Critical、跨租戶讀仍為 Medium（`rules/severity.py:25-30`）。這個不對稱是刻意的嗎？
  → 決定：是否建議預設 `fail_on.severity: medium`，或讓 CROSS_TENANT_READ 對敏感欄位升級。
Q7. L11（Storage public bucket）完全無輸出，報告也沒有「Storage 未涵蓋」字樣；FR-05「報告列出探索覆蓋率，並聲明『未發現不代表安全』」在 traceability 第 56 行標為「→ MS6」，我在 HTML/JSON 報告中找不到覆蓋率或此聲明（L11 報告 `grep -c 不代表安全` = 0）。這是否被遺漏？若已實作，在哪個檔案：行？

## C. 營運副作用 — 決定 ci 對 preview DB 的上線建議
Q8. L09（insert-only 表）每次 ci／dev 掃描殘留 13 列（10 列 canary、**3 列 content 為空、無 canary 標記**），重跑 apply 後再掃一次仍是 +13。CLEANUP_FAILED finding 沒有列出殘留主鍵、沒有清理 SQL；且有 ≥high finding 時 exit 1 蓋過 exit 4。
  (a) SPEC §5 M3「lab 中有 DB 連線時代為清理」是否實作？我提供了 `db_url_env`，仍殘留。
  (b) 為何有 3 列沒有 canary 標記？（推測：OpenAPI 的必填欄位填值時沒有把 canary 放進文字欄）
  (c) 是否同意報告列出殘留主鍵並附 `DELETE … WHERE pk IN (…)` 範本？
Q9. L09 的 CLEANUP_FAILED 同一個 `id` 出現兩次（d49f4406f71fed8f ×2、6172264dd663da7d ×2）；L07 的 SECURITY_DEFINER_EXECUTABLE 同一函式出現 role=None 與 role=anon 各一。SPEC §6 說 id 用來分辨新舊問題（SARIF partialFingerprints）。重複 id 是已知問題嗎？

## D. 上線與發佈 — 決定「外部使用者」上線清單
Q10. 發佈計畫：`version = "0.0.0"`、沒有 `--version`、沒有 LICENSE、沒有產品 README（只有 README_HARNESS.md）、沒有 PyPI 發佈、`.github/workflows` 只有手動的 verify-milestone（沒有 push/PR 時跑測試或自我掃描）。Action 從 `$GITHUB_ACTION_PATH/..` 原始碼安裝，第三方 action 以 tag（非 SHA）固定。哪些是刻意延後、哪些是遺漏？有沒有預定的授權條款？
Q11. `rlsentry init`：(a) 錯誤訊息「pass --config or a TARGET」但 init 不接受 TARGET；(b) init 需要 `anon_key_env`，scan 卻可從 bundle 取 key；(c) 草稿只有 `target` 與 `tables`，沒有 `authorized`、`supabase_url`、`test_users`、`profile`、`fail_on`；(d) RPC 草稿為 `deny/deny` 且沒有 `primary_key`，導致 L07 永遠 inconclusive。這些是已知取捨嗎？哪個 ADR？
Q12. lab：`python -m lab._shared env` 不給測試帳號 email、`sql` 不印查詢結果，盲測時我只能用 `RAISE EXCEPTION` 取得 email。這是刻意的嗎（例如避免輸出資料）？

## E. 法律／安全
Q13. 授權紀錄 `confirmed_by` 在 CI/容器中多半是 `unknown`（`pipeline.py:62-67`，只看 RLSENTRY_CONFIRMED_BY/USER/USERNAME）。Action 是否應自動帶 `GITHUB_ACTOR` 與 repo？audit 報告作為「授權確認紀錄」時，unknown 是否可接受？
Q14. audit 唯一允許的非 GET 是密碼登入；GoTrue 登入本身會寫 `auth.*`（traceability 第 12 行）。對 production 做 audit 時，這些寫入（last_sign_in_at、refresh_tokens、audit_log_entries）是否已在 USAGE 告知使用者？「audit 絕不寫入」的對外說法是否需要精確化為「不經 PostgREST 寫入」？
