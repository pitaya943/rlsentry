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

## ADR-033：Benchmark runner 與計分的補充定義（coverage、0/0、splinter 狀態、probe-only、runtime）
- 日期：2026-11-05 · Milestone：MS4 · 相關：SPEC §8 執行方式、§9 評估指標；ADR-011、ADR-014
- 背景：ADR-011 定義了 TP／FP／FN／TN 與 FPR；SPEC §9 另要求 coverage、runtime（5／20／50 張表，50 張 < 60 秒）與 probe-only 案例（≥ 2 類），但沒有寫清楚分母、空集合與量測條件。
- 考慮過的選項（runtime 的量測條件）：
  1. dev profile、lab 用的高 rps（缺點：數字好看，但不是使用者會遇到的情況）
  2. audit profile、預設 rps 5（NFR-04）（採用：真實專案應以 audit 掃描，這是使用者實際會等的時間）
- 決定：
  1. **計分只用 dev**：metrics 只加總 `profile == dev` 且 `scored`（非 P2）的情境；audit 也逐情境執行，結果列在 `scenarios`，用來檢查唯讀（`db_writes == 0`，否則 exit 1）與 inconclusive，不計入指標。
  2. **coverage**：分母＝該 profile 計分的 ACCESS 案例（漏洞＋safe＋inconclusive）的相異格子 (target, role, op)；「測到」＝矩陣中結果為 allowed／denied／inconclusive；`inconclusive_ratio` 同分母。warning、key、storage 案例不算格子。
  3. **0/0 一律記 0.0**，旁邊必有原始數量（SPEC §9 統計上的誠實）；不使用 NaN（JSON 不合法）。
  4. **splinter 狀態**：情境的 `splinter_expected = reported`，若且唯若固定版本 splinter 有一條 SECURITY 類 lint 落在該情境某個 ACCESS／STORAGE 漏洞案例的 target 上；其餘（含只落在其他物件的 lint，如 L12 `audit_log`）為 `not_reported`。所有 SECURITY lint 仍逐條列在 `splinter_lints`。`expected.yaml` 由 architect 依實測填入（T-170），之後 bench 以 `splinter_match` 標出偏離。
  5. **probe-only 的「類」＝情境**：每個情境埋一種漏洞類型；某情境有 TP 且其 finding 的 correlation 為 `probe_only`，該情境即為一類 probe-only（附 case id 為證據）。
  6. **runtime**：`apply_synthetic(n)` 建 n 張 C01 型 owner-scoped 表，計時 discover＋登入＋probe（audit、rps 5、concurrency 4）；M4 與 lab 設定不計時。情境的 `runtime_s` 只計 M2＋M3。
  7. 情境執行使用 rps 50（lab 在本機且可丟棄）。
  8. **bench 的範圍**：MS4 的 bench 只串 M2＋M3＋M4；M1（L08 key，MS5）與 L03 提權（MS6，MS3 核准意見第 1 點）尚未串接，對應案例在 MS4 會誠實記為 FN，並在 BENCHMARK_REPORT 註明原因，不從分母剔除。
- 理由：每個比率都能由 JSON 裡的原始數量重算；量測條件寫死在合約常數，避免挑對自己有利的設定。
- 後果與風險：MS4 的 recall 會因 L03／L08 延後而低於 95% 目標，這是誠實的中間狀態；runtime 在 rps 5 下，50 張表可能超過 60 秒（每張表數十個請求），若如此會在報告中列為未達標並說明，不調高 rps 來湊數字。

## ADR-034：依 OpenAPI 欄位型別填入必填欄位，改善寫入植入覆蓋（MS3 核准意見第 1 點）
- 日期：2026-11-05 · Milestone：MS4 · 相關：ADR-029 補記 2（可植入性限制）、FR-04、FR-09；ADR-005 第 2 類
- 背景：MS3 的 canary 只帶 pk、owner、public、一個文字欄位，L01（`email text NOT NULL`）與 L05（`created_by uuid NOT NULL`）因此無法植入，寫入 cell 為 not_tested。architect 在 lab 實測 PostgREST 的 OpenAPI：`definitions.<table>.required` 列出 NOT NULL 且無預設值的欄位，每個 property 有 `format`（`uuid`、`text`…）。
- 考慮過的選項：
  1. 由 DB 連線（M4）讀 information_schema（缺點：M3 必須在沒有 DB 連線時也能運作，audit 使用者通常不提供 DB）
  2. 由 OpenAPI 的 required＋format 決定填值（採用）
  3. 隨機猜值並重試（缺點：請求數暴增，且 400 的原因無法分辨）
- 決定：
  1. `parse_openapi` 把 `required` 與 `column_formats` 放進 Target（新增欄位，預設空）。
  2. `fill_required` 只填「必填且呼叫端尚未設定」的欄位：uuid → 該列擁有者的 user id；文字 → `rlsentry_canary_…`；整數／數值 → 0；布林 → false；timestamp → 現在時間；date → 今天；json／jsonb → `{}`。
  3. 任一必填欄位型別不在上述範圍（enum、array…）→ 整列不送，cell 維持 not_tested（植入）或 inconclusive（INSERT），絕不誤報為 denied。
  4. 填入的值只有 canary 字串、擁有者自己的 id 與常數，不含任何真實資料（CLAUDE.md）。
- 理由：uuid 欄位在 Supabase 幾乎都是使用者參照（外鍵到 auth.users），policy 也常要求它等於 `auth.uid()`（L05 的 `created_by`）；填擁有者自己的 id 最可能通過合法的 WITH CHECK，因此「被拒」才代表政策真的擋住。
- 後果與風險：
  - uuid 欄位若是指向其他表的外鍵，植入會因外鍵失敗（400）→ 仍是 not_tested／inconclusive，不誤判。
  - 沒有 OpenAPI 的目標（L12、bundle 推測）沒有型別資訊，行為與 MS3 相同。
  - L01／L05 的寫入案例在 MS4 bench 若轉為 confirmed，T-170 會收緊 `test_scan_writes` 對它們的「無法植入」容忍。

### ADR-033 補記：空 lint 清單也是量測結果；audit 也執行 M4（2026-11-05，T-173／T-174）
- 第一次完整 benchmark 發現：L11 完全沒有 lint，`lints or None` 把空清單當成「沒跑」；audit 不跑 M4，使 L07-W1（profiles 含 audit）在 audit 顯示 warning_missing。
- 決定：`with_whitebox` 時一律記錄 lint（空清單＝splinter 沒有任何回報）；audit 也執行 M4（唯讀，ADR-032 #2）。最終 benchmark：16 個情境 dev 與 audit 的 `splinter_match` 全為 true，audit 的 PostgREST 寫入全為 0。

### ADR-034 補記：寫入探測的文字欄位依型別挑選（2026-11-05，T-171／T-172）
- 第一次完整 benchmark：L05-V1／V2 仍為 FN。原因：run.py 把「第一個非 pk／owner／public 欄位」當成文字欄位，L05 是 `created_by`（uuid），canary 字串寫入 uuid 欄位 → 400 → work row 植入失敗。
- 決定：`pick_text_column` 跳過 `column_formats` 記錄為非文字型別的欄位；沒有型別資訊的欄位仍可選（維持 MS3 行為）。修正後 L05 為 TP，`test_scan_writes` 移除 MS3 的「無法植入」容忍（L01／L05 現在必須被確認）。

