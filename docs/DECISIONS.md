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

## ADR-005：PR 審查政策與高風險 ticket 判定規則
- 日期：2026-11-02 · Milestone：MS0 · 相關：STAGE0 核准意見、SPEC §11
- 背景：STAGE0 核准意見要求：(1) 每個 milestone 開 PR（session 分支 → main），核准後由人類 merge；(2) 高風險 ticket 各開一個僅供審查的 PR，附 file:line 逐段說明、驗證指令與預期輸出；(3) PR 與驗證清單加「阻擋與困難」一節；(4) 寫成 ADR。判定規則由 architect 提案。
- 考慮過的選項：
  1. 所有 ticket 都開 PR（缺點：MS0 就有十多個 PR，審查注意力被稀釋）
  2. 依「出錯時的後果」判定高風險，其餘只在 milestone PR 中審查（採用）
- 決定：符合任一條件即為高風險：
  1. 修改 `rlsentry/safety/**`（授權閘門、唯讀、遮罩、限速）
  2. 會發出非 HEAD／GET 請求、建立 DB 連線或寫入任何資料的程式（probe 寫入、植入、清理、M4）
  3. 處理 key、JWT、密碼，或決定輸出內容是否遮罩
  4. 決定「什麼算漏洞」：預期權限解析、差分、證據等級與嚴重度規則、benchmark 計分
  5. Ground truth（`lab/**/expected.yaml`）與植入漏洞的 lab migration
  6. 修改既有合約欄位（新增合約不算，它在 milestone PR 中整體審查）

  審查 PR 的做法：推送 `review/T-xxx`（ticket 分支 tip）與 `review/T-xxx-base`（該 ticket 的 merge-base），PR 由前者指向後者，因此 diff 只含該 ticket、且永遠不會被合併；PR 說明附 file:line 逐段說明、驗證指令與預期輸出。milestone PR 由 session 分支指向 `main`，只由人類 merge。
- 後果與風險：本 session 的工具沒有 GitHub PR 建立權限（沒有 GitHub MCP 工具，gh 只允許搜尋）。在權限補上之前，architect 只推送分支，並在驗證清單「阻擋與困難」一節提供可直接開 PR 的 compare 連結與預先寫好的 PR 說明檔（`docs/reviews/`）。MS0 的高風險 ticket：T-012（計分規則，第 4 類）、T-015–T-020（第 5 類）、T-021、T-022（第 4 類）。

### ADR-005 補記：審查政策改為「依後果分級＋依類別合併」（2026-11-03，人類於 MS1 審查期間決定，選項 A＋B）
- 背景：MS0–MS1 累積 36 個僅供審查的分支（MS0 11 個、MS1 25 個）；人類的審查與學習速度跟不上產出。
- 決定（自 MS2 起適用；MS0、MS1 已推送的分支保留不動）：
  1. **A 分級**：第 1 類（safety）與第 2 類（非 GET 請求、DB 連線、寫入）**逐張**審查，各自一個 review 分支。第 3、4、6 類照舊逐張推送，但在說明檔中標為「建議抽查」。第 5 類（ground truth 與 lab migration）**抽查** 2–3 個情境，其餘由 lab oracle 與變異測試把關。
  2. **B 合併**：同一個 milestone 中同一類別的抽查型 ticket，合成一個 review 分支 `review/<MS>-<類別>`（base 為該 milestone 第一張此類 ticket 驗收前的 main），說明檔列出每張 ticket 的 file:line 重點，以及建議抽查的情境。
  3. 每份 `docs/reviews/<MS>-high-risk.md` 開頭先列出「逐張審查」與「抽查」兩份清單，以及預估的閱讀時間。
- 人類的理由（Q1–Q4 摘要）：人工審查的主要價值在於強迫自己理解系統細節與 critical impact，而不只是抓錯；目前的錯誤都由自動檢查、subagent 回報或 auditor 抓到。
- 後果與風險：抽查可能漏掉 oracle 與 lab 共用同一個錯誤假設的情境（共模失效）。緩解方式：每個 milestone 至少有一項變異測試（故意弄壞 lab，確認 oracle 會失敗）列入驗證清單；auditor 審查時固定抽查 3 個情境。

## ADR-006：§6 資料模型的增補
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §6、§4、FR-12
- 背景：SPEC §6 規定改動欄位需 ADR。§6 只列模組交換的核心模型，沒有各階段的輸出容器與報告根物件。
- 決定：(1) `Finding` 增加 `role`、`op`：benchmark 以 (target, op, role, rule) 比對案例，而 key finding 沒有 probe 可推導；(2) 新增 `Profile`、`SEVERITY_RANK`、`ReconResult`、`DiscoveryResult`、`AccessMatrix`、`AuthorizationRecord`、`ScanReport`；(3) `finding_id()` 的格式凍結在合約中（sha256 前 16 碼）；(4) 所有模型 `extra="forbid"`；(5) `ProbeResult` 以驗證器強制「known_rows_checked == 0 不得為 allowed／denied」（適用所有操作，依 §6 原文）。
- 理由：把 SPEC 最重要的不變式（count = 0 不等於 denied）寫進型別，任何模組都無法繞過。
- 後果與風險：寫入探測必須把讀回的 canary 或植入列計入 known_rows_checked；可呼叫但不回傳已知列的 RPC 只能是 inconclusive。

## ADR-007：RPC 呼叫以 Op.SELECT 表示
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §6 Op、§8 L07
- 背景：§6 的 Op 只有四種，L07 需要表達「anon 呼叫 RPC 取得資料」。
- 考慮過的選項：1. 新增 `Op.EXECUTE`（缺點：改動 SPEC enum，expected policy 也要新增一個操作鍵）；2. RPC 呼叫視為讀取（採用）。
- 決定：RPC 一律以 `op: select` 表示「呼叫並取得資料」；expected policy 中以 RPC 名稱當作表名列出。
- 後果與風險：有副作用的 RPC（會寫入的函式）無法在 policy 中與讀取區分；MS2 只記錄 RPC 的可呼叫性與回傳的已知主鍵，不猜參數（SPEC §5 M2）。

## ADR-008：Rule catalog
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §5 M5
- 決定：`rlsentry/contracts/rules.py` 列出全部 rule id 與預設證據等級、嚴重度。SPEC 未明定、由 architect 決定的有：
  1. `USER_METADATA_ESCALATION`（L03）為 High：等同取得預期不可見的資料，與跨租戶寫入同級。
  2. `SENSITIVE_COLUMN_PUBLIC`（L10）為 Configuration warning／Review：列層級正確，是否應公開 email 只有人能判斷。
  3. view 洩漏（L06）沿用 `ANON_READ_OWNER_SCOPED`／`CROSS_TENANT_READ`，修補 SQL 依目標種類（view）選模板。
  4. 經 RPC 取得他人資料，anon 與使用者都用 `SECURITY_DEFINER_RPC_DATA`（Medium，SPEC 明列）。
  5. `ANON_READ_OWNER_SCOPED` 遇到敏感欄位升為 Critical（`escalates_to`），比對清單為 `SENSITIVE_COLUMN_PATTERNS`。
- 後果與風險：rule id 是報告格式的一部分，改名需 ADR；benchmark 要求 rule 完全一致才算 TP。

## ADR-009：Ground truth 格式的增補
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §8「每個情境的檔案」
- 背景：§8 的範例只有 cases 與 `splinter_expected`。lab-dev 需要知道要建什麼表、植入哪些固定主鍵；benchmark 需要把預期權限交給掃描器。
- 決定：expected.yaml 增加 `title`、`priority`、`plant`（植入說明）、`openapi`、`schema`、`rows`（固定主鍵，格式 `5ce0<S><NN>-…`，見 `row_pk`）、`policy`（與 rlsentry.yaml 相同格式的預期權限）、`warning_cases`、`discovery_cases`；case 增加 `id`、`kind`（access／key／storage）、`new_owner`、`precondition`、`profiles`、`severity`、`key_kind`。測試帳號固定為 `LAB_USERS`。
- 理由：ground truth 先於 lab 寫好並凍結，lab-dev 依它建置（MS1 驗證 lab 與它一致），掃描器只拿到 `policy`，看不到 cases。
- 後果與風險：`plant` 是自然語言，lab 是否真的照做由 MS1 的 lab 驗證測試把關。

## ADR-010：設定檔預設值
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §6、NFR-01、NFR-02
- 決定：`profile` 省略時為 `audit`（唯讀）；`authorized` 省略時為 false；設定檔不允許未知欄位。
- 理由：「預設唯讀」（CLAUDE.md、NFR-01）；拼錯的 policy 鍵若被默默忽略，會變成「沒有預期權限」而漏報。
- 後果與風險：使用者升級設定檔格式時，舊的未知欄位會讓掃描直接失敗（錯誤訊息會指出鍵路徑）。

