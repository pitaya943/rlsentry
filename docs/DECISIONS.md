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

## ADR-002：ruff 不檢查凍結的 harness/host 與 subagent worktree
- 日期：2026-11-02 · Milestone：STAGE0 · 相關：§11、CLAUDE.md「Style」
- 背景：T-000 第一次 `accept` 失敗，原因不是產品程式，而是 `make check` 的 `ruff check .` 在凍結檔案
  （`harness/`、`host/`）回報 105 個錯誤（雲端安裝的 ruff 0.16.9 預設規則比 harness 撰寫時更多，例如
  RUF100、EXE001、FURB167；連舊預設 `E4,E7,E9,F` 也會在 `harness/tickets.py` 報 E702），
  並且把 `.claude/worktrees/` 下的 subagent worktree 再掃一次。這些檔案在 session 內不可修改，
  因此每一張 ticket 都會被同一批錯誤擋下。
- 考慮過的選項：
  1. 修改 harness 讓它通過 lint（缺點：違反凍結規則，architect 也無權修改）。
  2. 在 `pyproject.toml` 把 `select` 降到很少的規則（缺點：同時降低產品程式的 lint 強度，而且 E702 仍會失敗）。
  3. 在 `pyproject.toml` 的 `extend-exclude` 排除 `harness`、`host`、`.claude`（優點：產品程式仍用完整預設規則；缺點：凍結程式不再被 lint）。
- 決定：採選項 3。原本已排除的 `harness/tests` 被 `harness` 涵蓋。
- 理由：凍結程式的正確性由你在核准前的 `git diff harness-frozen` 與 harness 自我測試保證，不靠 lint；
  `.claude/worktrees/` 是未合併的 subagent 工作區，不屬於 main 的內容。
- 後果與風險：ruff 版本未鎖定，未來預設規則再變動時，產品程式可能突然出現新錯誤；MS0 會在
  `pyproject.toml` 的 dev 依賴鎖定 ruff 版本（待 MS0 ADR 決定）。若你偏好在本機修正 harness 使其 lint 乾淨，
  可以在重新凍結時一併處理，然後移除這個排除。