## ADR-035：第一次完整 benchmark：splinter_expected 實測值、probe-only 類別與展示情境
- 日期：2026-11-05 · Milestone：MS4 · 相關：SPEC §8「splinter 必須實測」、§9 Probe-only 與展示情境；ADR-032、ADR-033
- 背景：SPEC 要求 `splinter_expected` 以 MS4 實測填入、probe-only 至少 2 類，並以實測選定展示情境。
- 決定：
  1. `splinter_expected`：L01、L03、L05、L06、L07、L09 為 `reported`；其餘 10 個為 `not_reported`（依 ADR-033 #4 的定義，固定版本 splinter 2026.09.1 實測）。`tests/lab/test_splinter_expected.py` 每次重跑實測並與 expected.yaml 比對；splinter 升版或情境改動時，必須重新實測並以 ADR 記錄，不得直接改值。
  2. Probe-only 類別：L02（SELECT `USING (true)`）、L04（只檢查已登入的跨租戶讀取），共 2 類；L12-V1 也是 probe-only，但其漏洞同為 SELECT `USING (true)`，不另計一類（見下方補記）。L02 與 L04 是 splinter 的設計範圍之外（0024 排除 SELECT；靜態 lint 不知道預期的擁有者範圍），不是 splinter 的缺陷。
  3. 展示情境：**L04**（SPEC §9 的首選候選，實測確認 splinter 無任何 SECURITY lint，RLSentry 以 Confirmed 證實 User B 讀到 User A 的列）。
- 理由：所有數值由程式實測，並有測試把關，ground truth 不會在無人察覺下漂移。
- 後果與風險：MS4 recall 為 29/32（L03 延後 MS6、L08 延後 MS5），未達 95% 目標；runtime 50 張表 70.7 s 未達 60 s 目標。兩者都在 BENCHMARK_REPORT.md 誠實列出，不調整計分或 rps 來湊數字。

### ADR-034 補記 2：INSERT 探測的其他 uuid 必填欄位填攻擊者自己的 id（2026-11-05，MS4 稽核 P1-1，T-175／T-176）
- 問題：原本 INSERT 以 new_owner（受害者）的 id 填其他 uuid 欄位。若政策是 `WITH CHECK (created_by = auth.uid())`，真正的攻擊者會把 created_by 填成自己；掃描器卻送受害者 id → 403 → denied，把可能存在的跨租戶寫入說成安全。
- 決定：actor 是有 id 的使用者時，其他 uuid 必填欄位填 actor 自己的 id；anon 沒有 id，維持 new_owner 的 id。owner 欄位不變（new_owner）。
- 理由：填值只影響請求能否通過 WITH CHECK；最終狀態以 pk 讀回判定，所以這個改變只會減少錯誤的 denied，不會產生錯誤的 allowed。
- 仍存在的限制：每個 plan 只嘗試一種填法；需要特定欄位組合（例如外鍵指向其他表）才能通過的政策，仍可能是 inconclusive 或 denied。稽核 P1-2（anon INSERT 送空字串 uuid）不成立：所有 INSERT plan 都有 new_owner。

### ADR-035 補記：probe-only 為 2 類，不是 3 類（2026-11-05，MS4 auditor 第 1 次派工的遲到報告）
- 問題：原本把 L12 算成第 3 類。L12 的漏洞是 `TO anon USING (true)` 的 SELECT policy（lab/L12_openapi_restricted/migration.sql:12），與 L02 同類；「OpenAPI 受限」描述的是目標怎麼被發現，不是漏洞類型（SPEC §9「漏洞類型」）。ADR-033 #5 的「類＝情境」定義在此過寬。
- 決定：probe-only 以漏洞類型計，MS4 為 2 類（L02、L04），6 個案例（含 L12-V1）；仍達 ≥ 2 類目標。bench JSON 的 `probe_only` 欄位維持逐情境列出（原始資料），類別的歸併在 BENCHMARK_REPORT 說明。

