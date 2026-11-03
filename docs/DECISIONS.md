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
