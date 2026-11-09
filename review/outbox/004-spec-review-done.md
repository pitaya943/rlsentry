# 004 A5 SPEC 審閱完成 — Auditor-PM → architect

回覆：`review/inbox/004-task-spec-review.md`

## 交付
- `review/spec-review.html`：26 條建議（P0 4、P1 8、P2 12、P3 2），每條含位置（SPEC 行號）、現行文字、問題與證據、建議文字、替代方案比較（含「不改」）、解釋、影響、優先；§4 逐條對照「偏離 SPEC」與未吸收的 ADR。
- `review/spec-issues.md`：純清單。
- 獨立性：交付前未閱讀 `docs/reviews/pm-response-and-fix-plan.html`。

## 重點
- P0：S-01 ci 掃描完整性門檻（新 exit 6，目前未被使用）；S-02 有效 profile 必須可見、要求 ci 卻得不到 ci 時 exit 2；S-03 覆蓋率與「未發現不代表安全」拆為獨立 FR-17；S-04 指標註明量測條件並新增使用者路徑指標。
- 需人類決策：S-01 門檻預設值、S-05 ci 跑 M1、S-06 跨租戶讀取嚴重度、S-09 init 的 TODO 是否擋掃描、S-10 授權條款、S-12 audit 是否適用 fail_on、S-21 audit 是否拒絕 unknown 確認者、S-25 分離 PROCESS 文件（harness/milestones.yaml:1 與 acceptance.py:171 引用 SPEC §11、§9，凍結檔需人類處理）。

## 問題（一輪，可選答）
1. S-22：產品 CI 的覆蓋率閘門需要新增 workflow 或 Makefile target（Makefile 凍結）。你傾向放在哪裡？這決定 S-22 的「影響」欄是否要列為需人類處理。
2. S-14：發佈 JSON Schema 是否已有任何既有測試（例如 SARIF 的 OASIS schema 驗證之外，報告 JSON 是否有 schema 測試）？若有，S-14 可降為 P3。

未回覆也不影響本交付；A5 到此結束。
