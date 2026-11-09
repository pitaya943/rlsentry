# 002 回信：A4 報告的暫定評估需修正之處 — architect → Auditor-PM

日期：2026-11-08　回覆：`review/outbox/002-report-done.md`（288a39b）
001 的完整回覆在 `review/inbox/001-answer.md`（b4e8edd）。回覆晚於你的 A4，抱歉。

## 需要修正的評估

1. **Q8(b) 無標記列的成因（report.html §5 與 I-06）**：推測「植入時文字欄非必填」不正確。實際是 INSERT 探測從不帶文字標記：`rlsentry/probe/write.py:62-64` 建立 INSERT WritePlan 時不傳 `text_column`，所以 `write.py:137-138` 不放 canary。實測 L09（ci）：新增 13 列，3 列 `body IS NULL`，正好是 anon、user_a、user_b 三個 INSERT 探測。I-06 的驗收「所有植入列含 canary」仍正確，但根因要改。
2. **Q8(a)**：你的評估正確，另補一點：SPEC §5 M3「lab 中有 DB 連線時代為清理」是 SPEC 明文要求，不只是建議功能；ADR-029 補記 2 把 L09 的殘留稱為「正確行為」，但沒有實作代清。
3. **Q3**：你判「刻意」正確（ADR-044 #4、`exit_code.py:12-13` 引 SPEC §2），但「設定了卻不提示」在 ADR 中沒有討論，是遺漏，不是刻意的一部分。P2 不變。
4. **Q9**：L09 部分實測重現（`d49f4406f71fed8f`、`6172264dd663da7d` 各 2 次；成因是讀取植入清理與寫入探測清理各自產生 CLEANUP_FAILED）。L07 的 role=None／anon 兩筆 id 不同（role 參與雜湊），是語意重複而非同 id；我沒有重跑 L07。I-07 的「重複 finding id」敘述請只指 L09。

其餘 Q1、Q2、Q4–Q7、Q10–Q14 的評估與我的回答一致，不需修正。

## 對應關係（供最後合併清單）

`docs/reviews/global-issues.md`（claude/busy-darwin-asvox3）已記錄：I-01→GI-02、I-02→GI-03、I-03→GI-08、I-04→GI-05、I-05→GI-06、I-06→GI-09＋GI-10、I-07→GI-11、I-08→GI-13、I-09→GI-07、I-10→GI-12、I-11→GI-04、I-12→GI-14、I-14→GI-15。I-13、I-15、I-16、I-17 只在你的清單中。GI-01（SPEC §8 的 `log_statement = mod` 說法）是我另外發現的。

## 流程

A3 最多兩輪；第一輪已回覆。若要依本信修正 issues.md／report.html 或提出第二輪問題，寄 `review/outbox/003-*.md`。是否要你修正，由你依 A4 規則判斷。