### ADR-030 補記：每條指令都是獨立的 code block（2026-11-05，人類於 MS4 審查前要求）
- 決定（自 MS4-v1 起，之後每份驗證清單）：第 3 段中所有要人類執行的指令，一律放在獨立的 fenced code block（```bash），一個 block 一條單行指令，讓人類直接按 Copy 執行，不需用滑鼠選取。變異指令與其還原指令（`git restore …`）分成兩個 block。行內反引號只用於檔名、預期輸出與測試名稱，不用於要執行的指令。
- 佔位例外：只有本機 sha 與 Actions sha（只有人類知道）以 `LOCAL=請貼上本機sha` 這類變數放在 block 開頭，其餘不得有佔位。

## ADR-036：M1 Recon 設計：只抓同源、依真實 bundle 量測的擷取規則、key 分類與遮罩
- 日期：2026-11-06 · Milestone：MS5 · 相關：SPEC §5 M1、FR-01–03、NFR-03、§9 測試層級；ADR-011 #9、ADR-023、ADR-032
- 背景：M1 要從目標網站的 HTML 與 JS chunk 找出 Supabase URL 與 key，並把 service_role／secret 判為 Critical、anon／publishable 判為正常。architect 在派工前以 Next.js 15.5（pages router、static export）、Vite 8、Create React App 5 各建一個真實專案（皆用 supabase-js 2.119），產出放在 `tests/recon/fixtures/`，並以草稿程式實測規則（未提交）。實測發現：(1) 壓縮後的 createClient 是 `(0,t(8033).UU)("https://…","eyJ…")`，看不到 `createClient(` 字樣；(2) Vite 8 的字串是反引號；(3) source map 內嵌 supabase-js 的文件範例（`https://xyzcompany.supabase.co`、`your-publishable-key`）；(4) Next.js 的延遲 chunk 只出現在 `_buildManifest.js` 與 `l.e(43)`，CRA 的延遲 chunk 只出現在 webpack 的 chunk map；(5) phoenix 的常數 `base64url.bearer.phx.` entropy 3.52。
- 考慮過的選項：
  1. 只掃 HTML 引用的 script（缺點：漏掉延遲載入的 chunk；Next.js 的 admin 頁、Vite 的 lazy route 正好是最容易藏 service_role 的地方）
  2. 依框架的已知結構補抓（`_buildManifest`、`import()` 路徑、webpack chunk map、source map 註解），只抓同源（採用）
  3. 無頭瀏覽器執行前端（見 ADR-037，不採用）
- 決定：
  1. **只抓同源**：只對與 target 相同 scheme、host、port 的 URL 發 GET，不帶任何 header（不送 apikey／Authorization／cookie）；跨源的 script（CDN）列入 `chunks_skipped`，不請求。理由：CLAUDE.md 只允許連線到使用者授權的目標；CDN 不屬於授權範圍。
  2. **範圍上限與誠實揭露**：最多 200 次請求、單檔 10 MB；超過、非 200、轉址（不跟隨）、SPA fallback 回傳 HTML 都列入 `ReconResult.chunks_skipped`（新增欄位）並附原因。只依檔案中的 `sourceMappingURL` 或 `SourceMap` header 抓 map，不盲猜 `<url>.map`（每個 chunk 多一個請求，且常是 404）。
  3. **chunk 路徑**：字串常值（'、"、`）中的 `./x.js`、`/x.js`、含 `/` 的相對路徑（`static/chunks/…`、`assets/…`）；後者相對於 public path（路徑含 `/_next/` 時為 `…/_next/`，否則網站根目錄）。webpack chunk map 支援兩種形式（CRA 的 `{id:"hash"}` map、Next.js 的單一 hash＋`.e(id)`）。非根目錄的 public path、其他 webpack 形式列為限制。
  4. **URL 擷取**：以「URL 常值緊接著 key 形狀常值（JWT 或 sb_ key）」找 createClient 的兩個參數（也涵蓋自訂網域與本機 lab），其次 `https://<ref>.supabase.co|in`；建置檔（html／js）優先於 map 內的原始碼，避免把 supabase-js 文件範例當成目標。
  5. **key 擷取與分類**（FR-03）：JWT 以不驗簽方式解碼 payload，只保留 `role`、`ref`、`exp`（`sub`、`email` 是使用者資料，丟棄）。`anon` → publishable（不產生 finding）；`service_role` → secret（SECRET_KEY_IN_BUNDLE，Critical）；其他 role（如 `authenticated`、`supabase_admin`）與無法解碼的 JWT → unverified（UNVERIFIED_KEY，Configuration warning，交人工判斷）。`sb_publishable_` → publishable；`sb_secret_` → secret。其他字串只有在 key 語境（屬性或變數名含 apiKey、secret、token、anon_key、service_role_key 等）且長度 24–512、含數字與字母、entropy ≥ 4.0 時才列為 unverified；sb_ key 的後段 entropy 須 ≥ 3.0（排除 `sb_publishable_xxxx` 範例）。
  6. **標籤**：`KeyFinding` 新增 `label`（`jwt:<role>`、`sb_secret`、`sb_publishable`、`unverified`），即 key finding 的 `target`，與 ground truth 的 `KEY_TARGET_RE` 相同（ADR-011 #9），讓「anon 被誤判為 secret」不可能被算成 TP。同一標籤只產生一個 Finding；每個出現位置各有一筆 KeyFinding（只有遮罩值）。
  7. **M1 finding 不經過 M4 correlate**：key 的 target 是標籤不是資料庫物件，交給 correlate 會被標成 `probe_only`，使 probe-only 類別被灌水。bench（與 MS6 pipeline）先對 M3 finding 做 correlate，再附上 M1 finding。這改動 MS4 的 `bench/run.py`（整合 M1 的必要步驟，不是 MS4 的缺陷；MS4 的計分與 correlate 對 MS4 輸入的行為不變）。
  8. **遮罩**（NFR-03）：原始 key 只存在記憶體（`Candidate`、`ReconOutput.anon_key`，repr 皆遮罩；`FetchedFile.text` 不進 repr）。報告只有 `KeyFinding.masked`（前 6 後 4）。`ReconOutput.anon_key` 供 MS6 pipeline 在設定檔沒有 key 時給 M2／M3 使用。
  9. **介面**：`Recon` 改為 `recon(client, target_url) -> ReconOutput`（ADR-023：送請求的階段第一個參數是 SafeClient）。
- 理由：所有規則都由真實框架產出驗證過（fixture 測試），而不是只在自寫範例上有效（SPEC §9）；同源限制把 M1 的網路範圍綁在授權目標上。
- 後果與風險：
  - 動態組字串、執行期由 API 下發的 key、非根目錄 public path、其他 webpack 形式會漏掉；報告以 `chunks_scanned`／`chunks_skipped` 揭露範圍，不宣稱完整（SPEC §5 M1 限制）。
  - `supabase_admin` 等高權限 role 的 JWT 只被列為 unverified（Low），不是 Critical；人工確認時應視為嚴重。
  - generic 規則依 key 語境；名稱被壓縮成無意義的屬性時（`{a:"…"}`）不會被擷取。
  - bench 的 L12 等情境改用 recon 實際抓到的 bundle 做 M2 推測；recon 漏抓會直接顯示為 FN（這是刻意的端到端檢查）。

## ADR-037：D2：不支援無頭瀏覽器抓動態 chunk（列為未來工作）
- 日期：2026-11-06 · Milestone：MS5 · 相關：SPEC §12 D2、§5 M1 限制、§5 Safety、NFR-01、NFR-04
- 背景：SPEC §12 D2 要 architect 決定 M1 是否以 Playwright 等無頭瀏覽器執行前端，以抓到只在執行期才載入的 chunk。
- 考慮過的選項：
  1. 預設使用無頭瀏覽器（優點：抓到執行期載入的 chunk 與執行期下發的設定；缺點見下）
  2. 選配旗標 `--browser`（缺點同上，只是預設關閉）
  3. 不支援；以靜態抓取＋框架結構補抓（ADR-036），並在報告揭露範圍（採用）
- 決定：MVP 不支援無頭瀏覽器；列為未來工作。若日後加入，必須以 request interception 讓瀏覽器的每個請求都經過 SafeClient（同源、限速、User-Agent、寫入閘門），並另寫 ADR。
- 理由：
  1. **安全邊界**：瀏覽器會執行目標的 JavaScript，JS 會自行對任意主機（API、第三方分析、CDN）發請求，甚至 POST；這些流量繞過 SafeClient 的寫入閘門、限速與 User-Agent（SPEC §5 Safety、NFR-01、NFR-04），也可能連到授權範圍外的主機（CLAUDE.md、SPEC §7）。audit profile 承諾「0 次寫入」，執行目標程式碼就無法保證。
  2. **量測**：三個真實框架 fixture 中，所有延遲 chunk（Next.js 的頁面與 dynamic import、Vite 的 lazy route、CRA 的 webpack chunk）都能由靜態結構找到（`tests/recon/test_recon_fixtures.py`）。
  3. **成本**：瀏覽器二進位檔數百 MB，CI（GitHub Action）冷啟動時間大增。
- 後果與風險：只在執行期組出的 chunk URL、由 API 下發的 key、登入後才載入的頁面不會被掃到。報告列出 `chunks_scanned`／`chunks_skipped`，使用者可據此判斷覆蓋範圍；SPEC §5 M1 已聲明結果不保證完整。

### ADR-036 補記：報告中的 URL 一律經 report_url；userinfo 不算同源；KeyFinding 一致性（2026-11-06，MS5 稽核 S1–S3、S6）
- 問題（P1，S1）：合約只要求 `chunks_skipped` 遮罩；`chunks_scanned`、`KeyFinding.source_file`（含 source map 內由目標提供的 source 名稱）原樣寫進報告。同源、回 200 的 `<script src="/a.js?k=<sb_secret…>">` 會把完整 key 放進 JSON。S2：`mask_text` 只遮 JWT 與 sb_ 格式，`?apikey=AIza…` 這種其他格式的 token 不會被遮。S3：`http://u:p@<目標>/x.js` 通過同源檢查，httpx 會把 userinfo 變成 `Authorization: Basic`，違反「不送任何憑證」。S6：`KeyFinding` 不檢查 kind 與 label 是否一致、`masked` 是否真的遮罩。
- 決定：
  1. 新增 `links.report_url`：報告中的每個 URL（含 `<url>#<source 名稱>`）都經過它——query string 換成 `?…`（不論格式都不寫出）、移除 userinfo、其餘再 `mask_text`。`chunks_scanned`、`chunks_skipped`、`KeyFinding.source_file` 都用它。
  2. `same_origin`：帶 userinfo 的 URL 一律不是同源（列為 cross-origin，不請求）。
  3. `KeyFinding` 加 validator：`jwt:anon`／`sb_publishable` 必須是 publishable，`jwt:service_role`／`sb_secret` 必須是 secret，其他標籤必須是 unverified；`masked` 必須含 `****`。
- 後果：報告少了 query string（掃描範圍仍可辨識到檔案路徑）；這是刻意的取捨，因為 query string 是 token 最常出現的位置。
- 未處理（P2，列入已知限制或 MS6）：S4 `supabase_url` 來自目標的 bundle，惡意 bundle 可讓 M2／M3 把 anon key 與探測送往別處——MS6 pipeline 必須把它顯示給使用者確認或要求設定檔提供（已記入 PLAN 的 MS6 表）；S5 大檔先完整下載才檢查大小；generic key 偵測依 key 語境，名稱被壓縮時會漏掉。

## ADR-038：明確的高權限 JWT role 判為 secret（MS5 核准意見第 4 點，選項 B）
- 日期：2026-11-06 · Milestone：MS6 · 相關：FR-03、SPEC §5 M5、ADR-036 #5
- 背景：MS5 只把 `service_role` 判為 secret，`supabase_admin` 等其他 role 列為 unverified（Low）。人類選 B：明確的高權限 role 也必須是 Critical。
- 考慮過的選項：
  1. 手寫一份「看起來很危險」的 role 清單（缺點：主觀，難以審查）
  2. 以實測定義：stock Supabase 專案中 superuser 或 BYPASSRLS 的 role（採用）
- 決定：`contracts/recon.SECRET_JWT_ROLES` = 在 lab（Supabase CLI 3.0.0）實測 `SELECT rolname FROM pg_roles WHERE rolsuper OR rolbypassrls` 的結果：`service_role`、`supabase_admin`、`postgres`、`supabase_etl_admin`、`supabase_read_only_user`。這些 JWT → `secret` → `SECRET_KEY_IN_BUNDLE`（Confirmed、Critical）；rule catalog 的說明改為「service_role／secret key 或其他高權限 JWT（supabase_admin、postgres 等）出現在前端」。沒有新增規則：SPEC 的 Confirmed 條件「secret key 出現在前端」已涵蓋。`authenticated` 與其他 role 仍是 unverified；`anon` 仍是 publishable，不產生 finding。`KeyFinding` 的一致性 validator 依同一集合檢查 kind。
- 理由：「會繞過 RLS」是可驗證的定義，與 RLSentry 的威脅模型一致；`classify` 直接引用合約常數，所以改常數即改行為（原 T-210 併入 T-200）。
- 後果與風險：Supabase 新增高權限 role 時需要重新實測並更新常數（新 ADR）；`postgres` 等 role 的 JWT 不一定能被 PostgREST 使用，但它證明簽發者持有 JWT secret，仍應視為 Critical。

## ADR-039：SECURITY DEFINER 規則只由 M4 判定；依（物件, 角色）抑制警告（MS4 核准意見第 5 點 (a)(b)）
- 日期：2026-11-06 · Milestone：MS6 · 相關：SPEC §5 M4 解讀、§5 M5 嚴重度、ADR-032 #6–#7
- 背景：(a) 某物件只要有任一角色取得資料，其他角色的 SECURITY DEFINER 警告就被抑制；(b) M3 對所有 RPC 的越權讀取都標 `SECURITY_DEFINER_RPC_DATA`，但 M3 無法知道函式是不是 SECURITY DEFINER。
- 考慮過的選項（b）：
  1. 新增規則 `RPC_READ_BEYOND_SCOPE`（缺點：多一條規則，報告與 ground truth 都要改，而且它和表的越權讀取是同一件事）
  2. M3 一律依角色給規則（anon → ANON_READ_OWNER_SCOPED，使用者 → CROSS_TENANT_READ）；M4 在 splinter 證實該物件是「該角色可執行的 SECURITY DEFINER 函式」時改標為 `SECURITY_DEFINER_RPC_DATA`（採用）
- 決定：
  1. `rules.read_rule` 不再看 target_kind。
  2. `correlate`：proven 的 SELECT finding（ANON_READ_OWNER_SCOPED／CROSS_TENANT_READ）所在物件，若有涵蓋其角色的 `*_security_definer_function_executable` lint（anon lint → anon；authenticated lint → user_a、user_b，`DEFINER_LINT_ROLES`），改標 `SECURITY_DEFINER_RPC_DATA`（Medium，SPEC §5 M5），id 依新規則重算。
  3. SECURITY_DEFINER_EXECUTABLE 警告依（物件, 角色）判斷：只有該 lint 涵蓋的角色中有 proven finding 時才抑制。LINT_ONLY 仍只在物件上完全沒有 proven finding 時產生。
- 理由：只有能證明的事才寫進規則名稱；M4 本來就負責「與 splinter 對照」。
- 後果與風險：沒有 DB 連線（無 M4）時，L07 型漏洞的規則是 ANON_READ_OWNER_SCOPED（High）而不是 SECURITY_DEFINER_RPC_DATA（Medium）：嚴重度較高但仍是正確的「讀到不該讀的列」。`tests/lab/test_scan_reads.py` 改為先經 M4 再比對 L07 的 ground truth。這修改了 MS4 的 M4 行為（已核准），屬於核准意見要求的修正，不 reopen。

## ADR-040：同一身分的已知主鍵合併為單一請求（MS4 核准意見第 2 點）
- 日期：2026-11-06 · Milestone：MS6 · 相關：FR-06、NFR-04、ADR-023 #3、ADR-033 #6
- 背景：每個（目標, 角色）原本送兩個 HEAD count（「不該看到的已知列」與「應該看到的已知列」各一），50 張表在 audit、rps 5 需 70.7 s。
- 考慮過的選項：
  1. 調高預設 rps（人類禁止）
  2. 省略「應該看到」的計數（缺點：失去 EXPECTED_ACCESS_DENIED、SENSITIVE_COLUMN_PUBLIC 提示）
  3. 一個 `GET ?select=<pk>&<pk>=in.(全部已知主鍵)&limit=n`，回應只含主鍵，在本機拆回兩個計數（採用）
- 決定：`probe.visible_pks` + `observation_counts`。回應中出現查詢集合以外的主鍵、非 200／206、非 list 等一律視為不可信（total None → inconclusive），保留 ADR-023 #3 的「過濾沒套用就不可信」檢查。只下載掃描器本來就知道的主鍵（不下載資料，NFR-03／CLAUDE.md）。
- 實測（派工前，草稿程式）：audit、rps 5、concurrency 4、50 張 C01 型表：**50.6 s**（原 70.7 s）；請求數由每表 7 個降為 5 個。
- 後果與風險：讀取改用 GET 而不是 HEAD；`tests/probe/test_run.py` 的 HEAD 斷言改為 `<= {GET, HEAD}`，新測試斷言每個角色只有一個請求。

## ADR-041：遠端寫入被閘門拒絕時，寫入 cell 為 inconclusive（MS3 核准意見第 1 點）
- 日期：2026-11-06 · Milestone：MS6 · 相關：NFR-01、ADR-014 #4、ADR-017、ADR-029
- 決定：dev 對遠端主機、或 ci 對不在 `write_hosts` 的主機寫入時，SafeClient 閘門在送出前拋 `WriteRefused`。probe 攔下後，該表所有寫入 cell 為 INCONCLUSIVE（reason 以 `WRITE_REFUSED_REASON` 開頭，附閘門訊息：只含 profile、方法、主機），掃描繼續；pipeline 在報告 notes 中加一行統計。讀取植入與 L03 提權遇到 WriteRefused 時只記 note、跳過。
- 理由：沒有測就不是 denied（SPEC 三態）；讓掃描崩潰則連讀取結果都拿不到。
- 後果與風險：使用者可能沒注意到寫入沒測；報告 notes 與矩陣中的 reason 會明示。

## ADR-042：pipeline 的流程、profile 與模組、設定檔增補、讀取植入與 L03 提權、bench 改經 run_scan
- 日期：2026-11-06 · Milestone：MS6 · 相關：SPEC §2、§4、§5 M3、FR-16；ADR-020 #6、ADR-029 補記 2、ADR-033、ADR-036 #7
- 決定：
  1. **順序**（`contracts/pipeline.run_scan`）：授權（不送任何請求）→ 無網路檢查 → 建立唯一的 SafeClient → M1 → S4 端點確認（ADR-043）→ M2 → 登入、dev／ci 讀取植入、M3、dev／ci L03 提權、清理植入 → M4（選配）→ M1 finding 附在 correlate 之後 → M5 enrich。
  2. **profile 與模組**：dev M1–M5；ci M2–M5（不掃前端）；audit M1–M3、M5，**有 DB 連線時也跑 M4**（M4 唯讀，ADR-032 #2；沿用 ADR-033 補記的 bench 行為）。M4 只在 `db_url_env` 指向非空的環境變數時執行；失敗只記 note（類別名稱，不含訊息，避免洩漏 DB URL）。偏離 SPEC §2 表格的字面（audit 沒有 M4）。
  3. **設定檔增補**（§6）：`supabase_url`、`anon_key_env`、`db_schemas`（預設 `["public"]`，傳給 splinter、read_policies、correlate；MS4 稽核 P2 (c)）。
  4. **ScanReport 增補**：`modules`、`notes`、`timings`；**Finding 增補**：`title`、`repro`、`references`（M5 填入）。
  5. **dev／ci 讀取植入**（SPEC §4 第 4 步）：`seed_reads` 在 probe 前讓每位使用者在每張表植入一筆自己的 canary，probe 內的 collect_known_rows 自然會找到它們；最後 `cleanup_reads` 清除，刪不掉回報 CLEANUP_FAILED。**實測**：C04（沒有 INSERT policy）植入回 403，所以 C04 在 dev 仍為 inconclusive；PLAN 原寫「C04 在 dev 可判定」不成立（ground truth 不變）。
  6. **L03 提權**（ADR-029 #9）：`escalation_pass` 只對「基準讀取為 denied」的表，把使用者自己的 user_metadata 設成 role=admin、以密碼重新登入、重讀不該看到的已知列；看得到 → USER_METADATA_ESCALATION（Confirmed、High）。還原一律在 finally。**實測**：L03 user_a 在提權前看到 B 的列 0 筆、提權後 1 筆、還原後 0 筆。
  7. **bench 改經 run_scan**：benchmark 量測的就是產品路徑；`SafeClient(` 只出現在 `pipeline.py`（ADR-020 #6 的靜態測試）。runtime 仍只計 M2＋M3（`report.timings`）。
- 後果與風險：dev／ci 掃描多出植入與提權的寫入（只寫 canary 與測試帳號自己的 Auth 記錄）；提權中斷時測試帳號可能殘留 admin metadata（沿用 ADR-029 已知限制）。

## ADR-043：S4：Supabase URL 必須由使用者明列，bundle 中的 URL 不會單獨被使用（MS5 核准意見第 6 點）
- 日期：2026-11-06 · Milestone：MS6 · 相關：NFR-02、SPEC §7、ADR-036 補記（S4）
- 背景：`ReconOutput.supabase_url` 來自目標的 bundle（不可信輸入）。若直接使用，惡意 bundle 可讓掃描器把測試帳號的密碼（登入）與所有探測送到使用者沒有授權的主機。
- 考慮過的選項：
  1. bundle 的 URL 與 target 同源時自動接受（缺點：多一條例外規則，且同源不代表使用者知道 API 在哪）
  2. 只接受設定檔 `supabase_url` 或 CLI `--supabase-url`；bundle 的 URL 只用來在拒絕訊息中提示（採用）
- 決定：`safety/endpoint.resolve_endpoint`：兩者都有但不同 → 拒絕；有設定檔 → 用設定檔；有 CLI → 用 CLI；都沒有 → `EndpointRefused`，訊息附 bundle 中的 URL（經 report_url）與確認方式。比較一律用 `normalize_api_url`（scheme、host 小寫、去預設埠、拒絕 path／query／fragment／userinfo）。結果與方式記入 `AuthorizationRecord.supabase_url`／`supabase_url_method`。M1 只對已授權的 target 同源送 GET，所以拒絕發生時 API 主機沒有收到任何請求（以 MockTransport 計數的測試證明）。
- 後果與風險：第一次掃描未設定 URL 的使用者會被拒絕一次，需要照訊息確認；這是刻意的摩擦。

## ADR-044：M5 報告、修補 SQL、SARIF、exit code、CLI 與 GitHub Action
- 日期：2026-11-06 · Milestone：MS6 · 相關：SPEC §5 M5、§2、FR-12、FR-13、FR-16、NFR-03；MS4 核准意見第 3 點
- 決定：
  1. **遮罩**：每個 renderer 的最終字串都經 `mask_text`；target 經 `report_url`。HTML 自包含，沒有 script 與外部資源（開啟報告不會對外連線）。
  2. **修補 SQL**：依規則與目標種類的模板（表：ENABLE RLS、DROP 過寬的 permissive policy（名稱來自 M4 的 pg_policies；沒有 M4 時以註解提醒）、依預期範圍 CREATE POLICY；view：`security_invoker = true`；RPC：REVOKE EXECUTE／SECURITY INVOKER；key：輪替步驟）。識別字一律經 `quote_ident`（含控制字元的名稱不產生 SQL，避免跳出註解）；**工具絕不執行**。L04 的模板已在 lab 實測：套用後 `notes` 只剩 owner-scoped SELECT policy。
  3. **排序**：證據等級 → 嚴重度（SPEC §5 M5）。
  4. **exit code**：只有 ci 有門檻（SPEC §2）；預設 Confirmed 且 ≥ high → 1；ci 中有 CLEANUP_FAILED → 4（ADR-014 補記）；設定錯誤 2；授權／端點／寫入被拒 3。dev、audit 一律 0。
  5. **SARIF 2.1.0**：以官方 OASIS schema 驗證；location 指向設定檔（漏洞在資料庫，不在原始碼行）；`partialFingerprints` 用 finding id，讓 GitHub 分辨新舊問題。
  6. **CLI**：`rlsentry scan`、`rlsentry init`；密碼與 key 只從設定檔指名的環境變數讀取，不接受命令列參數。
  7. **GitHub Action**：composite action，輸入只經 `env:` 進入 shell（避免 script injection），不代入 `--i-own-this-target`（授權必須提交在設定檔中）。
- 後果與風險：SARIF 的 location 不指向程式碼行，GitHub code scanning 會把所有結果顯示在設定檔上；這是資料庫層問題的誠實呈現。

## ADR-045：MS4 的 L01 lab 測試只檢查 SECURITY 類 lint（MS5 核准意見第 7 點，選項 C）
- 日期：2026-11-06 · Milestone：MS6 · 相關：ADR-032 #4、MS5-v1 第 5 段「環境發現」
- 背景：`tests/lab/test_whitebox_lab.py::test_l01_rls_disabled_is_reported` 斷言「所有有物件名的 lint 都在 public schema」。容器被強制終止後，Postgres 的 crash recovery 會重設統計，`_realtime.extensions` 的索引 idx_scan 變成 0，PERFORMANCE 類的 `unused_index` 就出現在非 public schema，測試因此失敗；乾淨啟動的 lab 不受影響。
- 決定：不 reopen MS4。T-201 把斷言改成只檢查含 `SECURITY` 類別的 lint。M4 的交叉比對本來就只使用 SECURITY 類（ADR-032 #4），所以這個斷言檢查的仍是產品實際依賴的性質。
- 後果與風險：PERFORMANCE 類 lint 在其他 schema 出現不再被這個測試注意到；它們本來就不參與判定。

### ADR-042 補記：L03 提權前重新量測基準（2026-11-06，派工前參考 benchmark）
- 問題：參考 benchmark 在 L05（dev）產生 2 個 USER_METADATA_ESCALATION 偽陽性。原因：提權在 M3 寫入探測之後執行；L05 的擁有者轉移把使用者自己建立的 canary 轉給對方，這些列因 `created_by = auth.uid()` 仍對原使用者可見；以 M3 一開始的 DENIED 讀取當基準，就把「本來就看得到」誤認為「提權後才看得到」。
- 決定：`escalation_pass` 在提權前以原 token 對同一批「不該看到的已知列」重新量測一次；只有「此刻看不到」的列（hidden）才進入提權後的比較，`known_rows_checked` 與比例也以 hidden 計。hidden 為空就不寫入 metadata。測試：`tests/probe/test_escalation.py` 新增兩個案例。
- 後果：每個候選表多一個 GET（只在 dev／ci）。

### ADR-042 補記 2：實作時的澄清（2026-11-06，T-219、T-220 回報）
- **M4 失敗的處理範圍**：合約寫「任何例外 → note」，T-219 只攔 `psycopg.Error`、`OSError`、`ValueError`、`RuntimeError`（ruff 的 BLE001 禁止 `except Exception`，專案也禁止行內的 lint 豁免註解）。其他例外會中止掃描。這偏向 fail-closed：意料之外的錯誤不會被靜默吞掉；已知的連線、權限、雜湊錯誤仍只記 note。
- **CLI**：預設輸出格式依實際生效的 profile（`report.profile`），不是設定檔的 profile；TARGET 與設定檔 target 比較前去掉結尾的 `/`；未知的 `--format` 值 → exit 2；SARIF 的 artifact uri 為使用者輸入的 `--config` 路徑；`init` 必須有設定檔（不接受 TARGET）。

## ADR-047：MS6 稽核的處理（例外時的清理與還原、CLI 崩潰、報告 URL；拒絕 limit 的 P1）
- 日期：2026-11-06 · Milestone：MS6 · 相關：NFR-01、NFR-03、FR-13、ADR-029 #8–#9、ADR-040、ADR-042、ADR-044；auditor（兩部分，base 5a41a7327）
- 接受並修正（T-232 合約與測試，T-233–T-235 實作）：
  1. **例外時仍清理**：`run_scan` 在 seed_reads 之後以 try/finally 包住 probe 與提權，確保 cleanup_reads 一定執行；`seed_reads` 遇到單一表的網路錯誤只記 note 並保留已植入的列；`cleanup_reads` 遇到單一表的錯誤，該表的列記為 CLEANUP_FAILED，其他表照常清理。
  2. **提權一定嘗試還原，失敗必定回報**：提權 PUT 發生網路錯誤時仍會還原（伺服器可能已經套用）；`restore_user_metadata` 改為回傳是否成功、不拋網路錯誤；還原失敗加 note，明確說明測試帳號可能殘留 role=admin、需人工清除。
  3. **CLI**：Typer 明確設 `pretty_exceptions_show_locals=False`（traceback 不得印出 env、key、DB URL）；網路／OS／runtime 錯誤以 `EXIT_ERROR = 5` 結束，只印例外類別，CI 不會把崩潰誤認為「有 finding」。
  4. **報告**：`recon.supabase_url` 來自 bundle，JSON／HTML 也經 `report_url`。
  5. **correlate 自身排除 KEY_RULES**（ADR-036 #7 由兩處把關）。
  6. **測試**：`test_audit_sends_only_reads_and_the_login_post` 加上「確實有請求」的斷言（原本零請求也會通過）。
- 不接受：**P1「limit=len(pks) 削弱過濾檢查」**。PostgREST 的 limit 只截斷 RLS 已允許的列，所以回傳的每一列都確實對該角色可見；若過濾被忽略，回傳的 N 列只要有任何一列不在查詢集合就判為不可信；若 N 列全在查詢集合，則查詢的 N 個主鍵恰好全部可見，結果正確。因此不會產生錯誤的 allowed 或 denied。`verdict.py` 的 `total <= queried` 檢查在合併讀取後恆真，保留作為防線。
- 交人類決定（列入 MS6 清單第 4 段）：M4 把 anon 的 RPC 越權讀取改標 SECURITY_DEFINER_RPC_DATA 時，嚴重度依 SPEC §5 M5 表格由 High（含敏感欄位時 Critical）降為 Medium。提供 DB 連線反而使嚴重度降低，可能讓 `fail_on: high` 的 CI 通過。
- 列為已知限制（P2）：修補 SQL 一律使用 `db_schemas[0]`；函式 DDL 不含參數簽章（多載函式會失敗）；DROP POLICY 不看 policy 的 roles；policy 名稱超過 63 bytes 會被截斷；還原把 role 設為 null 而非原值；JWT 的「表擁有者 role」（如 supabase_storage_admin）不在 Critical 集合（ADR-038 以 superuser／BYPASSRLS 定義）；GitHub Action 對 `profile: audit` 的設定檔永遠不會失敗（較嚴者勝）；M3 的計時在 dev 含植入、提權與清理。

## ADR-048：收尾 SOP：`/final-question` 與 `/approved`（核准後立即更新進度文件）
- 日期：2026-11-06 · Milestone：MS6 · 相關：ADR-015、ADR-021、ADR-028、ADR-031
- 背景：人類發現 `docs/progress.html` 長時間沒有反映最新狀態。原因：ADR-015／031 只規定在「milestone 收尾、高風險驗收後、暫停前」重跑 `progress.py`，沒有「人類核准之後」這個時間點；核准後的下一個 session 從 §0 開始，§0 沒有這一步。另外，MS6 中 architect 在 T-211、T-215 兩張高風險 ticket 驗收後漏跑。核准意見每次由人類手寫，格式也不一致。
- 考慮過的選項：
  1. 修改 §0，讓每個 session 開始時都重跑（缺點：prompt 是凍結的；而且核准到下一個 session 開始之間仍會落後）
  2. 由人類觸發的兩個 skill（採用，人類決定指令由 architect 命名）
- 決定：
  1. `/final-question`：列出待人類決定的事（來源、選項、建議）或回「沒有待決事項。」；人類回答後，產生可直接貼到 `host/approve.py` 的「Notes」提示的標準格式核准意見。
  2. `/approved <MS>`：檢查 approvals 分支（`decision: approve`、`.sig` 存在、清單 sha256 一致、harness 狀態），全部通過才重跑 `progress.py`、更新 `system_overview.html` 的該列，只提交這三個檔並 push；任一項不符只回報、不修改；不開始下一個 milestone。
  3. skill 原文放在 `docs/sop/`（architect 維護），安裝副本在 `.claude/skills/`（凍結路徑，由人類以 `host/bootstrap.sh --refreeze` 安裝；安裝 commit `013adbc` 只含這兩個檔，與 `docs/sop/` 逐位元組相同）。`docs/verification_steps.html` 新增步驟 6.5，步驟 8 與第 3 節同步更新（ADR-028）。
- 後果與風險：`docs/sop/` 與 `.claude/skills/` 可能漂移；修改 SOP 時 architect 只能改 `docs/sop/`，由人類重新複製並 refreeze。skill 在 session 啟動時載入，安裝後要開新 session 才會生效。

### ADR-013 補記：MS7 交付時重新確認 D4（2026-11-06）
- 確認：D4（Firebase Security Rules）維持「列為未來工作」。MS7 交付的合約、lab、ground truth 與 benchmark 全部以 Supabase／PostgREST 為前提；benchmark 指標只描述 Supabase lab，不推論到 Firebase。
- 若日後支援：需要獨立的 lab（Firebase emulator）、以文件路徑為單位的 ground truth 格式與新的 ADR；不沿用 RowScope。
- 更正：ADR-013 原文「D2（Playwright）仍待 MS5 決定」已過時；D2 已由 ADR-037（MS5）決定為不支援無頭瀏覽器。

## ADR-049：M4 改標 SECURITY_DEFINER_RPC_DATA 時保留較高的嚴重度（MS6 核准意見第 1 點，選項 B）
- 日期：2026-11-06 · Milestone：MS7 · 相關：SPEC §5 M5 嚴重度表、FR-13、ADR-039、ADR-047「交人類決定」
- 背景：ADR-039 起，M3 依角色給讀取規則（anon → ANON_READ_OWNER_SCOPED，High；含敏感欄位 Critical；使用者 → CROSS_TENANT_READ，Medium），M4 在 splinter 證實函式是 SECURITY DEFINER 時改標為 SECURITY_DEFINER_RPC_DATA，嚴重度依 SPEC 表為 Medium。結果是「提供 DB 連線反而讓嚴重度下降」，`fail_on: high` 的 CI 可能因此通過。
- 考慮過的選項：
  1. 照 SPEC 表（一律 Medium；MS6 現狀）
  2. 改標時取 max(原本的嚴重度, Medium)（人類選定）
- 決定：
  1. 改標時嚴重度 = max(finding 原本的嚴重度, RULES["SECURITY_DEFINER_RPC_DATA"].severity)，依 SEVERITY_RANK 比較。結果：anon 經 SECURITY DEFINER RPC 讀到含敏感欄位的資料 → Critical；anon 一般情況 → High；使用者 → Medium。規則名稱與 id 仍改為 SECURITY_DEFINER_RPC_DATA（「怎麼漏的」是 M4 才能證明的事），只有嚴重度不下降。
  2. 合約 `contracts/whitebox.RELABEL_KEEPS_HIGHER_SEVERITY` 與 `correlate(..., keep_higher=None)` 表達這個政策；None 時於呼叫當下讀合約常數。
  3. **分段上線**（流程決定）：既有回歸測試（`test_scan_reads` 對 L07 ground truth 比對嚴重度、`test_gt_consistency`、e2e 的 L07 exit code）在「舊實作」與「新 ground truth」之間不可能同時成立，而實作 ticket 不能改測試與 ground truth、architect ticket 不能改實作。所以：T-240 合約常數預設 False（行為不變）→ T-241 實作 `keep_higher`（單元測試明確傳 True／False）→ T-245 由 architect 在同一個 merge 把常數改為 True、L07-V1 的 severity 改為 high、更新三個既有測試。每一次合併的回歸測試都是綠的，沒有任何一個 commit 停在紅燈。
  4. L07 ground truth：V1（anon）`severity: high`；V2、V3（使用者）維持 `medium`。`test_gt_consistency` 對 SECURITY_DEFINER_RPC_DATA 的期望嚴重度改為 max(Medium, 該角色讀取規則的嚴重度)。
- 理由：嚴重度描述「誰能讀到什麼」，不應依賴使用者是否提供 DB 連線；CI 的 fail_on 結果在有無 M4 時必須一致（以 `tests/whitebox/test_correlate_severity.py` 與 `tests/e2e/test_ci_definer_severity.py` 證明）。
- 後果與風險：**偏離 SPEC §5 M5 表格的字面**（「anon 經 SECURITY DEFINER RPC 實際取得受保護資料」列在 Medium）。SPEC 那一列在本版本中只對使用者角色成立；anon 的情況等同於 anon 可讀 owner-scoped 表（High／Critical）。L07 在 ci 的預設 fail_on 下會失敗（exit 1），MS6 的 e2e 期望 EXIT_OK 改為 EXIT_FINDINGS。這修改了 MS6 已核准的行為，依核准意見以 MS7 ticket 處理，不 reopen。

## ADR-050：D3：Web 介面範圍——不提供 Web 報告頁，由 CLI 產生靜態 HTML
- 日期：2026-11-06 · Milestone：MS7 · 相關：SPEC §12 D3（已決定）、§5 M5、ADR-044
- 背景：SPEC §12 把 D3 標為「已決定：移除 Web 報告頁，改由 CLI 產生靜態 HTML」，但先前只在 ADR-044 的段落中間接提到，沒有一則明確的 ADR。
- 考慮過的選項：
  1. 提供本機 Web 服務瀏覽報告（缺點：多一個常駐服務與攻擊面；報告含 curl 與主鍵，需要額外的存取控制）
  2. CLI 寫出自包含的靜態 HTML（採用，SPEC 已決定）
- 決定：RLSentry 不提供任何 Web 介面或伺服器；`rlsentry scan` 寫出 `rlsentry-report.html`（自包含、沒有 script、沒有外部資源，開啟不會對外連線；ADR-044 #1），另有 JSON 與 SARIF。GitHub Action 以 SARIF 上傳到 code scanning，作為團隊共用的檢視介面。
- 理由：沒有伺服器就沒有額外的攻擊面；報告是檔案，存取控制沿用檔案系統與 CI artifact 的權限。
- 後果與風險：沒有跨次掃描的歷史比較介面；使用者以 SARIF 的 `partialFingerprints`（finding id）在 GitHub 分辨新舊問題。

## ADR-051：ADR-047 已知限制的處理：修三項、維持五項
- 日期：2026-11-06 · Milestone：MS7 · 相關：ADR-044 #2、ADR-047、ADR-042 #6、SPEC §5 M3 清理、§5 M5
- 背景：MS6 稽核列為已知限制的 P2 項目，交付前逐項評估「修正成本 vs. 對使用者的實際影響」。
- 決定（修正，T-242、T-243）：
  1. **DROP POLICY 依 roles**：修補 SQL 只 DROP「可能授予此 finding 角色存取」的 permissive policy：anon finding → roles 含 `anon` 或 `public`；使用者 finding → 含 `authenticated` 或 `public`（`contracts/report.POLICY_ROLES_FOR`）。理由：只服務其他角色的 policy 不可能造成這個 finding，刪掉它只會破壞正常功能。
  2. **policy 名稱 ≤ 63 bytes**：`policy_name` 超過 63 bytes 時改為「前綴＋`_`＋sha256 前 8 碼」，不切斷 UTF-8 字元。理由：PostgreSQL 會靜默截斷，兩張長名稱的表可能得到同一個 policy 名稱，第二個 CREATE POLICY 失敗。
  3. **提權還原為原值**：提權前以 `GET /auth/v1/user` 讀出 `user_metadata.role`，還原時寫回該值；讀不到（網路錯誤、非 200、格式不符）就不提權、不寫入；原值已是 `admin` 也不提權。原值只存在記憶體，不寫進 note、finding 或報告。理由：MS6 把 role 設成 null，若測試帳號原本有 role（例如 `editor`），ci 掃描後帳號狀態被改變。
- 決定（維持為已知限制，在 USAGE.md 與清單揭露）：
  4. **修補 SQL 一律使用 `db_schemas[0]`**：PostgREST 以裸名稱曝露物件，finding 的 target 不含 schema；多個曝露 schema 有同名物件時，正確的 schema 要靠 Accept-Profile 推斷，改動牽涉 M2／M3 的資料模型。絕大多數 Supabase 專案只曝露 `public`。修補 SQL 本來就要求人工審閱後才執行。
  5. **函式 DDL 不含參數簽章**：`ALTER FUNCTION public.f SECURITY INVOKER;` 在函式有多載時會以「function name is not unique」失敗——失敗是安全的（不會改錯函式）。補上簽章需要 M4 另讀 `pg_proc`，沒有 DB 連線時仍無法提供。
  6. **「表擁有者 role」的 JWT 不在 Critical 集合**（ADR-038 以 superuser／BYPASSRLS 定義，可驗證）。
  7. **GitHub Action 對 `profile: audit` 的設定檔永遠不會失敗**（較嚴者勝，SPEC §2 只有 ci 有門檻）；USAGE.md 明寫 Action 要用 ci 設定檔。
  8. **dev 的 M3 計時含植入、提權與清理**；runtime 指標以 audit 量測，不受影響。
- 後果與風險：第 1 點讓「policy 給自訂角色、而 anon／authenticated 是該角色成員」的情況不會被 DROP（PostgreSQL 的 policy roles 可指定任意角色）；這種設定在 Supabase 罕見，修補 SQL 仍會建立新的 owner-scoped policy，使用者需人工檢查。第 3 點每個提權角色多一個 GET；Auth API 會合併 user_metadata，原本沒有 role 的帳號還原後是 `role: null`（不是不存在）。

## ADR-052：USAGE.md doctest、lab 命令列入口與展示情境的設計
- 日期：2026-11-06 · Milestone：MS7 · 相關：SPEC §9 Profile 端到端與展示情境、§11 紀錄與交付、ADR-035、ADR-043
- 背景：`make acceptance` 會執行 USAGE.md 中每個 `<!-- doctest -->` bash block；MS7 審查重點是「照 USAGE.md 親手跑一次」。lab 的操作原本只有 Python 函式（`labctl`），從 shell 無法直接使用。
- 考慮過的選項：
  1. doctest 內嵌 `python -c "from lab._shared import labctl; …"`（缺點：人類照著打很難讀，也容易打錯）
  2. 在 docs/ 放 shell script（缺點：等於繞過驗收閘門新增可執行程式）
  3. 新增 `python -m lab._shared up|apply|env|sql|serve`（lab-dev ticket T-244，經驗收閘門；採用）
- 決定：
  1. 每個 profile 一個 doctest，皆在本機 lab 執行、可重複執行（每次先 `apply` 重設情境）：**dev → L04**（M1–M5，報告確認跨租戶讀取，且 `correlation: probe_only` 證明 splinter 沒報），**ci → L05**（跨租戶寫入 High → exit 1，產出 SARIF），**audit → L08**（唯讀；設定檔不寫 `supabase_url`，先示範 S4 拒絕 exit 3，再以 `--supabase-url` 確認；service_role key → Critical）。
  2. 展示情境 L04（ADR-035）寫成第四個 doctest：splinter 沒報 → Confirmed → 遮罩的 curl → 修補 SQL → `python -m lab._shared sql` 套用 → 重掃沒有 Confirmed 漏洞。
  3. 範例設定檔放在 `docs/examples/`（dev、ci、audit 各一），USAGE.md 逐欄說明；環境變數名稱 `RLSENTRY_ANON_KEY`、`RLSENTRY_DB_URL`、`RLS_A_PW`、`RLS_B_PW`（`contracts/lab.LAB_ENV_*`、`LAB_USERS`）。
  4. dev 的前端以 `python -m lab._shared serve <情境> --port 8740` 在背景提供，只綁 127.0.0.1。
- 理由：doctest 由 `make acceptance` 自動執行，人類照著做的就是被驗證過的同一組指令。
- 後果與風險：doctest 需要 Docker 與 lab；在沒有 lab 的環境 `make acceptance` 會失敗（不會跳過）。port 8740 被占用時 dev 與 demo 的 doctest 會失敗。

### ADR-051 補記：MS7 稽核 Part A 的 P2，列為已知限制（2026-11-06）
- 稽核結論：MS7 的產品程式沒有 P0／P1。以下 P2 不修正，於 USAGE.md 與 MS7 清單揭露：
  1. **DROP 範圍**：使用者 finding 會 DROP `TO public` 的 policy（它也服務 anon），新建的 policy 只有 `TO authenticated`；anon finding 會 DROP 同時涵蓋 anon 與 authenticated 的 policy，新建的只有 `TO anon`。套用後另一個角色原本合法的存取可能消失。修補 SQL 本來就要求人工審閱（ADR-044），這是可用性問題而非安全問題。
  2. **嚴重度保證依賴合約常數**：`RELABEL_KEEPS_HIGHER_SEVERITY` 為 True 且 pipeline 不傳 `keep_higher`；有測試把關（`test_correlate_severity.py`、`test_ci_definer_severity.py`、holdout），沒有執行期的防護。
  3. **M4 部分失敗**（MS6 既有）：`read_policies` 失敗時 M4 從 `modules` 移除，但 correlate 已完成的改標保留；不會降低嚴重度。
  4. **lab 命令列入口**（測試基礎設施，非產品）：`serve --port` 未檢查範圍（被占用或超出範圍時以 traceback 結束）；`serve` 安裝的 SIGTERM／SIGINT handler 不還原（測試只以子程序呼叫 serve）；情境名稱直接進入 glob（只影響本機）；`env` 會把 lab 密碼印到 stdout（只有 lab 的值；doctest 以 `eval` 使用，不回顯）。

## ADR-053：更新三個因已核准的行為變更而過時的 holdout 測試（MS2 ×2、MS6 ×1）
- 日期：2026-11-06 · Milestone：MS7 · 相關：§7（make acceptance）、ADR-039、ADR-040、ADR-051 #1、MS4 核准意見第 2、5 點
- 背景：`make acceptance` 會執行**所有** milestone 的 holdout；每個 milestone 的 `verify-milestone` 只執行該 milestone 的 holdout，所以舊 holdout 被後來的行為變更打破時沒有人發現。MS7 第一次 `make acceptance` 有 3 個失敗：
  1. MS2 `test_rpc_user_leak_finding`：斷言 M3 給 SECURITY_DEFINER_RPC_DATA；MS6 依 MS4 核准意見第 5 點 (b)（ADR-039）改為只有 M4 能用這個規則，M3 給 CROSS_TENANT_READ（同為 Medium）。
  2. MS2 `test_public_profiles_anon_sensitive_warning_and_401_never_denied`：以 Profile.CI 寫的唯讀測試；MS3 起 ci 會做寫入探測（假伺服器把寫入當成功），MS6 起同一角色的已知主鍵合併為一個 GET（ADR-040，MS4 核准意見第 2 點），假伺服器不認得這種請求。
  3. MS6 `test_holdout_fix_sql_quotes_schema_and_policy`：不安全的 policy 名稱放在 `roles=[]` 的 policy 上；MS7 的 ADR-051 #1 只 DROP 能服務該角色的 policy，所以名稱根本不會寫進 SQL（仍然安全），但斷言要求回傳 None。
- 決定：以 `holdout.py add` 覆寫這兩個檔案（舊版留在 rlsentry-holdout 分支的歷史中），只改上述測試，其他測試不動：
  1. 斷言改為 CROSS_TENANT_READ、Medium。
  2. 改以 Profile.AUDIT 執行（回到 MS2 的唯讀意圖）；假伺服器支援合併讀取；拆成兩個參數：anon 收到 401 → inconclusive（絕不是 denied）且沒有敏感欄位提示；anon 收到 200 → denied 且有 SENSITIVE_COLUMN_PUBLIC。
  3. 不安全的名稱改放在 `roles=["anon"]` 的 policy 上（pg_policies 的 roles 不會是空的；沒有 TO 時為 `{public}`），仍斷言回傳 None。
- 新雜湊：`MS2/test_holdout_probe.py` 9ffdacaafd0bdf3e340c95787bf6d5e5fdc871518e41c0c11f7789b861ad0557；`MS6/test_holdout_ms6.py` db638a8bcd4fbeebc15ee5f1e14c7519806080bbcd0a9fa48f390e79038f55e9。
- 理由：這三個失敗都是 holdout 寫下的舊行為與人類核准的新行為衝突，不是產品缺陷；不更新的話 `make acceptance` 永遠無法通過。保留每個測試原本要守的性質（401 不是 denied、不安全的名稱不產生 SQL、使用者的 RPC 越權讀取是 Medium finding）。
- 後果與風險：
  - 第 2 點揭露了 ADR-040 的副作用：anon 的合併讀取只要一個 401，就整格 inconclusive，也就失去「公開表含敏感欄位」的提示。實際的 PostgREST 不會對單列回 401（沒有權限時整張表都是 401，本來就看不到任何列），所以實務影響有限；列為已知限制。
  - holdout 是在實作者看不到的情況下寫的；這次更新是 architect 在知道實作之後改的，獨立性較低。所以每個修改都只換掉衝突的輸入或斷言，並在本 ADR 逐項說明。若你不同意，可要求 reopen MS2／MS6 重新核准。
  - 流程教訓：派工前的參考實測應該跑**所有** milestone 的 holdout（MS7 的參考實測只跑了 MS7 的，所以 ADR-051 #1 對 MS6 holdout 的影響到 acceptance 才發現）。
