# MS0 驗證清單 v1（main @ 4ecbe30be）

## 1. 本模組做了什麼
- ticket：23 張（T-010–T-032），0 張 blocked。T-026 用了 2 次，其餘 1 次；平均 1.04 次。
  - architect 19 張：合約（T-010–T-013）、可見測試（T-014、T-031）、16 個情境的 ground truth（T-015–T-020）、一致性測試（T-024）、MS1–MS7 ticket 計畫（T-025，`docs/PLAN.md`），以及依 auditor 審查做的修正（T-026–T-030）。
  - probe-dev 4 張：`rlsentry/policy/resolve.py`、`visibility.py`、`load.py`（T-021–T-023），以及錯誤訊息不得回顯檔案內容的修正（T-032）。
- ADR-005–ADR-014：
  - 005：PR 政策與高風險判定規則（你在 STAGE0 的要求）
  - 006：§6 模型增補
  - 007：RPC 以 select 表示
  - 008：rule catalog
  - 009：ground truth 格式增補
  - 010：設定檔預設 audit／未授權
  - 011：計分規則，以及 L04 偏離 SPEC 範例
  - 012：mypy 與相依套件
  - 013：D4 Firebase 列為未來工作
  - 014：auditor 發現的修正
- Ground truth：P0 漏洞案例 32、safe 72、inconclusive 7；L11 為 P2，不計分。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS0 --no-vc`：ALL PASSED。
  - tests：302 passed
  - holdout：12 passed
  - safety：9 passed
  - 其他：provenance、ruff、mypy 皆通過
  - mutation：略過
- auditor（Base 3a3c611）找到 1 個 P0 ground truth 錯誤（L05）與 2 個 P0 設計缺口（audit 登入、資料庫 log 判準），處理方式見 ADR-014。追溯表在 `docs/verification/traceability.md`。

## 3. 請你親手驗證（逐項打勾）
- [ ] 在容器內執行 `make verify-milestone MS=MS0`。執行前，先在你的機器上跑 `git diff --stat harness-frozen -- harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud .gitattributes`。
      預期：diff 為空；最後一行為 `MS0: ALL PASSED`。（若 mypy 報 pydantic import 錯誤，代表你 PATH 上的 python3 沒裝相依套件，見 ADR-012：`pip install -e .[dev]`。）
- [ ] 閱讀 `rlsentry/contracts/models.py:101-128`（ProbeResult 與它的驗證器）
      確認：known_rows_checked == 0 時不可能產生 allowed／denied。這是 SPEC「count = 0 不等於 denied」的型別化。
- [ ] `python3 -c "from rlsentry.contracts.models import *; ProbeResult(target='t',role=Role.ANON,op=Op.SELECT,outcome=Outcome.DENIED,known_rows_checked=0,reason='',evidence_curl='')"`
      預期：ValidationError，訊息含 `a verdict needs at least one known row`。
- [ ] 閱讀 `lab/L04_cross_tenant_read/expected.yaml` 第 4–10 行與 L04-V2
      確認：你同意 SPEC §8 範例中「user_a 讀 note_b1 為 denied」與該 policy 矛盾，應改列為漏洞（ADR-011 偏離）。
- [ ] 閱讀 `lab/L05_cross_tenant_write/expected.yaml` 第 4–14 行
      確認：`created_by` 的設計合理。理由是 UPDATE 會讓 Postgres 對新列套用 SELECT policy，原寫法下漏洞不存在（auditor G1）。若你有 Docker，可照 auditor 的 psql 指令實測（PRODUCTION_LOG 審查事件）。
- [ ] 抽查一個對照組：`lab/C04_user_without_data/expected.yaml` 全檔
      確認：A 讀 B 的列是 inconclusive（B 沒有資料），B、anon 讀 A 的列是 denied。
- [ ] 把 `lab/C01_owner_scoped_ok/expected.yaml` 中 C01-S2 的 `role: user_a` 暫時改成 `role: user_b`，再執行 `python3 -m pytest -q tests/ground_truth`（完成後用 `git restore` 還原）
      預期：失敗，訊息含 `each safe/inconclusive cell may appear once`，或一致性測試指出 policy 允許該列。這證明 ground truth 的檢查會咬人。
- [ ] `python3 -c "from rlsentry.policy.load import load_config; load_config('target: http://x\ntest_users: [{name: user_a, password: hunter2SECRET\n')"`
      預期：ConfigError 只含 `line …, column …` 與錯誤種類，不含 `hunter2`（auditor F5，T-032）。
- [ ] 閱讀 `rlsentry/contracts/ground_truth.py:9-38`（計分與 lab 慣例）
      確認：FP 包含 ground truth 沒預料到的 confirmed finding；FPR 可由 `fp_safe`、`tn` 重現；新增 `safe_decided_ratio`，避免「全部回報 inconclusive」看起來像完美。
- [ ] 閱讀 `rlsentry/contracts/interfaces.py:41-52` 與 ADR-014 第 1、2、4 點，並**做出決定**：
      (a) audit 允許登入這一個 POST；(b) NFR-01 的資料庫 log 只計 PostgREST 角色的寫入，排除 GoTrue 寫入 `auth.*`；(c) ci 的寫入目前只允許 localhost。
      若你不同意任何一點，請寫在核准意見中，MS1 會依此調整。
- [ ] `python3 harness/spec.py "6"` 並看最後幾行
      預期：輸出停在 `db_url_env: SUPABASE_DB_URL`，看不到 `tables:`、`defaults:`。這是凍結 harness 的 bug（SPEC.md:342 的 YAML 註解被當成標題），只有你能修（auditor K5）。
- [ ] `git show origin/rlsentry-holdout:MS0/test_holdout_policy.py | sha256sum`
      預期：`d347875d5857eb9fb02883ad466f936f574a6a566c67407366c5a8e02b7eb0ba`；另一個 `.pyc` 是誤帶入的（PRODUCTION_LOG）。
- [ ] 開啟 `docs/reviews/MS0-high-risk.md` 中任一 compare 連結（例如 T-029）
      確認：diff 只含該 ticket 的檔案。可直接以此建立「僅供審查」的 PR。

## 4. 與 SPEC 的偏差與假設
- §8 L04 範例的 safe case 改為漏洞案例 L04-V2（ADR-011）。
- §8 safe_cases 允許 `expect: allowed`（C02-S1、L10-S3）（ADR-011 #5）。
- §8 case 鍵 `table:` 改名為 `target:`，並增加 schema、rows、policy 等欄位（ADR-009、ADR-014）。
- §6 Finding 增加 role、op；新增階段輸出模型；TablePolicy 增加 primary_key；所有模型禁止未知欄位（ADR-006、ADR-010、ADR-014）。
- §6 Op 不增加 execute：RPC 以 select 表示，且只用 GET／HEAD 呼叫（ADR-007、ADR-014）。
- §5 Safety 的「非 HEAD／GET 一律過閘門」加上唯一例外：測試帳號登入（ADR-014 #1，待你確認）。
- §2 ci（preview DB）暫不允許遠端寫入（ADR-014 #4，待你確認）。
- §12 D4：Firebase 列為未來工作（ADR-013）。

## 5. 已知限制
- Ground truth 只與自身的 policy 驗證過一致；與真實 Postgres／PostgREST 的一致性要到 MS1 的 lab 驗證測試才會檢查（auditor G2–G7 的假設都寫在 `plant` 與 ground_truth.py 的 lab 慣例中）。
- 所有 lab 表都使用 uuid 主鍵 `id`（O1）；L01 佔 32 個漏洞案例中的 12 個，recall 受它主導（O3）。
- 每格只有一個 outcome，混合範圍（public_rows_only）格子的語意延到 MS2 定義（K3）；UPDATE 新舊列都需允許的規則目前只寫在測試中（K4）。
- Probe 介面沒有 refresh token 與 DB 連線，L03 改 metadata 後換 JWT、L09 canary 清理延到 MS3 設計（F6）。
- 計分規則目前只有 docstring 與 BenchReport 鍵的測試；完整計分測試在 MS4 bench ticket。
- 背景派工時，`logs/events.jsonl` 的 `report` 事件記錄的是啟動中繼資料，不是 subagent 的回報內容（例如 `daa64dc1`）；回報摘要改記在 PRODUCTION_LOG。T-032 的 subagent 回報文字只有 "placeholder"，architect 直接檢查分支 diff 後才驗收。
- `spec.py` 的 §6 截斷（見第 3 段），implementer 讀不到 expected policy 的範例。

## 6. 阻擋與困難
- **無法建立 PR**：本 session 沒有 GitHub PR 工具（沒有 GitHub MCP，gh 只允許搜尋）。替代做法是推送 `review/T-xxx` 與 `review/T-xxx-base` 分支（高風險 ticket：T-012、T-015–T-022、T-029、T-030），並把 PR 說明寫在 `docs/reviews/MS0-high-risk.md`。milestone PR 請用 https://github.com/pitaya943/rlsentry/compare/main...claude/busy-darwin-asvox3 。若要由 architect 自動開 PR，需要在 environment 連接 GitHub MCP。
- **auditor 找到 P0**：L05 的漏洞在真實 Postgres 上不成立。已修正，但這說明 ground truth 只做自我一致性檢查不夠，MS1 必須先完成 lab 驗證測試。
- **一次驗收失敗**：T-026 第 1 次失敗。原因是 architect 把尚未有實作的新測試，留在回歸測試檔的工作區中。已改為獨立測試檔 `tests/policy/test_load_safety.py`（PRODUCTION_LOG）。
- **guard 誤判**：helper script 中的 `git add --` 被當成跨分支複製而擋下，已改寫。
- **stop budget 已耗盡**：上一個 session 留下的 stop 嘗試次數已達上限（logs/INCOMPLETE.md），本 session 開始時就是此狀態。
