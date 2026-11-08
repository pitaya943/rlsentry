# 004 新任務（A5）：審閱 SPEC 並提出修改建議 — architect → Auditor-PM

日期：2026-11-08　依據：人類（專案負責人）的指示。A0–A4 已結束，這是新的獨立階段 A5。

## 目的

以 PM（上線前的產品負責人）角度審閱現有系統的規格書 `docs/SPEC.md`（654 行，§0–§14），提出修改建議。SPEC 是凍結檔，**你只提建議，不修改**；人類會依你與 architect 的建議修訂並重新凍結。

## 範圍

全部章節都要看，重點是：

1. **與實際設計的落差**：已經被 ADR 改掉、但 SPEC 從未吸收的偏離。例如 ADR-011 #5（safe case 可為 allowed）、ADR-019（log_statement）、ADR-042 #2（audit 也跑 M4）、ADR-007（RPC 以 select 表示）。請逐一檢查 `docs/DECISIONS.md` 中寫著「偏離 SPEC」的地方。
2. **產品需求層級的缺口**：你在 A2 找到的問題中，根因在 SPEC 的部分。例如 §2 的 ci 模組表與失敗門檻、§5 M5 的嚴重度表、FR-05 的驗收方式。
3. **對外上線缺少的需求**：發佈、版本、授權、相容性承諾、報告格式的穩定性等，SPEC 是否該規定。
4. **可驗證性**：每條 FR／NFR 的驗收方式是否可以客觀檢查；模糊、矛盾或無法測試的條文。
5. **§10–§13 的開發流程章節**：哪些是開發期專用、上線後應移出或改寫（產品規格與開發流程是否該分開）。

## 每條建議的格式（必填）

| 欄位 | 內容 |
| --- | --- |
| 編號 | S-01、S-02… |
| 位置 | SPEC 章節與行號（`docs/SPEC.md:NNN-NNN`） |
| 現行文字 | 原文引用（短） |
| 問題 | 為什麼要改；附證據（ADR、file:line、你的實測、review/ 中的 I-xx） |
| 建議文字 | 可以直接替換的新條文 |
| 替代方案比較 | 至少兩個選項（含「不改」），各自的優缺點與取捨 |
| 解釋 | 給人類看的說明：背景與直覺先於細節（人類熟悉 CS，但對資安產品規格較陌生） |
| 影響 | 會牽動哪些實作、測試、ADR、USAGE；是否改變既有行為 |
| 優先 | P0／P1／P2／P3 |

## 交付

- `review/spec-review.html`：完整報告（繁體中文、自包含 HTML、不載入外部資源）。開頭附摘要與依優先排序的總表。
- `review/spec-issues.md`：純清單（編號、位置、一句話建議、優先），方便合併。
- `review/outbox/004-spec-review-done.md`：完成通知。若有需要 architect 回答的問題，寫在這封信裡（最多一輪）。

## 規則

- 規則同 A0–A4：只寫 `review/`；只連線 localhost、PyPI、GitHub；不修改其他檔案；不 merge、rebase、reset、tag、force-push。
- **獨立性**：在交付前，請不要閱讀 `docs/reviews/pm-response-and-fix-plan.html`。那是 architect 對你 A4 報告的修正方案，人類要比較你和 architect 各自獨立的 SPEC 建議。`review/` 與 `docs/reviews/global-issues.md` 可以讀。
- Stop hook：結束回合前先 commit 並 push。若 hook 阻擋結束，照常完成交付即可，不要為了等回信而空轉。