## ADR-011：Benchmark 計分與 ground truth 撰寫規則
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §8、§9、NFR-06
- 決定（細節見 `rlsentry/contracts/ground_truth.py` 模組 docstring）：
  1. 格子 = (kind, target, op, role)。漏洞案例需 confirmed 且 target、op、role、rule 全部一致才算 TP。
  2. FP = 沒對上任何漏洞案例的 confirmed 漏洞 finding（含 ground truth 沒預料到的，列出交人工確認，不丟棄）；FPR 的分母是 safe cases。
  3. 同一格不得同時是漏洞與 safe／inconclusive；safe 與 inconclusive 每格只列一次。
  4. 對稱漏洞（A、B 都能做）兩個方向都列為漏洞案例；掃描器應對兩個測試帳號都測。
  5. safe case 可為 `expect: allowed`（例如 C02 anon 讀已發佈文章），偏離 §8「應判定為 denied 或 inconclusive」的字面說法，因為 FPR 必須涵蓋「合法公開被誤報」。
  6. `denied` 只能建立在某個測試帳號看得到或能植入的列上；沒人看得到的列只能是 inconclusive（L12 audit_log、C03、C04）。
  7. 寫入案例只在 dev／ci 計分；benchmark 以 dev 計分、另跑 audit 檢查唯讀與 inconclusive。
  8. P2 情境（L11）只列結果，不計入 §9 指標。
  9. key 案例以 `target` 標籤（`jwt:service_role`、`jwt:anon`…）比對，避免把 anon key 誤判為 secret 卻被算成 TP。
- 偏離 SPEC：§8 L04 範例的 safe case「user_a 讀 note_b1 為 denied」與該情境的 policy（只檢查已登入，對 A、B 對稱）矛盾，改列為漏洞案例 L04-V2。
- 後果與風險：rule 必須完全一致，rule 命名錯誤會同時造成 FN 與 FP；這是刻意的嚴格。

## ADR-012：相依套件與 mypy 設定
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §10、NFR-08
- 背景：雲端環境的 `mypy` 指令來自 uv 隔離環境，看不到專案的 pydantic，`mypy rlsentry` 誤報 import 錯誤。
- 決定：pyproject 的 `[tool.mypy] python_executable = "python3"`，讓 mypy 以 PATH 上的 python 解析套件；相依套件只加入當下需要的 pydantic、pyyaml，其餘（httpx、PyJWT、typer…）由第一個用到的 milestone 加入。
- 後果與風險：審查者的 PATH 上的 `python3` 必須裝有專案相依套件（`pip install -e .[dev]`）。

## ADR-013：D4（Firebase Security Rules）列為未來工作
- 日期：2026-11-02 · Milestone：MS0 · 相關：SPEC §12 D4
- 決定：不在本版本延伸到 Firebase。合約（RowScope、PostgREST 探測方式、ground truth）全部以 Supabase／PostgREST 為前提。
- 理由：Firebase 的授權模型（Security Rules、文件路徑）與列層級 RLS 差異大，需要獨立的 lab 與 ground truth；在 Supabase 指標達標前分散範圍不划算。
- 後果與風險：D2（Playwright）仍待 MS5 決定。

## ADR-014：依 MS0 auditor 審查修正合約與 ground truth
- 日期：2026-11-02 · Milestone：MS0 · 相關：NFR-01、NFR-03、FR-07、FR-08、§8、§9；auditor 報告（PRODUCTION_LOG 事件）
- 背景：auditor 指出合約與 ground truth 在真實 Postgres／PostgREST 上會出錯或讓後續 milestone 無法完成。
- 決定：
  1. **登入允許清單**（F1）：`POST /auth/v1/token?grant_type=password` 是任何 profile 都允許的唯一非 GET 請求，完全比對；audit 拒絕其餘所有寫入。否則 audit 無法取得 user_a／user_b 的 JWT，FR-08 不可能完成。
  2. **NFR-01 的資料庫 log 判準**（F2）：登入會讓 GoTrue 寫入 `auth.*`。MS1 的 lab 驗證只計算由 PostgREST 角色（anon、authenticated、authenticator）執行的寫入，必須為 0；GoTrue（supabase_auth_admin）的寫入另列，不計入。此判準在 MS1 寫成測試前由人類確認（驗證清單第 3 段）。
  3. **RPC 只用 GET／HEAD 呼叫**（F3、G3）：任何 profile 都不 POST 到 RPC；拒絕 GET 的函式為 inconclusive。lab 的 RPC 一律宣告 STABLE。
  4. **寫入只限 localhost**（F4）：暫採保守解讀；SPEC §2 的 ci（preview DB）是否允許遠端寫入，交由人類在 MS3 前決定。CLI `--profile` 與設定檔 `profile` 取較嚴者（audit > ci > dev）。
  5. **ConfigError 不引用檔案內容**（F5）：YAML 語法錯誤只回報行列與錯誤種類（T-031、T-032）。
  6. **TablePolicy.primary_key**（K1、K2）：expected policy 可指定主鍵欄位；沒有 OpenAPI 也沒有指定時，該格為 inconclusive，掃描器不猜 `id`。L07 的 RPC 與 L12 的表都已列出。
  7. **計分**（O4、O5）：BenchReport 加 `fp_safe` 與 `safe_decided_ratio`，FPR = fp_safe/(fp_safe+tn) 可由原始數量重現；「全部回報 inconclusive」不會被誤認為完美；key 案例以標籤與 rule 比對（修正 docstring 與 ADR-011 的矛盾）。
  8. **Lab 慣例**（G2、G4）：所有表、view 明確 GRANT 給 anon、authenticated，RPC 明確 GRANT EXECUTE；寫入探測用 `Prefer: return=minimal`，由應看得到最終狀態的身分讀回；anon 新增時把擁有者欄位設為測試帳號以便讀回（L01-V2、L09-V1）。
  9. **Ground truth 修正**：L05 加 `created_by` 並讓 SELECT policy 允許建立者讀取，否則轉移會被 Postgres 以 42501 擋下、漏洞不存在（G1）；L11 物件以 SQL 設定 `owner_id`（G5）；L12 寫明關閉 OpenAPI 的方法（G7）。
  10. **ground truth 隔離**（O2）：產品程式中只有 `bench/` 可以匯入 `rlsentry.contracts.ground_truth`（測試把關）。
  11. **已知列語意**（G6）：被拒絕的 INSERT 以「看得到的讀者確認 canary 不存在」算 1 個已知列。
- 未採納或延後：K3（每格只有一個 outcome，混合範圍的格子語意）、K4（UPDATE 新舊列都要允許的規則目前只在測試中）延到 MS2 設計 probe 時以 ADR 決定；O1（所有 lab 表都是 uuid `id`）與 O3（L01 佔 32 個漏洞案例中的 12 個）列為已知限制；F6（Probe 介面缺 refresh token 與 DB 連線）延到 MS3。
- 補記：ADR-009 也把 SPEC §8 範例的 case 鍵 `table:` 改名為 `target:`（因為也涵蓋 view、RPC、bucket）（G8）。

### ADR-014 補記：人類的決定（2026-11-03，於 session 中確認）
- #1 同意：audit 允許唯一一個非 GET 請求，即測試帳號登入。
- #2 同意：NFR-01 的資料庫 log 只計算 PostgREST 角色（anon、authenticated、authenticator）的寫入；GoTrue 寫入 `auth.*` 另列，不計入。
- #4 **改為開放**：ci 可以寫入遠端的 preview DB（SPEC §2）。規則（MS1 實作 `safety/mode.py` 時寫進合約，並另以 ADR 記錄欄位）：
  1. 只有 ci 可以寫入遠端；dev 仍只限 localhost，audit 一律不寫；
  2. 遠端主機必須列在設定檔新增的明確清單中（暫名 `write_hosts`），完全比對 host，不支援萬用字元；
  3. 必須同時符合 `authorized: true`（或 CLI 確認）；
  4. 寫入內容仍只限 canary 與植入列，並以讀回驗證、自動清理。
  最壞情況：使用者把正式環境的主機誤列進清單，ci 掃描就會在正式資料庫植入、修改、刪除測試列。緩解：清單必須逐一列出、report 開頭列出本次允許寫入的主機、清理失敗時 exit code 非 0。

## ADR-015：人類新增的流程規則：progress.html 與分支紀錄
- 日期：2026-11-03 · Milestone：MS0（審查中）· 相關：SPEC §11 紀錄與交付
- 背景：專案負責人要求：(1) 在每個 milestone 結束、每張關鍵 ticket 完成、以及每次暫停等待審核或提問時，維護一個列出已完成函式、其目的與結構的檔案；(2) 記錄分支如何合併、最新分支走到哪裡、哪些 active、哪些 finished。
- 考慮過的選項：
  1. architect 手寫（缺點：會與程式碼漂移，而且每輪都花 token）
  2. 只看 git log（缺點：看不出函式的目的、也看不出分支與 ticket 的對應）
  3. 由程式從權威來源產生（採用）
