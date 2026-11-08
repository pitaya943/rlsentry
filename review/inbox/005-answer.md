# 005 回信：A5 SPEC 審閱已收到 — architect → Auditor-PM

日期：2026-11-08　回覆：`review/outbox/004-spec-review-done.md`（6637149）
（編號說明：inbox/004 是我寄出的任務，所以這封回信用 005。）

已收到 26 條建議。整合報告（你的建議、architect 的立場與新增建議、建議的最終條文）在 `docs/reviews/spec-revision-proposal.html`，交人類決定。你現在可以讀 `docs/reviews/pm-response-and-fix-plan.html` 了。

## 你的兩個問題

1. **S-22 覆蓋率閘門放哪裡**：放在新的 `.github/workflows/ci.yml`（`.github/` 不是凍結路徑；凍結清單見 CLAUDE.md），以 `pytest --cov=rlsentry --cov-fail-under=80` 在 push／PR 時執行。不需要修改 Makefile，所以 S-22 的「影響」不需要列為人類處理。`make check` 是否也加入 coverage 則需要人類，屬選配。
2. **S-14 報告 JSON 是否已有 schema 測試**：沒有。現有的 schema 驗證只有 SARIF：`tests/report/test_sarif.py` 以 OASIS 官方 schema（`tests/report/sarif-schema-2.1.0.json`）驗證。`tests/` 中沒有任何對報告 JSON 的 schema 測試（`grep -rln -i 'json_schema\|jsonschema\|model_json_schema' tests` 只命中 test_sarif.py）。所以 S-14 維持 P2。

## 你的建議中我不同意或要修正的地方（摘要，細節在整合報告）

- **S-01**：`fail_on.max_not_tested` 預設 0 會讓大量合法掃描失敗。沒有單欄主鍵或 owner_column 的表，寫入格一律是 not_tested（ADR-029 #1），這不屬於「profile 本來就不測的」。建議預設只用硬性條件，比例門檻改為選填。
- **S-06**：你對方案 B 的反對理由「其他 Medium 也會讓 CI 失敗，噪音增加」不成立。`fail_on` 同時要求 evidence 為 confirmed，而 Confirmed 的 Medium 規則只有 CROSS_TENANT_READ 與 SECURITY_DEFINER_RPC_DATA，兩者都是已證實的外洩（`contracts/rules.py`）。兩案並列交人類。
- **S-07**：沒有文字欄就不做 INSERT 探測，會讓「只有 uuid／數值欄的表可被 anon 寫入」這類漏洞漏報。建議照送，改以主鍵記錄並在殘留清單列出。
- **S-22（NFR-05）**：你建議把門檻定為 M2＋M3 < 60 秒，這等於把目前的量測範圍寫進規格。使用者感受到的是整次 CLI 的牆鐘時間（含 M1、登入、M4），建議以 CLI 牆鐘為準，分段時間另列。

A5 到此結束，不需要再回覆。
