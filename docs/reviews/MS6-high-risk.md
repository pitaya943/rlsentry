# MS6 高風險 ticket 審查說明（ADR-005 補記：分級＋合併）

本 milestone 以 worktree accept 合併（未另推 `review/T-xxx` 分支，同 MS5）。要看單張 diff：`git show <sha>`，或 `https://github.com/pitaya943/rlsentry/compare/<sha>~1...<sha>`（`<sha>` 換成下表的 accept commit）。

## 清單與預估閱讀時間（約 60 分鐘）
**逐張審查**（第 1 類 safety、第 2 類寫入）：
- T-215 `safety/endpoint.py`（S4：Supabase URL 必須由設定檔或 `--supabase-url` 指名；bundle 的 URL 只出現在拒絕訊息），約 6 分鐘 — f1bc45e
- T-219 `pipeline.py`（授權 → 唯一 SafeClient → M1 → S4 → M2 → M3 → M4 → M5；audit 不植入、不提權），約 12 分鐘 — eb35e5e
- T-234 `pipeline.py`／`cli.py`／`whitebox/correlate.py`（稽核修正：例外時仍清理、Typer 不印 locals、EXIT_ERROR、correlate 排除 KEY_RULES），約 6 分鐘 — 81b084c
- T-213 `probe/read.py`、`probe/run.py`（合併讀取的單一 GET；遠端 WriteRefused → inconclusive），約 8 分鐘 — ac1d56a
- T-214 `probe/seed_pass.py`、`probe/escalation.py`（dev／ci 讀取植入與清理；L03 提權：提權前重測基準、一定還原），約 10 分鐘 — ea1a426
- T-233 同上兩檔＋`probe/metadata.py`（稽核修正：網路錯誤時不遺失植入紀錄、還原失敗必回報），約 6 分鐘 — 028a6d5

**建議抽查**（第 3、4、6 類）：
- 合約與 ADR：T-200（ADR-038–044）684d1af；T-202（提權基準補記、read_policies DB log 測試）927d13a；T-232（ADR-047）46885df
- 判定規則：T-211 correlate（依物件與角色、改標）0e93abc；T-212 read_rule 5eb90e3
- 報告與遮罩：T-216 修補 SQL／enrich d32ecb4；T-217 JSON／HTML 65f0c55；T-218 SARIF／exit code c95fe36；T-235 recon URL 253bd06
- 介面：T-220 CLI 20f08ac；T-221 GitHub Action 9f39ecc；T-222 bench 改經 run_scan f436852
- 測試：T-201 aae004b；T-203 fd71983；T-230 99638bc

MS6 沒有 ground truth（第 5 類）的變更。

## 重點
- **audit 無法寫入**：三道防線——pipeline 在 audit 不呼叫植入與提權、probe 的寫入 cell 一律 not_tested、SafeClient 閘門拒絕所有非 GET（登入除外）。e2e 以 DB log 驗證寫入為 0。
- **CI 只在 Confirmed 時失敗**：`report/exit_code.py` 只在 ci 生效；證據等級與嚴重度兩個門檻同時成立才回 1。
- **S4**：bundle 指向未確認的主機時，API 主機一個請求都收不到（單元測試以 MockTransport 計數；e2e 在 lab 以實際連線計數）。