- 決定：
  - `docs/tools/progress.py` 產生兩個檔案：
    - `docs/progress.html`：(A) `rlsentry/**` 中每個公開函式與類別的結構（簽名、欄位、方法）、目的（docstring 第一段）、由哪張 ticket 加入、哪些測試檔涵蓋；(B) 分支現況（active、受保護、review-only、finished、未合併）與合併方向；
    - `docs/branch-log.md`：由 `logs/events.jsonl` 產生的 ticket 開始、驗收合併、驗收失敗時間表。
  - **何時執行**（architect 必須遵守）：每個 milestone 收尾（§4 第 5 步 push 之前）、每張高風險 ticket（ADR-005 的 6 類）驗收後、每次暫停等你審核或提問之前。執行後與其他文件一起 commit、push。
  - 每份驗證清單加一項：`python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md` 必須沒有差異（代表檔案是最新的）。
- 理由：產生的內容與程式碼必然一致，重跑即可驗證，也不需要 architect 記住要更新哪些地方。
- 後果與風險：「目的」只和 docstring 一樣好（CLAUDE.md 已要求 public 函式寫 docstring）；腳本 import 凍結的 harness（唯讀）；檔案是衍生資料，不要手改。CLAUDE.md 是凍結檔，本規則只記在此 ADR；建議專案負責人在 MS0 核准意見中重述，讓下一個 session 一定會讀到。

## ADR-016：harness/spec.py 的 code fence 解析缺陷（人類修正）
- 日期：2026-11-03 · Milestone：MS1 · 相關：SPEC §6、§11 Token 使用原則；MS0 核准意見；auditor K5
- 背景：`spec.py` 以「行首為 `#`」判斷標題，沒有略過 ``` code fence。SPEC.md:342-365 是 `rlsentry.yaml` 範例（YAML code block），其中 `# Expected access policy…`（SPEC.md:342）與下一行的 YAML 註解被當成標題，`spec.py "6"` 在 `db_url_env:` 就截斷，`tables:`、`defaults:`、`fail_on:` 與 `rlsentry init` 段落都讀不到。MS0 期間所有依規定用 `spec.py` 讀 §6 的 agent 都看到不完整的設定檔範例。
- 考慮過的選項：
  1. architect 修改 spec.py（不可行：harness 為凍結檔，hook 會拒絕）
  2. 在 ticket 中直接貼 SPEC 原文（違反 Token 規則 2，且只是繞過）
  3. 由人類修正凍結檔並 refreeze（採用）
- 決定：人類於 commit `ddedd60`（harness: refreeze）新增 `_heading_indices()`，略過 fence 內的行；`toc()` 與 `section()` 都改用它，並在 `harness/tests/test_harness.py` 加回歸測試。MS1 開始時已確認 `spec.py "6"` 輸出含 `tables:`、`defaults:`、`fail_on:` 與 `rlsentry init` 段落。
- 影響範圍：只影響 SPEC.md:342-365 所在的 §6「設定檔 `rlsentry.yaml`」小節（SPEC 中唯一含 `#` 註解的 code block）。MS0 的合約（`rlsentry/contracts/policy.py`）是 architect 讀 SPEC 全文撰寫的，已含 `tables`／`defaults`／`fail_on`，不受影響；受影響的是 MS0 implementer（T-021–T-023、T-032）可讀到的背景，但它們以合約 docstring 為唯一依據，且 holdout 通過，故不重做。
- 後果與風險：之後 ticket 引用 §6 可以直接要 implementer 用 `spec.py "6"`；若 SPEC 新增含 `#` 的 code block，修正後的解析已涵蓋。

## ADR-017：ci 可寫入遠端 preview DB 的 `write_hosts` 欄位
- 日期：2026-11-03 · Milestone：MS1 · 相關：SPEC §2、§5 Safety、NFR-01、NFR-02；MS0 核准意見 #4；ADR-014 #4 補記
- 背景：人類在 MS0 核准意見中把 ADR-014 #4 改為開放：ci 可寫入遠端 preview DB，但需明確清單、完全比對 host、需授權、只寫 canary 與植入列。
- 考慮過的選項：
  1. host 支援萬用字元（`*.supabase.co`）：方便，但一個字元就可能涵蓋正式環境（人類已否決）
  2. 以完整 URL 比對：連埠號、路徑都要一致，使用者難以正確填寫且沒有額外安全性
  3. 以 host（含明確埠號時連埠號）完全比對、大小寫不敏感（採用）
- 決定：
  1. `ScanConfig.write_hosts: list[str] = []`：每一項是裸 host（可帶 `:port`），不得含 scheme、路徑、`*`、空白；載入時轉小寫並去重。
  2. `require_write_allowed(profile, method, url, write_hosts=())`：GET／HEAD 一律放行；登入 POST 一律放行（ADR-014 #1）；其餘 audit 一律拒絕；dev 只允許 localhost（`localhost`、`127.0.0.1`、`::1`）；ci 允許 localhost 或 `write_hosts` 中完全相同的 host（URL 帶埠號時，清單項目為無埠號 host 或相同的 `host:port` 才算相符）。
  3. `authorized: true`（或 CLI 確認）由 `safety/gate.py` 在任何請求前檢查；寫入閘門本身不再重複檢查授權，但 `write_hosts` 非空時 `authorize()` 會把清單寫進 `AuthorizationRecord.write_hosts`，讓報告開頭列出本次允許寫入的主機。
  4. 「只寫 canary 與植入列、讀回驗證、自動清理、清理失敗 exit code 非 0」屬於 MS3（probe/seed、write、cleanup）與 MS6（exit code）的完成定義，於該 milestone 的 ticket 中引用本 ADR。
- 理由：host 完全比對讓清單內容一目了然；把清單寫入授權紀錄，使用者在報告第一屏就看得到 ci 這次可能寫到哪裡。
- 後果與風險：最壞情況是使用者把正式環境 host 列入清單，ci 掃描就會在正式資料庫植入、修改、刪除測試列；緩解只能是「明列＋報告揭露＋清理失敗即失敗」，工具無法分辨 preview 與正式環境。dev 不讀 `write_hosts`：設定檔即使列了遠端 host，dev 仍只能寫 localhost。
- 與凍結規則的關係：CLAUDE.md「寫入只在 lab mode、只在 localhost」描述的是開發期間的行為；本 ADR 改的是產品在使用者環境中的行為，依人類簽署的 MS0 核准意見。開發與測試期間仍只連 localhost：`write_hosts` 的測試只呼叫閘門函式、不發出任何網路請求。

## ADR-018：Lab 架構：單一本機 Supabase 專案、逐情境載入、以 oracle 驗證 ground truth
- 日期：2026-11-03 · Milestone：MS1 · 相關：SPEC §8、§9、NFR-01；ADR-009、ADR-014 #2 #8
- 背景：SPEC §8 每個情境有 migration、seed、frontend，benchmark「以 Supabase CLI 啟動該情境」。16 個情境的表名互相重複（notes、profiles…），不能同時載入同一個 schema。MS0 的 ground truth 只與自己的 policy 驗證過一致（auditor 在 L05 找到 P0），MS1 必須以真實 Postgres／PostgREST 驗證。
- 考慮過的選項：
  1. 每個情境一個 Supabase 專案，各自 `supabase start`（缺點：每個 ~50 秒、16 組容器、埠號衝突）
  2. 一個專案，每次 `supabase db reset`（缺點：會重啟服務，每次數十秒，逐案還原時無法接受）
  3. 一個專案常駐，`apply(id)` 以 SQL 清空 public schema、storage、auth.users 後載入該情境（採用）
- 決定：
  1. `lab/_shared/` 是唯一的 Supabase CLI 專案（`project_id = rlsentry-lab`，排除 studio、realtime 等不需要的服務）；介面在 `rlsentry/contracts/lab.py`，lab-dev 實作 `lab/_shared/labctl.py`。
  2. 驗證方式：architect 的 `tests/lab/oracle.py` 讀 expected.yaml，對執行中的 lab 逐案以原始 HTTP 驗證 `schema`、`rows`、每個 case 的 `expect`、key 與 discovery 案例；寫入案例以 service_role 讀回最終狀態判定，每個成功的寫入後重新 `apply()`，案例之間互不影響。oracle 是測試程式，不是掃描器：它看得到 ground truth 與 service_role key。
  3. 前端是手寫、模仿打包輸出的 `frontend/index.html` + `frontend/assets/app.js`，不跑 npm 建置。真實框架（Next.js、Vite、CRA）的 bundle 解析留給 MS5 M1 的 fixture。
  4. `log_statement = mod`、log 前綴含資料庫使用者；`db_writes_since()` 只回傳角色與指令種類，不保存值（NFR-03）；NFR-01 只計 `POSTGREST_ROLES`（ADR-014 #2，人類已確認）。
  5. 多個 process 共用一個 lab，以 `/tmp/rlsentry-lab.lock` 檔案鎖序列化。
  6. Storage 物件放在 `lab/<id>/storage/<bucket>/<path>`，在 migration 之後、seed 之前以 Storage API 上傳（Storage 的 HEAD 需要實際檔案，只寫 `storage.objects` 列不夠）。
