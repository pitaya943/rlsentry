# MS5 高風險 ticket 審查說明（ADR-005 補記：分級＋合併）

本 milestone 以 worktree accept 合併（未另推 `review/T-xxx` 分支）。要看單張 diff：`git show <sha>`，或 `https://github.com/pitaya943/rlsentry/compare/<sha>~1...<sha>`（`<sha>` 換成下表的 accept commit）。

## 清單與預估閱讀時間（約 45 分鐘）
**逐張審查**（第 1 類精神：決定送出哪些請求；第 3 類：key 與遮罩；第 4 類：計分輸入）：
- T-186 `recon/fetch.py`（只 GET、不帶 header、同源才請求、上限、跳過原因），約 8 分鐘 — c7eced0
- T-182 `recon/classify.py`（JWT 不驗簽、service_role → Critical、publishable 不產生 finding、只留遮罩值），約 5 分鐘 — 0967193
- T-183 `recon/extract.py`（JWT／sb_／generic 候選、entropy 與 key 語境），約 6 分鐘 — 78fc85c
- T-187 `recon/run.py`（supabase_url 與 anon_key 的優先序、範圍、sources），約 6 分鐘 — ee1c4b2
- T-193 `recon/links.py` 的 `report_url`、`same_origin` userinfo、fetch／run 的報告 URL（稽核 P1 S1），約 5 分鐘 — ec0d1d6
- T-189 `bench/run.py`（recon 不計時、key finding 不經 correlate），約 4 分鐘 — 157fcf9

**建議抽查**：
- 合約與 ADR：T-180（ADR-036、037；KeyFinding.label、chunks_skipped）460ec9c；T-192（report_url、KeyFinding validator、ADR-036 補記）75ea911
- T-184 `recon/links.py`（chunk 路徑、webpack map）8569144；T-185 `recon/sourcemap.py` 1ac80b2；T-188 `labctl.serve_frontend` 1b1aace
- 測試與 fixture：T-181 c96747a（三個真實框架建置，見 `tests/recon/fixtures/README.md`）；T-191 0387d30（只改 docstring）
- T-190（benchmark JSON 與報告）5a41a73

MS5 沒有修改 `rlsentry/safety/**`，也沒有 ground truth（第 5 類）的變更。

## 重點
- **service_role 一定是 Critical**：`classify_key` 以 JWT payload 的 `role` 判斷（不驗簽）；`findings_from_keys` 只對 secret／unverified 產生 finding；`KeyFinding` validator 讓「service_role 被標成 publishable」在型別上不可能。
- **anon／publishable 永不產生 finding**：16 個 lab 前端都有 anon key，只有 L08 有 finding（`tests/recon/test_lab_frontends.py`）。
- **遮罩**：KeyFinding 只有前 6 後 4；報告中所有 URL 經 `report_url`（省略 query string、移除 userinfo、再 mask_text）。
- **網路範圍**：recon 只對 target 同源送 GET、不帶任何 header；跨源（CDN、帶 userinfo）只列入 `chunks_skipped`。
