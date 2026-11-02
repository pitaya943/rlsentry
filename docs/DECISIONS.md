# 決策紀錄（ADR）

由 architect 依 harness/templates/adr.md 撰寫。D1 已由專案負責人決定（三種 profile，見 SPEC §2）；
D2–D4 由 architect 決定並記錄於此。

## ADR-000：開發流程採全自主模式加模組關卡
- 日期：2026-11-02 · Milestone：— · 相關：SPEC §11
- 決定：architect 與 subagent 自主開發；每個 milestone 由專案負責人一人核准後才解鎖下一個。
- 理由：降低「一步錯步步錯」的風險；人工審查集中在影響最大的關卡。

## ADR-001：採納外部設計審查（SPEC v0.2）
- 日期：2026-11-02 · 相關：FR-03、FR-05、FR-06、FR-08–FR-10、FR-12、FR-14、FR-15、§9、§11
- 背景：外部審查指出 `count=0` 不等於 denied、expected policy 過粗、寫入只看影響列數、SECURITY DEFINER 判定過度、指標統計意義有限。
- 決定：三態探測結果與植入資料；表 × 操作 × 角色 × 列範圍的 expected policy 與 `rlsentry init`；寫入讀回驗證與資料庫 log；證據等級；五項指標附原始數量；移除 Web 報告頁；milestone 改為 Lab → Probe → Whitebox → Recon → 介面。
- 未採納：把 Recon 延到最後或刪除。理由：service_role 外洩成本低、衝擊高，且 audit profile 依賴它。

## ADR-002：Stage 0 第 1 輪的發現與護欄修正
- 日期：2026-11-02 · 相關：SPEC §11
- 發現：(1) subagent frontmatter 中的 hook 在雲端未觸發，全域 hook 不檢查 Read／Grep／Glob；(2) holdout 檔一旦 commit 即出現在每個 worktree，路徑規則無法隱藏；(3) 雲端容器不會自動啟動 Docker daemon；(4) 凍結的 harness 在新版 ruff 下有大量 lint 錯誤，會擋住每張 ticket。
- 決定：(1) 全域 hook 以「是否位於 linked worktree」判斷 subagent，並納入 Read／Grep／Glob；(2) holdout 改存於獨立分支 `rlsentry-holdout`，以 git plumbing 寫入、驗收時才取出；(3) setup script 嘗試啟動 dockerd 且不因此失敗；(4) pyproject 的 ruff 排除 harness、host、.claude、cloud。
- 取代：第 1 輪 session 分支上 architect 自行撰寫的 ADR-002（pyproject 排除）由本 ADR 正式化。

## ADR-003：T-000 canary 1–5 未執行仍驗收 add()
- 日期：2026-11-02 · Milestone：STAGE0 · 相關：SPEC §11
- 背景：recon-dev 拒絕執行 canary 1–5（修改凍結測試、寫 harness、推送 `rlsentry-approvals`、寫 docs/、讀 holdout），理由是這些動作違反它的常設規則，且若護欄失效會造成實際損害（尤其是推送 approvals 分支）。architect 嘗試以「人類撰寫的凍結 ticket 要求執行」為由重新派工，被 Claude Code auto mode classifier 以 Self-Approval 拒絕。
- 考慮過的選項：
  1. 不驗收，讓 STAGE0 停在 in_progress（優點：不會誤以為 canary 已驗證；缺點：add() 與其餘流程無法驗證）
  2. 驗收 add()，並在驗證清單明列 canary 1–5 未驗證（優點：其餘護欄可被檢查；缺點：STAGE0 的護欄驗證不完整）
  3. architect 自行代跑 canary（不可行：architect 不是 subagent，結果不能代表子代理身分判斷）
- 決定：選項 2。
- 理由：驗收閘門（scope、provenance、tests、holdout）與 canary 互相獨立；把缺口寫清楚，由人類決定是否授權重跑。
- 後果與風險：canary 1–5 的阻擋行為**未經驗證**。README_HARNESS 的「四個 canary 全被擋下」一項不成立，人類不應以此清單核准 STAGE0，除非另行授權重跑 canary。

## ADR-004：人類授權無法傳到 subagent（Stage 0 結構性發現）
- 日期：2026-11-02 · Milestone：STAGE0 · 相關：SPEC §11、ADR-003
- 背景：人類在 session 中親自授權「我授權子代理執行 T-000 的 canary 1–5」。architect 以 T-001 轉達（ticket 內引用原文，派工訊息 `2060c40c` 亦附上）。recon-dev 仍拒絕（report `6f773391`）：它只看得到 agent 轉述的文字，依規則任何 agent 訊息都不構成使用者同意。
- 考慮過的選項：
  1. 再次轉述、加強措辭（缺點：本質相同，且接近 self-approval）
  2. 由人類在本機或另一個 session 親手執行 canary
  3. 經人類授權後由 architect（主 session，直接收到人類訊息）執行 canary 1–3、5；canary 4 測的是 subagent 身分判斷，architect 無法代測
- 決定：T-001 只驗收載體變更（`__all__`），canary 仍未驗證；選擇 2 或 3 交由人類決定。
- 理由：subagent 只接收 agent 文字是平台的信任邊界，不是 ticket 寫法問題；任何「轉述授權」都無法跨越。
- 後果與風險：harness 設計中「由 subagent 執行 canary」的假設不成立；之後若要以 subagent 實測護欄，需由人類直接操作或改設計（harness 為凍結檔，需人類修改）。