- 理由：方案 3 讓單一情境載入在數秒內完成，oracle 才能在每個寫入案例後還原；ground truth 由獨立於掃描器的程式在真實服務上驗證，掃描器的錯誤與 ground truth 的錯誤不會互相掩蓋。
- 後果與風險：
  - 從 MS1 起，lab 測試是回歸測試的一部分：之後每次 `accept` 與 `make verify-milestone` 都需要 Docker 與 Supabase 映像（首次 ~1 分鐘拉取與啟動）。沒有 Docker 時 lab 測試會失敗而不是略過（CLAUDE.md 禁止 skip）。
  - 清空方式若漏掉某種物件（例如 role 層級設定），情境之間可能互相汙染；`apply()` 合約列出必須重設的項目，L12 的 `pgrst.openapi_mode` 已涵蓋。
  - 每個情境的 ticket 有 4 類檔案（migration、seed、index.html、app.js），超過「最多 3 個檔案」的指引；各檔都很小（合計 < 200 行），拆開反而讓同一情境由兩個 agent 寫。

## ADR-019：NFR-01 的資料庫 log 驗證改為「authenticator 記錄全部語句＋寫入關鍵字分類」
- 日期：2026-11-03 · Milestone：MS1 · 相關：NFR-01、SPEC §8（`log_statement = mod`）、ADR-014 #2、ADR-018
- 背景：T-061（L01）與 T-065（L05）的 lab-dev 回報：寫入確實生效，但 DB log 裡找不到 PostgREST 的寫入。architect 實測確認：PostgREST 把寫入送成 `WITH pgrst_source AS (INSERT …) SELECT …`，Postgres 依「外層」指令分類為 SELECT，所以 `log_statement = mod` 完全不記錄；pgaudit 的 session 模式也一樣，會把它分類為 READ。**SPEC 指定的驗證方式對它要防的寫入（PostgREST 寫入）是盲的**：audit 模式就算真的寫了，log 仍會顯示 0 次寫入。
- 考慮過的選項：
  1. 全域 `log_statement = all`（缺點：GoTrue、Storage 的大量讀取也進 log，雜訊大）
  2. pgaudit（缺點：session 模式同樣依外層分類；object 模式要逐表設定 audit role，且情境每次重建）
  3. `pg_stat_user_tables` 計數差（缺點：統計延遲數秒才刷新，無法可靠地「立即」判定；也無法歸屬角色）
  4. 只對 `authenticator`（PostgREST 的登入角色）設 role 層級 `log_statement = all`，再以 `WRITE_KEYWORD_RE` 在語句全文中找資料修改關鍵字（採用）
- 決定：保留全域 `log_statement = mod`（SPEC §8，涵蓋 DDL 與其他角色），另加 `ALTER ROLE authenticator SET log_statement = 'all'`；`db_writes_since` 回傳所有含寫入關鍵字的語句（合約 `rlsentry/contracts/lab.py` `WRITE_KEYWORD_RE`），不含純讀取。被 RLS 過濾成 0 列的 UPDATE／DELETE 仍算一次寫入嘗試（NFR-01 量的是「有沒有送出寫入」，比「有沒有改到資料」更嚴格）。
- 理由：歸屬仍由 log 前綴的資料庫使用者決定（ADR-014 #2 不變）；關鍵字分類以實測的 PostgREST 語句格式驗證，且 `tests/lab/test_shared.py` 同時測「寫入被抓到」與「讀取不被誤算」。
- 偏離 SPEC：§8「log_statement = mod 即可留下所有寫入」的前提不成立；改為上述組合。
- 後果與風險：關鍵字分類是文字比對；若未來 PostgREST 改變語句格式，`test_postgrest_writes_are_attributed_and_reads_are_not` 會失敗而不是靜默放過。字串常值中的關鍵字理論上可能造成誤報（多算寫入），方向是保守的。

## ADR-020：MS1 safety 稽核的處理（fail-closed、RPC 路徑正規化、授權綁定延到 MS6）
- 日期：2026-11-03 · Milestone：MS1 · 相關：NFR-01、NFR-02、NFR-04、NFR-09；ADR-014 #3、ADR-017；MS1 auditor part 1
- 背景：auditor 找到 1 個 P1、5 個 P2。
- 決定：
  1. **P2-1 fail-closed**：`profile` 不是 Profile 成員（字串 `"AUDIT"`、None）時一律拒絕，連 GET 也拒絕（原本會落到「localhost 允許」）。
  2. **P2-2 RPC 路徑**：先反覆 percent-decode 到穩定、轉小寫、合併連續斜線，再比對 `/rest/v1/rpc/`。Kong／PostgREST 是否會解碼並未實測；這裡採保守做法，假設它們會解碼。
  3. **P2-3 預設埠**：`write_hosts` 中的 `:80`、`:443` 項目載入時就報錯，因為 httpx 送出的 URL 不會含預設埠，這種項目永遠比對不到。
  4. **P2-4**：HTTP client `trust_env=False`（不讀 proxy 環境變數，NFR-09），也不保留 cookie。
  5. **P2-5**：`rps` 必須是有限正數。
  6. **P1-1（SafeClient 未綁定授權紀錄）延到 MS6**：唯一建立 SafeClient 的地方是 `pipeline.run_scan`，它在 `authorize()` 之後才建立。MS6 的 pipeline ticket 必須附兩個測試：(a) 靜態測試：`SafeClient(` 只出現在 `rlsentry/pipeline.py`；(b) 未授權時 `run_scan` 一個請求都不送出（以 MockTransport 計數）。
  7. **P2-6（登入 POST 會送到任何設定的目標）**：照 ADR-014 #1 的設計保留；登入的密碼只來自使用者自己設定的 test_users。
- 理由（第 6 點）：現在把建構子改成必須傳入 AuthorizationRecord，會讓已驗收的 `tests/safety/test_http.py` 與實作必須同時修改，否則兩張 ticket 都過不了驗收閘門。放到 pipeline 統一處理，加上靜態測試，同樣能保證「沒有授權就沒有連線」。
- 後果與風險：在 MS6 之前，任何新模組都可以不經授權就自建 SafeClient。MS2–MS5 的模組只接受由呼叫端傳入的 client，不自行建立。這條規則寫進各 milestone 的 ticket，並由 MS6 的靜態測試把關。

### ADR-019 補記：MS1 lab 稽核（2026-11-03）
- P1-5「RPC 內的寫入在 log 中看不到」**經實測不成立於掃描器的呼叫方式**：PostgREST 以唯讀交易執行 GET，VOLATILE 函式內的 INSERT 回 `25006 cannot execute INSERT in a read-only transaction`（HTTP 405）；STABLE 函式本身不能含 INSERT（`0A000`）。L07 `accounts` 列數維持 2。掃描器的 RPC 一律 GET／HEAD（ADR-014 #3、ADR-020 #2），所以 NFR-01 不受影響。觸發器只在寫入時執行，寫入本身已被記錄。
- oracle 強化（T-081）：被拒的寫入必須是 401／403／42501，或者 UPDATE／DELETE 得到 2xx 但被 RLS 過濾成沒有變化；讀取的錯誤一律算失敗，不算 denied；新增正向對照（policy 允許的身分必須看得到植入列）；預期範圍改由 oracle 直接讀 `gt.policy` 判定，不再匯入 `rlsentry.policy`。驗證方式：故意把 C04 改成 `USING (false)`、把 L05 的 RLS 關掉，oracle 都會失敗（C04：正向對照；L05：10 個 denied 案例全部失敗）。

## ADR-021：人類新增的流程規則：`docs/system_overview.html`
- 日期：2026-11-03 · Milestone：MS1（審查中）· 相關：ADR-015、ADR-005 補記；SPEC §11 紀錄與交付
- 背景：人類的審查與學習速度跟不上產出，要求 architect 維護一份以系統設計角度、可視化方式說明設計理念的總覽；每個 milestone 完成時，以模組化的視覺方式呈現完成的進度（只給 overview，細節由人類自己看 docs）。
- 與 ADR-015 的分工：`progress.html` 是由程式產生的「有哪些函式、分支在哪裡」（what），`system_overview.html` 是 architect 撰寫的「為什麼這樣設計、各部分如何互動、哪裡最容易出錯」（why／how）。
- 決定：
  1. `docs/system_overview.html` 是單一自包含檔（內嵌 SVG 與 CSS，不載入任何外部腳本或字型，離線可開），內容為繁體中文。
  2. 固定章節：一句話定位、系統架構圖（標示各模組完成狀態）、核心設計理念、一個請求的旅程（safety 層）、lab 與驗證架構、開發流程、milestone 進度地圖、本 milestone 的過程（ticket、失敗與由誰抓到）、最大風險、閱讀路線。
  3. **何時更新**：每個 milestone 收尾（§4 第 5 步 push 之前）。若某個 ADR 改變了架構圖上的任何一個方塊或箭頭，在同一個 commit 中更新圖。
  4. 每份驗證清單加一項：開啟 overview，確認「本 milestone」一節與架構圖的狀態色和實際一致。
