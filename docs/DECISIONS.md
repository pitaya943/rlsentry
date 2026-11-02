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