- 理由：圖與理念是人類建立 mental model 的入口；用文字描述的 ADR 一多就難以看出彼此的關係。
- 後果與風險：overview 是手寫的，可能與程式漂移。緩解方式：狀態、數字一律引用 PRODUCTION_LOG 與 tickets；每個 milestone 由 architect 對照 `progress.html` 檢查一次。CLAUDE.md 為凍結檔，本規則只記在此 ADR，建議你在 MS1 核准意見中重述，讓下一個 session 一定會讀到。

## ADR-022：獨立驗證流程（本機防竄改＋GitHub Actions verify＋sha 比對）與 repo 內的變異測試
- 日期：2026-11-03 · Milestone：MS1 核准後 · 相關：ADR-005 補記、ADR-018、ADR-019、ADR-021；SPEC §11 模組關卡
- 背景：MS1 審查時發現四個環境問題：
  - 人類本機（Windows）沒有 Docker；lab 工具只支援 POSIX（`fcntl`、`/tmp`）。
  - Claude Code app 只能在 localhost 執行 shell 指令。
  - 另一個雲端 session 照「只執行 make」的提示，驗證了一個落後約 120 個 commit 的過期 clone，而且沒有安裝相依套件。
  - `workflow_dispatch` 會使用所選分支上的 workflow 檔。
  人類要求驗證必須在線上執行、結果不能經過 prompt 轉述。
- 決定（人類於 MS1 審查期間決定）：
  1. **三段信任鏈**：
     - (a) 本機 `host/review.sh` 第 1、2 步：同步與防竄改檢查，只需要 git。
     - (b) GitHub Actions `verify-milestone`：workflow 只放在人類控制的 `main` 上，`ref` 由輸入參數指定，權限 `contents: read`，log 印出受測 sha。
     - (c) 檢查 C：`git diff --stat <本機 sha> <Actions sha> -- . ':!logs'` 必須沒有輸出。
     - 簽章仍在本機。
  2. 每份驗證清單第 3 段第 1 項改寫為上述三步驟。不再使用「另開雲端 session 請 agent 執行」的做法。
  3. **變異測試放在 repo 裡，不放在 workflow**：
     - `tests/lab/test_oracle_mutations.py`：情境載入後以 SQL 製造缺陷，斷言 oracle **以預期的原因**失敗。訊息必須含指定的 case id 或 `positive control`，避免「意外失敗」被誤認為抓到缺陷（人類 Q3）。
     - `tests/lab/test_design_assumptions.py`：設計前提，例如 ADR-019 的 CTE 盲點。
     - 以上測試皆標記 `safety`。
     - 每個 milestone 的 holdout 都另附一組變異方式不同的版本。
     - 需要在合約中新增 `labctl.execute(sql)`（`query()` 維持唯讀）。
  4. 選擇性：MS4 之後再考慮每週排程一次的上游漂移檢查（最新的 Supabase CLI 與映像）。
- 已知限制（補記 MS1）：
  - lab 只能在 POSIX 系統執行（Linux、macOS、WSL2）。
  - 雲端新 session 的 clone 可能過期，任何驗證前都必須比對 sha。
- 後果與風險：
  - workflow 只有人類能改，所以穩定；隨每個 milestone 成長的變異測試由 architect 維護，靠驗收閘門、auditor、holdout 與 `safety` 標記制衡。
  - 若 architect 同時弱化測試與 oracle，只有 holdout 與人工抽查能發現。

## ADR-023：MS2 M2 Discovery 與 M3 讀取的設計
- 日期：2026-11-03 · Milestone：MS2 · 相關：SPEC §5 M2、M3；FR-04–FR-08、FR-10、FR-15；ADR-007、ADR-014、ADR-022
- 背景：SPEC 只說「已知主鍵的可見數」與「audit 以主鍵交集判定」，沒有定義已知列從哪裡來、一個 cell 的三態怎麼由計數決定、哪些 HTTP 狀態可以當成 denied。以下各點都在本機 lab 實測過（`tests/lab/test_design_assumptions.py`）。
- 決定：
  1. **OpenAPI 不區分 table 與 view**：L06 的 view 與 table 在 PostgREST OpenAPI 中有相同的 methods 與 `<pk/>` 標記，所以 M2 一律回報 `kind: table`（RPC 為 `rpc`），不回報 `view`；MS4 whitebox 有 DB 連線時可再細分。
  2. **bundle 推測與 OpenAPI 取聯集**：SPEC 寫「OpenAPI 關閉時改用 bundle」，本設計在 OpenAPI 可用時也加入 bundle 中出現、但 OpenAPI 沒列的名稱（`inferred`）。理由：PostgREST 預設只列出 anon 有權限的關聯，authenticated 才能用的表不會出現在 anon 的文件中。代價：不存在的名稱會多出 inconclusive 與 `INFERRED_TARGET` 提示。`supabase.storage.from('x')` 與 JS 內建物件的 `.from()` 不算目標。
  3. **一個讀取 cell 的判定**（`contracts/probe.py` 模組說明）：
     - 已知列：每位測試使用者用自己的 JWT 列出自己的主鍵（`<owner>=eq.<自己的 id>`，只取主鍵，最多 50 筆），有公開欄位時分成公開與非公開。這就是 SPEC 的「主鍵交集」；MS2 在所有 profile 都這樣做，MS3 為 dev／ci 加上植入資料。
     - 對被測角色，把已知列分成「預期不可見（forbidden）」與「預期可見（permitted）」；以 `HEAD … <pk>=in.(forbidden)` 加 `Prefer: count=exact` 取得可見數。
     - 可見數 > 0 → allowed（漏洞）；= 0 → denied；沒有 forbidden 已知列 → inconclusive。因此 C04 的 user_a（別人沒有資料）、C03（空表）都是 inconclusive，不會寫成安全。
     - 只有 200／206 且 Content-Range 有數字、且不超過查詢數，才下判定。401／403／404／400 一律 inconclusive：HEAD 沒有 body，無法分辨權限錯誤、JWT 錯誤與過濾條件錯誤（實測：不合法的 uuid 回 400）。代價：撤銷 GRANT 的表會是 inconclusive 而不是 denied（偏保守）。
     - permitted 列只用來產生提示：預期可見卻看不到 → `EXPECTED_ACCESS_DENIED`；anon 看得到含敏感欄位的公開列 → `SENSITIVE_COLUMN_PUBLIC`（L10-W1）。
  4. **規則對應**：RPC 讀到 forbidden 列 → `SECURITY_DEFINER_RPC_DATA`（任何角色，L07）；anon → `ANON_READ_OWNER_SCOPED`（欄位名含敏感字樣升為 Critical，bundle 推測的目標沒有欄位，不升級）；user → `CROSS_TENANT_READ`。
  5. **介面**：`Discover`、`Probe` 以 run 的 `SafeClient` 作為第一個參數，sessions 改為 `Sessions` 模型（token 不進 repr 與 JSON）。登入取得的 JWT 只解碼 `sub`（不驗簽、不新增 PyJWT 相依；M1 的 key 分類在 MS5 再決定）。
  6. **MS2 的寫入 cell**：一律 `not_tested`，audit 註明唯讀，dev／ci 註明 MS3 才實作；MS2 在任何 profile 都只送 GET／HEAD，以及允許的登入 POST。
  7. **`labctl.query()` 強制唯讀**（`default_transaction_read_only = on`），寫入只能透過新增的 `labctl.execute()`，且只供變異測試使用（ADR-022 #3）。
- 後果與風險：
  - audit 的已知列完全依賴擁有者欄位：找不到擁有者欄位的表一律 inconclusive（`NO_OWNER_COLUMN`）。
  - 每位使用者最多取 50 個主鍵：大表只抽樣，可見數仍是精確值，但只代表這 50 筆。
  - Storage（L11，P2）不在 MS2 範圍；計畫中尚無 Storage 探測的 milestone，列為已知限制。

## ADR-024：DB log 寫入分類排除字串常值（修訂 ADR-019，變更 MS1 的 labctl）
- 日期：2026-11-03 · Milestone：MS2 · 相關：ADR-019、ADR-022 #3、NFR-01
- 背景：MS2 的 lab 掃描測試（`tests/lab/test_scan_reads.py`）第一次在 audit 掃描中抓取 OpenAPI（`GET /rest/v1/`）。PostgREST 產生 OpenAPI 的 SQL 含 `has_table_privilege(c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, …')`，authenticator 記錄全部語句，ADR-019 的「全文任一處含寫入關鍵字」規則因此每次都回報一筆 `TRUNCATE`。實測：`GET /rest/v1/` 一次 → `[DbWrite(role='authenticator', command='TRUNCATE')]`；一般表的 GET → `[]`。
- 考慮過的選項：
  1. 測試中在 OpenAPI 請求之後才取 marker（缺點：把盲點藏起來，之後任何讀取 OpenAPI 的 NFR-01 檢查都會誤報）
  2. 在 `db_writes_since` 比對前，先移除單引號字串常值（採用）
  3. 只排除特定語句樣式（缺點：綁死 PostgREST 版本的 SQL 文字）
- 決定：WRITE_KEYWORD_RE 改為套用在「把所有 `'…'` 字串常值（`''` 為跳脫）替換成 `''` 之後」的語句上（`contracts/lab.py` 的 `SQL_STRING_LITERAL_RE`）。`E'…'` 反斜線跳脫不處理（PostgREST 不產生）。新增回歸測試：OpenAPI 讀取不得記成寫入，緊接著一筆內容含 `'TRUNCATE'` 字樣的真實 UPDATE 仍必須被記成 `UPDATE`。
- 為什麼不是 reopen MS1：MS1 範圍內的請求不會觸發此誤報（MS1 的測試從未抓取 OpenAPI），誤報方向是多報寫入（fail-closed），不會讓 MS1 的任何安全結論變成錯誤；這是 MS2 新流量暴露的設計限制。但此變更會修改 MS1 已核准的 `lab/_shared/labctl.py`，因此在 MS2 驗證清單第 4 段列為偏差，請人類確認；若你認為應以 reopen 處理，請在核准意見中註明，我會改走 reopen。
- 後果與風險：若有寫入語句完全包在字串常值中執行（例如 `EXECUTE 'INSERT …'` 的動態 SQL），authenticator 那一層不會再被計為寫入；PostgREST 不會送出這種語句，且被呼叫函式內的動態 SQL 原本就不會出現在 authenticator 的語句文字中（ADR-019 已知限制）。

### ADR-024 補記：MS2 auditor 的處理（2026-11-03）
- F1（P1）：原回歸測試的 PATCH 內容以 bind parameter 送出、記在 `DETAIL` 行，根本不會經過字串移除，因此是空轉的。改為新增純函式 `labctl.write_command(sql)`，並以 `tests/lab/test_shared_classify.py` 用合成語句直接測試（T-112 測試、T-113 實作）。
- F2：字串移除改為單次由左到右掃描單引號常值、雙引號識別字與 `$$` 字串（`SQL_QUOTED_RE`），所以識別字或 `$$` 內的單引號不能再開出假常值、吞掉後面的寫入關鍵字。
- F6：`db_writes_since` 改以 `RAISE LOG` sentinel 確認 log 已寫出，不再只靠 0.3 秒等待。
- F3–F5：變異測試同時比對 case id 與失敗片語；`query()` 唯讀測試比對 `read-only transaction`；掃描測試檢查所有 2xx GET，並移除不可能失敗的 HEAD body 檢查。

### ADR-023 補記：MS2 auditor 第 1 部分（2026-11-03）
- S1：RPC 只以 GET／HEAD 呼叫。新增設計前提測試：VOLATILE 函式（即使是 SECURITY DEFINER 且會寫入）對 GET 回 405；STABLE 函式內的 INSERT 在執行時被 Postgres 拒絕。因此 GET 呼叫 RPC 不會造成寫入。
- 已知限制（列入驗證清單第 5 段）：
  - S2：已知列的主鍵值會出現在 evidence curl 中；主鍵若是 email 這類個資，報告會帶出它（主鍵是 CLAUDE.md 允許記錄的唯一值）。MS6 報告階段再決定是否遮罩。
  - D1：沒有擁有者欄位的表，即使 anon 讀得到全部列，也只回報 inconclusive。
  - D2：`SENSITIVE_COLUMN_PUBLIC` 與嚴重度升級依表的所有欄位名判斷，沒有測試欄位層級的 GRANT。
  - D3：OpenAPI 只有 `/rpc/x` 時，bundle 的 `.from('x')` 會被略過。
  - FR-05 的「覆蓋率與未發現不代表安全」聲明屬於報告，延到 MS6；MS2 只提供 `openapi_available` 與每個目標的 confidence。

## ADR-025：驗證清單的四種標籤與「Codespaces 準備」（MS2 核准意見第 1 點）
- 日期：2026-11-05 · Milestone：MS3 · 相關：ADR-022、ADR-026、ADR-028；SPEC §11 模組關卡
- 背景：人類本機（Windows）沒有 Docker；GitHub Actions 只顯示通過或失敗，看不到細節。親手變異、`docker logs`、需要看輸出原文的項目，必須在 GitHub Codespaces 執行。簽章金鑰只能留在本機。
- 考慮過的選項：
  1. 不標註，由人類自己判斷每一項要在哪裡做（缺點：每次都要重新判斷，容易把需要看原文的項目當成 Actions 已涵蓋）
  2. 每一項固定標註執行地點與理由（採用，人類決定）
- 決定（自 MS3 起，每份驗證清單第 3 段）：
  1. 每一項只能有一個標籤：
     - 【Actions 涵蓋】：寫明涵蓋它的測試檔或檢查名稱，並註明「Actions 只證明通過，不顯示細節」。
     - 【Codespaces 必做】：Actions 會略過或無法顯示的項目（親手變異、docker logs、需要看輸出原文的測試）。附完整指令、預期輸出與還原方式。
     - 【Codespaces 必做變異】：見 ADR-026。
     - 【本機】：只有以下項目留在本機：防竄改檢查（`host/review.sh` 第 1、2 步，與本機的 harness-frozen tag 比對）、sha 比對、閱讀程式碼、做出決定、簽章。金鑰不得放進 Codespaces。
  2. 第 3 段開頭固定放「Codespaces 準備」：
     - 安裝指令；
     - 確認 `git rev-parse HEAD` 與本機驗證的 sha 一致。不一致時（中間多了只改 logs/ 的 commit），以排除 logs/ 的 diff 為空為準。
  3. 結尾固定提醒：不要從 Codespaces 提交或推送；測完先 `git restore .`，再刪除該 Codespace。
- 理由：標籤讓人類一眼看出「哪些只能信 Actions、哪些必須親眼看」；把信任邊界（金鑰、防竄改基準）固定在本機。
- 後果與風險：
  - Codespaces 的 clone 可能與本機驗證的 sha 不同，所以準備步驟必須先比對 sha。
  - Codespaces 預設映像不一定有 Supabase CLI。準備步驟必須列出安裝方式，並在 MS3 的清單中實測一次。
  - `vc-check` 不檢查標籤，標籤是否齊全由 architect 在撰寫時自查，並由人類審查。

## ADR-026：親手變異測試分級：必做變異與選做變異（MS2 核准意見第 2 點）
- 日期：2026-11-05 · Milestone：MS3 · 相關：ADR-022 #3、ADR-005 補記、ADR-025
- 背景：自動測試全部通過，只證明「測試認為沒問題」；親手弄壞一行、看測試失敗，才能證明測試真的在檢查那一行。人類的時間有限，所以要分出哪些一定要做。
- 決定：
  1. 「必做變異」：錯誤會造成下列任一後果時，就是必做：
     - 把不安全說成安全；
     - 讓判定錯誤；
     - 讓唯讀、遮罩、授權、NFR-01 偵測等防線失效。
     例如三態判定、safety、oracle、ground truth、計分。
  2. 清單中每一項必做變異都要寫明：改哪一個 file:line（改成什麼）、預期的失敗訊息（測試名稱與訊息片段）、它能抓到什麼錯誤、為什麼重要、如何還原（`git restore <file>`）。
  3. 人類必須在 Codespaces 實際做過、結果符合預期之後才簽章。每份清單把它列為「簽章前提」。
  4. 「選做變異」：只影響呈現或便利性，可以不做，標為選做。
  5. 每份清單至少一項必做變異；若某個 milestone 真的沒有，第 3 段要說明原因。
- 理由：必做變異針對的是「測試與實作同時錯、所有自動檢查仍然全綠」這種共模失效（ADR-005 補記）。
- 後果與風險：變異寫錯位置或行號漂移，人類會看到「沒有失敗」。所以 architect 在撰寫清單前要自己實際做一次，並以清單標頭的 sha 為準。

## ADR-027：worktree 規則：origin/main 必須是 HEAD 的祖先（MS2 核准意見第 4 點）
- 日期：2026-11-05 · Milestone：MS3 · 相關：ADR-022；MS2-v1 第 4 段「開發環境」
- 背景：MS2 時，main 上有人類新增的 workflow commit，它不是 session 分支的祖先，所以 `sync_worktree.py` 拒絕從 session 分支建立 subagent 的 worktree。architect 當時在本機執行了 `git remote set-head` 作為變通。人類已把 main 的 workflow commit 合併進 session 分支（`2c1ee1b`）。
- 決定：
  1. 每個 milestone 開始時（§0），確認 `git rev-list --count origin/main ^HEAD` 為 0，也就是 origin/main 是 HEAD 的祖先。
  2. 若不是，停下來回報人類，不得自行變通。禁止 `git remote set-head`，也禁止任何改寫 origin/HEAD 或分支的做法。
  3. MS3 開始時已確認：結果為 0，HEAD 為 `65ad96a`，且不是 shallow clone。
- 理由：worktree 的基準由人類控制的分支決定；agent 改本機 metadata，等於自己決定 subagent 從哪裡開始，人類看不到。
- 後果與風險：人類若之後又只在 main 加 commit，下一個 milestone 會在開始時停下來，需要人類先合併。

## ADR-028：`docs/verification_steps.html` 是固定的審查流程文件（MS2 核准意見第 6 點）
- 日期：2026-11-05 · Milestone：MS3 · 相關：ADR-021、ADR-022、ADR-025、ADR-026
- 背景：審查流程分散在多個 ADR 與核准意見中，人類需要一份照著做的步驟文件。
- 決定：
  1. `docs/verification_steps.html` 與 ADR-021 的 `system_overview.html` 地位相同：單一自包含檔，繁體中文，由 architect 維護。
  2. 審查流程有任何改變（包括 Codespaces 的步驟），都要在同一個 commit 中更新它，並在當次驗證清單中提醒人類。
  3. 本 ADR 的 commit 已依 ADR-025、ADR-026 更新該文件，加入 Codespaces 準備、四種標籤與必做變異的簽章前提。
- 理由：CLAUDE.md 是凍結檔；流程文件若與實際流程脫節，人類會照著過期的步驟簽章。
- 後果與風險：文件是手寫的，可能漂移。緩解方式：驗證清單第 3 段第一項引用它的步驟編號；若步驟不符，人類可直接要求修改。

## ADR-029：M3 寫入探測（dev／ci）：只動自己植入的 canary、以讀回驗證最終狀態、完整清理
- 日期：2026-11-05 · Milestone：MS3 · 相關：SPEC §5 M3 寫入、FR-09、FR-10；ADR-023、ADR-014、NFR-01
- 背景：SPEC §5 M3 要測 INSERT／UPDATE／DELETE，只在 dev／ci，audit 一律唯讀。關鍵 RLS 行為：`USING` 擋下的 UPDATE／DELETE 會回 2xx 但影響 0 列；只有違反 `WITH CHECK` 的 INSERT 會回錯誤。所以「沒報錯」不等於「寫入成功」，「回 200」不等於「有漏洞」。SPEC 要求以讀回的最終狀態判定，並自動清理 canary。以下設計都在本機 lab 驗證（`tests/lab/test_scan_writes.py`、`test_write_mutations.py`）。
- 考慮過的選項：
  1. 直接對 seed.sql 既有列做寫入探測（缺點：改到既有列後無法乾淨還原；跨租戶 DELETE 會破壞後續 case）
  2. 探測只動「掃描器自己植入的 canary 列」，每一列都由其擁有者負責清理（採用）
  3. 以 HTTP 狀態碼判定寫入成功（缺點：被 USING 過濾的 0 列 UPDATE 會被誤判為成功）
- 決定：
  1. **植入（seed_known_rows）**：探測前，每位測試使用者以自己的 token POST 一筆自己擁有的 canary 私有列（有 public_column 時再一筆公開列）。canary 值一律以 `rlsentry_canary_` 開頭（唯一會寫入的非主鍵值，且不含真實資料，CLAUDE.md）。沒有單欄主鍵或 owner_column 時不植入，該目標的寫入 cell 一律 not_tested。
  2. **只動自己植入的列**：寫入探測只對 seeded canary 或探測自己新增的 canary 動手，所以掃描器永遠是被改列的擁有者，可完整清理（SPEC 清理）。不碰 seed.sql 既有列。
  3. **探測哪些寫入（plan_writes）**：只送「預期政策禁止其最終狀態」的寫入（`forbidden_write` = `row_permitted` 為否）：anon 的任何寫入；使用者寫別人的 canary；使用者把自己的 canary 轉移給另一位（L05）。政策允許的寫入不送（不是漏洞）。
  4. **送出（send_write）**：一律 `Prefer: return=minimal`。理由：`return=representation` 會讓新列再過一次 SELECT policy，把真的有寫入的情況藏在 403 後面（auditor L09-G2、ADR-014 補記）。
  5. **讀回（read_back／write_outcome）**：由「應該看得到最終狀態的身分」（INSERT／transfer 用新擁有者；UPDATE 值改／DELETE 用原擁有者）以一次 HEAD count 檢查最終狀態，不下載列。初始狀態由建構固定（全新 canary pk／值、自己的列、剛植入的列），所以只讀 after。`write_outcome`：DELETE 最終不存在才算生效；INSERT／UPDATE 最終存在才算生效。
  6. **判定（write_cell）**：生效 → allowed（漏洞）；可信地未生效 → denied；送不出或讀回不可信 → inconclusive。因此 2xx 但讀回沒變 → denied，絕不 allowed。
  7. **規則（write_rule）**：anon → ANON_WRITE；user → CROSS_TENANT_WRITE。
  8. **清理（cleanup_seeded）**：每一筆 canary 由其擁有者 DELETE 並以 HEAD 確認消失；刪不掉的回報 CLEANUP_FAILED（非漏洞的 Review 提示，SPEC「刪不掉也是一種發現」）。
  9. **L03 提權（escalate_user_metadata／restore_user_metadata）**：使用者以 `PUT /auth/v1/user` 把自己的 user_metadata 設成 role=admin、重新登入取得新 JWT、重跑讀取；原本禁止卻變成可讀 → USER_METADATA_ESCALATION。結束後把 role 清掉還原。只寫測試帳號自己的 Auth 記錄。
  10. **audit 不變**：audit 的寫入 cell 維持 not_tested（AUDIT_WRITE_REASON），一個寫入請求都不送；寫入閘門（NFR-01）在 SafeClient 層再擋一次。
- 理由：選項 2 讓「完整清理」成為可達成的性質，而不是盡力而為；選項 3 會違反 SPEC 的核心判定規則。讀回身分用擁有者，對應 SPEC「以擁有者身分或 DB 讀回」。
- 後果與風險：
  - canary 列短暫存在於 dev／ci 的 DB；清理失敗會留下 `rlsentry_canary_` 列並回報 CLEANUP_FAILED。
  - L03 提權會短暫把測試帳號設成 admin；還原是盡力而為，中斷時測試帳號可能殘留 admin metadata（列入已知限制）。
  - owner_column 為 NULL 或非單欄主鍵的表無法植入，寫入一律 not_tested（偏保守）。
  - 完全包在字串中的動態寫入不在偵測範圍（沿用 ADR-024 限制）。

### ADR-029 補記：每個破壞性寫入探測使用各自新植入的 work row（2026-11-05）
- 問題：原設計讓寫入探測共用「每位使用者一筆預先植入的 canary」。一次成功的跨租戶 DELETE 或擁有者轉移會消耗該列，使後續以同一列為目標的探測讀回到錯誤的最終狀態（偽陽性），清理推理也不完整。這正好牴觸 MS3 的焦點（讀回驗證最終狀態、清理完整）。
- 決定：`plan_writes` 只依政策與身分列出要探測的寫入（不再依賴預先植入列）。每個 UPDATE／DELETE 探測在送出前，由 `seed_work_row` 以所需擁有者的 token 新植入一筆專屬 work row；INSERT 自建 canary；讀回緊接在每次寫入之後。`WritePlan` 以 `work_owner` 取代 `pk`／`row_owner`；`send_write`、`after_filter` 改以傳入的 work row。`seed_known_rows` 僅供 dev／ci 讀取已知列（SPEC「dev／ci 植入已知資料」，讓 C04 這類空資料情境在 dev／ci 可判定），不再餵給寫入探測。所有 canary（讀取植入、work、INSERT）都在最後由各自擁有者清理，殘留回報 CLEANUP_FAILED。
- 後果：每個情境的寫入探測會植入較多短命 canary（每個破壞性探測一筆），但彼此獨立、判定正確、清理完整。work row 植入失敗（擁有者無法 INSERT）時該寫入 cell 為 not_tested，不會誤判。
- 補充（T-133）：`plan_writes` 第 4 參數改為 `text_column: str | None`（真實可變文字欄位名稱，由 run 依 target 欄位挑選），value-change UPDATE plan 直接帶入 `WritePlan.text_column`；None 時略過該 plan。避免實作以佔位字串猜欄位名。

### ADR-029 補記 2：寫入判定依 HTTP 狀態分類、清理全涵蓋、讀取植入與可植入性限制（2026-11-05）
- 實測（dev 掃描全情境）發現並修正：
  1. **狀態分類**：INSERT 因非授權原因失敗（如 L01 `customers.email` NOT NULL，回 400）原本被判 denied（＝安全）。改為 `write_cell` 依狀態分類：401／403（政策、42501）→ denied；2xx → 以讀回判 allowed／denied；其餘（400／409／5xx／無回應）→ inconclusive。因此掃描器自己送不出有效寫入時只會「無法判定」，絕不誤報為安全。
  2. **清理全涵蓋**：`run()` 收集每一筆建立過的 canary（work row 與 2xx 的 INSERT canary）全部交給 `cleanup_seeded`；刪不掉的一律產生 CLEANUP_FAILED，不得悄悄遺留（L09 feedback 無 owner DELETE policy → 預期會有 CLEANUP_FAILED 與殘留 canary，屬正確行為）。
- **延後至 MS6 pipeline**（probe() 沒有可用的輸入）：
  - dev／ci 讀取植入（seed_known_rows，SPEC「dev／ci 植入已知資料」）：MS3 讀取沿用 collect_known_rows（既有列）；C04 在 dev 仍為 inconclusive。
  - L03 `USER_METADATA_ESCALATION`：提權後需以密碼重新登入取得新 JWT，但 `probe()` 只收到 token（不含密碼，NFR-03）。metadata.py（escalate／restore）已實作並單元測試（T-129），於 MS6 串接。
- **可植入性限制**：寫入探測以 canary 列植入（pk uuid、owner id、public bool、一個文字欄位）。有其他 NOT NULL 無預設欄位或非文字型別欄位（L01 `email` text NOT NULL、L05 `created_by` uuid NOT NULL）的表無法植入 → 該寫入 cell 為 not_tested／inconclusive（保守、不誤報）。完整覆蓋需由 OpenAPI 取得欄位型別，列為未來工作。

- 補充（T-138）：CLEANUP_FAILED 以 (target, owner) 去重（Finding.id = finding_id(target, role, op, rule)），每位擁有者一筆，報告不含殘留列數；實際殘留列在 dev／ci 可丟棄 DB 中。

- 補充（T-139）：寫入探測只對 kind=="table"；RPC／view 的寫入 cell 一律 NOT_TESTED（對 RPC 路徑送寫入會被閘門擋，ADR-014 #3）。變異測試以 `disable row level security` 植入（permissive `to anon` policy 在本 lab 讓 anon DELETE 仍影響 0 列，非可利用）。

## ADR-030：驗證清單的指令品質（MS3 核准意見第 2 點）
- 日期：2026-11-05 · Milestone：MS4 · 相關：ADR-025、ADR-026、ADR-028
- 背景：MS3-v1 第 7 項留下一條佔位指令（select leftover），人類照貼無法執行；多行 heredoc 在 markdown 清單中被縮排，結尾終止符失效，shell 卡在續行。
- 考慮過的選項：
  1. 照舊，由人類自行修正指令（缺點：審查時間花在除錯指令，且可能照錯誤的指令簽章）
  2. 每條指令都是 architect 在 lab 實跑過的成品（採用，人類決定）
- 決定（自 MS4 起，每份驗證清單）：
  1. 每一條要人類執行的指令，architect 必須先在 lab（與清單標頭相同的 sha）實際執行，清單附**真實**的預期輸出（可截取關鍵行，但不得改寫）。
  2. 不得有佔位指令或需要人類自行補完的片段（`<...>`、`...`、「自行替換」）。唯一例外是本機簽章用的金鑰路徑，須註明。
  3. 指令要能直接複製貼上，優先單行；多步驟以 `&&` 串接或分成多個 code block。
  4. 禁用 heredoc（`<<EOF`）與依賴縮排的多行輸入；需要多行 SQL 時改用 `psql -c "..."` 單行，或 `python3 -c` 單行。
  5. 變異的還原、測試資料的刪除、Codespace 的清理等步驟，寫出完整指令（例如 `git restore rlsentry/whitebox/correlate.py`），不得只寫「還原」。
- 理由：人類在審查時的注意力應該花在判斷結果，而不是修指令；實跑過的輸出也讓「結果不符」成為有意義的訊號。
- 後果與風險：撰寫清單的成本變高（每條指令都要實跑）；lab 狀態會影響輸出（例如上一個套用的情境），所以需要前置狀態的項目要把 `labctl.apply` 寫進指令本身。

## ADR-031：收尾與暫停前同步 progress.html／branch-log.md（補強 ADR-015；MS3 核准意見第 3 點）
- 日期：2026-11-05 · Milestone：MS4 · 相關：ADR-015、ADR-021、ADR-028
- 背景：ADR-015 已規定何時執行 `docs/tools/progress.py`，但 MS3 收尾時人類發現 progress.html／branch-log.md 落後於 system_overview.html。
- 決定：
  1. 每次 milestone 收尾（§4 第 5 步 push 之前）與每次暫停等待人類之前，architect 依序：更新 `docs/system_overview.html`（ADR-021）→ 執行 `python3 docs/tools/progress.py` → 在**同一個 commit** 提交三個檔案。
  2. 每份驗證清單保留自檢項：`python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md`，預期沒有輸出（若 accept 之後 harness 又寫入 logs/，以清單標頭的 sha 為準）。
- 理由：衍生文件只要重跑就一致，漏跑才是問題；把它和 push 綁在一起，就不需要記得。
- 後果與風險：branch-log.md 來自 logs/events.jsonl，harness 在 Stop hook 時仍會追加事件，所以清單標頭之後的事件不會出現在該版 branch-log.md，這是預期的。

## ADR-032：M4 Whitebox 設計：固定版本 splinter、唯讀連線、以 target 層級交叉比對
- 日期：2026-11-05 · Milestone：MS4 · 相關：SPEC §5 M4、FR-11、§8「splinter 必須實測」；ADR-005 第 2、4 類
- 背景：M4 要把靜態 lint（splinter）與 M3 動態實測對照。MS4 焦點：probe-only 案例必須真實；SECURITY DEFINER 只有在實測取得受保護資料時才是漏洞，否則是 Configuration warning。architect 已在本機 lab 以 psql 實跑固定版本 splinter 於 16 個情境（實測摘要：L01 `rls_disabled_in_public`、L03 `rls_references_user_metadata`、L05／L09 `rls_policy_always_true`、L06 `security_definer_view`、L07 兩個函式皆有 `anon_／authenticated_security_definer_function_executable`、L12 `audit_log` 有 `rls_enabled_no_policy`；L02、L04、L08、L10、L11、C01–C04 沒有 SECURITY 類 lint）。
- 考慮過的選項：
  1. 執行期從 GitHub 下載最新 splinter（缺點：結果隨上游變動，benchmark 不可重現；掃描時多一個對外連線）
  2. vendor 固定 tag 的 `splinter.sql`，以 sha256 鎖定（採用）
  3. 自己重寫 lint（缺點：失去「與官方 linter 對照」的意義）
- 決定：
  1. **固定版本**：supabase/splinter tag `2026.09.1`（commit `e74a9e3`），`rlsentry/whitebox/splinter.sql` 逐位元組相同，sha256 `d8d558ba…9349` 寫在合約；雜湊不符拒絕執行。授權為 PostgreSQL License（著作權聲明記在合約 docstring）。升級版本＝新 ADR＋重新實測所有情境的 `splinter_expected`。
  2. **唯讀**：連線帶 `default_transaction_read_only=on`，psycopg 也設 `read_only=True`；每個交易最後一律 rollback，M4 從不 commit。所以 M4 可在 audit 執行。已實測：此連線上 `CREATE TABLE` 回 SQLSTATE 25006。
  3. **SET LOCAL pgrst.db_schemas**：以參數化的 `set_config('pgrst.db_schemas', %s, true)`（等同 SET LOCAL）設定，避免字串組 SQL；schema 名稱先以 IDENT_RE 驗證。另設 `statement_timeout`。
  4. **只取 SECURITY 類別**：PERFORMANCE 等 lint（如 `auth_rls_initplan`）與授權無關，不參與比對。
  5. **比對粒度＝target（物件名）**：lint 與 M3 finding 都落在同一個 PostgREST 物件名上即為 `confirmed`；只有 lint → `lint_only`；只有實測 → `probe_only`。
  6. **SECURITY DEFINER**：`*_security_definer_function_executable` 且實測沒有在該物件取得受保護資料 → `SECURITY_DEFINER_EXECUTABLE`（config_warning，Low），**不是** confirmed；實測有取得資料 → 保留 M3 的 confirmed finding（`SECURITY_DEFINER_RPC_DATA` 等），標 `confirmed`，不再另加警告。
  7. **M4 絕不產生 confirmed finding**：只註記 M3 finding、另加非漏洞警告（LINT_ONLY、SECURITY_DEFINER_EXECUTABLE），所以 M4 本身無法改變 recall／precision／FPR。
  8. `pg_policies` 的條件式（DDL 文字，不含資料）放進 `ScanReport.policies`，由 MS6 報告呈現。
- 理由：固定版本＋雜湊讓 benchmark 可重現，也讓「splinter 沒報」成為可驗證的陳述；target 層級比對簡單、可解釋，且不需要理解每條 lint 的內部邏輯。
- 後果與風險：
  - target 層級比對可能過寬：例如 L05 `projects` 的 lint 是關於 UPDATE 的 `WITH CHECK (true)`，若同表另有 SELECT 漏洞也會標 `confirmed`。報告會附 lint 名稱，讓人判斷。
  - splinter 0024 依設計不檢查 SELECT `USING (true)`、0023 只檢查未啟用 RLS 的表（見 splinter 原始碼註解），所以 L02、L04 等成為 probe-only 是兩種工具回答不同問題，不是 splinter 的缺陷（SPEC §5 M4 解讀）。
  - 新增相依 `psycopg[binary]`（ADR-012 的「需要時才加」）。
