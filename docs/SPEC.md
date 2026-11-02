# RLSentry 產品規格書（SPEC）

> 版本 v1.0 · 2026-11-02 · 取代先前所有版本（含 Claude Doc 版 v0.2）
> 本檔屬於凍結護欄的一部分：代理不得修改。規格變更由專案負責人在本機修改、重新打上 `harness-frozen` 標籤後推送。

## 0. 文件說明

本文件定義 RLSentry 的產品規格與自主開發流程。讀者有三類：

- **architect**（主代理）：依本文件規劃 milestone、撰寫合約與測試、拆 ticket、驗收。
- **implementer／auditor**（subagent）：依 ticket 引用的章節實作或審查。
- **專案負責人**（唯一的人工審查者）：在每個 milestone 關卡依本文件判斷成果是否正確。

規則優先序：流程的**機制**以 `harness/` 的程式與 `.claude/` 設定為準；本文件描述產品要做什麼、以及流程的意圖。兩者衝突時，architect 應寫 ADR 說明並在驗證清單第 4 段列出，不可自行繞過 harness。

需求編號：功能需求 `FR-xx`、非功能需求 `NFR-xx`。ticket、測試名稱、ADR 都要引用編號以便追溯。

### 名詞表

| 名詞 | 意義 |
| --- | --- |
| Supabase | 以 Postgres 為核心的開源 BaaS，提供 Auth、Storage 與自動產生的 REST API |
| PostgREST | 把 Postgres schema 自動變成 REST API 的伺服器，路徑 `/rest/v1/` |
| RLS | Row-Level Security，Postgres 內建的列層級授權 |
| Policy | RLS 規則：`USING`（可看到哪些列）與 `WITH CHECK`（可寫入哪些列） |
| publishable／anon key | 設計上公開、放在前端的 key，代表 `anon` 角色，受 RLS 限制 |
| secret／service_role key | 伺服器專用 key，**繞過 RLS**，絕不可出現在前端 |
| BOLA | Broken Object Level Authorization：存取不屬於自己的物件（OWASP API1） |
| 黑箱／灰箱／白箱 | 只有網址／另有測試帳號／另有 DB 連線 |
| Expected policy | 使用者宣告的預期授權：表 × 操作 × 角色 → 列範圍 |
| 三態結果 | 每個探測格子的結果：allowed／denied／inconclusive |
| 證據等級 | Confirmed／Suspected／Configuration warning，與嚴重度獨立 |
| Ground truth | Lab 中事先埋好、逐列寫明預期結果的資料，用來計算指標 |
| Milestone（MS） | 開發的大階段；每個 MS 結束都需要專案負責人以簽章核准 |

## 1. 產品概述

RLSentry 是一個開源的**動態授權驗證工具**：以不同身分實際存取 Supabase 應用的每張資料表與每種操作，比對「實際能存取的」與「使用者宣告應該能存取的」，差異即為發現（finding），並附可重現證據與修補建議。

一句話定位：**Security Advisor 告訴你設定長什麼樣，RLSentry 證明攻擊者實際能存取什麼。**

### 研究貢獻

一種**不依賴資料庫管理權限**的動態授權驗證方法：透過多身分、跨資料表、跨操作的差分存取測試，找出靜態 RLS 檢查無法確認的 Broken Access Control。RLSentry **不宣稱能證明整個專案安全**，它驗證的是授權行為是否符合宣告的預期。

### Why：問題成因

核心問題不是「RLS 沒開」，而是**授權邏輯錯誤且無人驗證**：

1. **架構移除了守門員**：瀏覽器以公開的 anon key 直接經 PostgREST 存取資料庫，RLS 是唯一一道門。
2. **開了 RLS 也可能錯**：`USING (true)`、依賴使用者可自改的 `user_metadata`、只檢查已登入而未檢查擁有者、UPDATE 的 `WITH CHECK` 寬鬆、RLS 不管欄位。
3. **金鑰混淆**：service_role key 被打包進前端，即完全繞過 RLS。
4. **設定退化**：新 migration 或 AI 重新生成程式碼，使昨天安全的系統今天不安全。
5. **現有工具只看設定是否存在**，而且需要 DB 權限。實例：CVE-2025-48757 中，約 10% 的受測 AI 生成 app 可僅用 anon key 讀寫資料表，而 Supabase 早已提供 Advisor 警告。缺的不是提醒，是驗證。

### How

攻擊者視角的**差分存取測試**：對每個（身分, 資料表, 操作）組合發出真實請求，以已知擁有者的資料判定結果，與 expected policy 比對。

### 目標與非目標

| 目標 | 非目標 |
| --- | --- |
| 自動偵測未授權的資料表存取（含跨租戶）與前端金鑰外洩 | 掃描任何未經授權的第三方網站 |
| 黑箱模式不需 DB 權限即可運作 | 支援 Supabase 以外的 BaaS（Firebase 等列為未來工作） |
| 每個 finding 有證據等級、可重現、可修補 | 自動修改使用者的資料庫或程式碼 |
| 可放進 CI 作為授權回歸測試 | 一般 Web 弱點掃描（XSS、SQLi 等） |
| 以 Lab benchmark 量化有效性 | Edge Functions 自身的授權邏輯（不經 PostgREST） |
| 三種 profile 共用同一核心 | Web 報告頁（已移除，以靜態 HTML 報告取代） |

## 2. 使用者與使用模式

### Persona

| Persona | 擁有的權限 | 想回答的問題 |
| --- | --- | --- |
| 獨立開發者／用 AI builder 做 app 的人 | 網址、自己的測試帳號、DB 連線 | 上線前有沒有漏掉什麼？ |
| 團隊後端工程師 | 同上，外加 CI | 這個 PR 有沒有讓哪張表變得可被存取？ |
| 稽核者／滲透測試者 | 通常只有網址，或由擁有者提供帳號 | 攻擊者實際拿得到什麼？ |

### 三種 profile（共用同一核心，只改預設值）

| Profile | 對象 | 寫入探測 | 啟用模組 | 輸出 | 失敗門檻 |
| --- | --- | --- | --- | --- | --- |
| `dev` | 獨立開發者 | 允許（本機 lab） | M1–M5；有 DB 連線才含 M4 | 靜態 HTML + 終端摘要 | 不設 |
| `ci` | 團隊 CI | 允許（僅限可丟棄的 preview DB 與專用測試帳號） | M2–M5 | JSON + SARIF + exit code | Confirmed 且 ≥ high |
| `audit` | 稽核者 | **禁止，且不可被設定檔覆寫** | M1–M3、M5 | HTML + JSON，附授權確認紀錄 | 不設 |

用法：`rlsentry scan --profile audit https://my-app.example.com --i-own-this-target`。

### 在開發生命週期中的使用時機

越早期越有 DB 權限、越可以寫入；越晚期越接近攻擊者視角、只能唯讀。前端金鑰外洩只有在 build 之後才看得到，所以 M1 必須掃描部署後的網址。

| 階段 | profile | 寫入 |
| --- | --- | --- |
| 本機開發 | dev | 允許 |
| PR／CI | ci | 允許（preview DB） |
| 上線前 staging | dev 或 ci | 允許（staging） |
| 上線後 production | audit | 禁止 |
| 外部稽核 | audit | 禁止 |

### 核心使用者故事

- 身為開發者，我執行一個指令，就能知道哪些資料表 anon 讀得到，以便在上線前修好。
- 身為開發者，我能確認 user A 讀不到 user B 的私有資料，而不是只看到「查詢回 0 列」。
- 身為團隊，我希望 PR 引入新的可存取表時 CI 失敗，以便授權不會悄悄退化。
- 身為稽核者，我只有網址也能得到有證據等級的報告；工具無法判定的地方會明寫 inconclusive。
- 身為任何使用者，我拿到的每個 finding 都有可貼上執行的修補 SQL。

## 3. 需求

P0 為交付必備，P1 為應做，P2 為有餘力再做。

### 功能需求（FR）

| 編號 | 需求 | 模組 | 優先 |
| --- | --- | --- | --- |
| FR-01 | 抓取目標網站的 HTML 與所有 JS chunk（含 source map，如存在），並記錄掃描了哪些 chunk | M1 | P0 |
| FR-02 | 從 JS 中擷取 Supabase project URL 與所有疑似 key | M1 | P0 |
| FR-03 | 將 key 分為三類：publishable／anon（正常公開，不是漏洞）、secret／service_role（Critical）、unverified（無法辨識，交人工確認）；同時辨識 JWT 與 `sb_publishable_`／`sb_secret_` 格式 | M1 | P0 |
| FR-04 | 透過 PostgREST OpenAPI 列舉 table、view、RPC 與欄位，標記為 confirmed | M2 | P0 |
| FR-05 | OpenAPI 不可用時，從 bundle 中的 `.from('x')`、`.rpc('x')` 推測目標並標記為 inferred；報告列出探索覆蓋率，並聲明「未發現不代表安全」 | M2 | P1 |
| FR-06 | 以 anon 身分對每個目標測試 SELECT，結果為 allowed／denied／inconclusive，不下載資料內容 | M3 | P0 |
| FR-07 | 以測試帳號登入取得 user A／B 的有效 Supabase Auth JWT | M3 | P0 |
| FR-08 | 跨租戶測試：以已知擁有者的資料列判定 A 能否讀、改、刪 B 的列；無可判定的資料時回報 inconclusive | M3 | P0 |
| FR-09 | dev／ci 模式下測試 INSERT／UPDATE／DELETE，並以擁有者身分或 DB 讀回驗證最終狀態；自動清理 | M3 | P1 |
| FR-10 | 讀取 expected access policy（§6），與實測結果比對產生 finding | M3 | P0 |
| FR-11 | 提供 DB 連線時執行 splinter lints，並與 M3 結果交叉比對 | M4 | P1 |
| FR-12 | 產生 JSON 與靜態 HTML 報告；每個 finding 同時標示證據等級與嚴重度，附 `curl` 重現指令與修補 SQL | M5 | P0 |
| FR-13 | GitHub Action 與 SARIF 輸出；依 `fail_on` 設定 exit code | 介面 | P1 |
| FR-14 | （已移除）Web 報告頁 | — | — |
| FR-15 | `rlsentry init`：依探索到的 schema 產生 expected policy 草稿供使用者修改 | M3 | P1 |
| FR-16 | Python API：`from rlsentry import run_scan`，與 CLI 行為一致 | 介面 | P1 |

### 非功能需求（NFR）

| 編號 | 需求 | 驗收方式 |
| --- | --- | --- |
| NFR-01 | **預設唯讀**：audit 模式絕不寫入；dev／ci 以外的模式不發出寫入請求 | 測試 + Postgres `log_statement = mod` 的資料庫 log 驗證 0 次寫入（不採信工具自己的宣稱） |
| NFR-02 | **授權閘門**：未確認擁有目標（`--i-own-this-target` 或設定檔 `authorized: true`）即拒絕執行，並在報告記錄確認者與時間 | 單元測試（標記 `safety`） |
| NFR-03 | **不保存資料內容**：只記錄列數、欄位名稱與主鍵；key 在所有輸出中遮罩（保留前 6、後 4 碼） | 程式審查 + 測試（標記 `safety`） |
| NFR-04 | **限速**：預設每秒 ≤ 5 個請求，可調整 | 整合測試 |
| NFR-05 | **效能**：50 張表以內的專案，audit 掃描 < 60 秒 | Lab 量測（§9 runtime） |
| NFR-06 | **有效性**：case-level recall ≥ 95%、precision ≥ 95%、FPR ≤ 5%，附原始數量 | §9 benchmark |
| NFR-07 | **可重現**：同一目標、同一設定，兩次掃描的 finding 集合相同 | 整合測試 |
| NFR-08 | **可維護**：核心模組測試覆蓋率 ≥ 80%；ruff 與 mypy 無錯誤 | CI |
| NFR-09 | **對外連線限制**：只連線 localhost 與使用者指定的目標；開發期間只連線 localhost、套件來源與 GitHub | 雲端 environment 網路白名單 + 程式審查 |

## 4. 系統架構

RLSentry 是一個核心函式庫加三層薄介面：CLI（Typer）、Python API、GitHub Action。三者都只呼叫同一個 `run_scan()`，所以行為一致、邏輯只寫一次。所有對目標的存取都經過 `safety` 層。

```text
  CLI ─┐   Python API ─┐   GitHub Action ─┐
       └───────────────┴──────────────────┴──> run_scan(config)
                                                  │
        safety：授權閘門 · 唯讀檢查 · 限速 · key 遮罩（套用於所有模組）
                                                  │
   M2 Discovery ─> M3 Probe ─> M5 Report     M1 Recon ─> M5     M4 Whitebox（選配）─> M5
        │              │                        │                       │
   PostgREST OpenAPI   PostgREST + Auth     部署後的 JS bundle      Postgres（DB 連線）
```

### 執行流程

1. 介面層讀取設定與 profile，交給 `safety` 檢查授權與模式；未通過即停止。
2. M1 抓取 bundle、分類 key。發現 service_role key 立即記為 Critical，但**絕不使用它存取資料**。
3. M2 以 anon key 列舉目標並標記信心等級。
4. 以測試帳號取得 A、B 的 JWT；dev／ci 模式植入已知擁有者的資料。
5. M3 以有限並行跑完存取矩陣，產生三態結果，與 expected policy 比對。
6. 若有 DB 連線，M4 執行 splinter 並標記 confirmed／lint-only／probe-only。
7. M5 輸出報告；CLI 與 Action 依 `fail_on` 決定 exit code。

### 為什麼選這個架構

| 方案 | 優點 | 缺點 | 結論 |
| --- | --- | --- | --- |
| 一堆獨立腳本 | 開發最快 | 容易漏步驟、無法進 CI | 不採用 |
| SaaS 服務 | 使用體驗最好 | 使用者要交出 DB 連線與帳號；掃描從我們的伺服器發出 | 不採用 |
| **核心函式庫 + 薄介面** | 行為一致、可在使用者自己的機器或 CI 執行 | 前期要設計模組邊界 | **採用** |

## 5. 模組設計

模組之間只透過 §6 的資料結構交接，因此可以分給不同 subagent 並行開發與單獨測試。每個模組拆成小檔（例如 `safety/gate.py`、`safety/mask.py`、`safety/ratelimit.py`），讓改不同檔案的 ticket 可以同時進行。

### Safety 層（所有模組共用）

- **授權閘門**（NFR-02）：未確認擁有目標就拒絕執行。
- **模式檢查**（NFR-01）：任何非 HEAD／GET 的請求都必須經過 `require_write_allowed()`；audit 一律拒絕，且 audit 的唯讀不可被設定檔覆寫。
- **限速**（NFR-04）：asyncio semaphore + token bucket。
- **遮罩**（NFR-03）：所有輸出中的 key 與 JWT 都遮罩。
- **可識別流量**：User-Agent 為 `RLSentry/<version>`，讓目標擁有者能在 log 中辨識。

### M1 Recon：找出 URL 與金鑰

**輸入**：目標網址。**輸出**：`list[KeyFinding]`、`supabase_url`、已掃描的 chunk 清單。

1. 抓 HTML，解析 `<script src>`、`<link rel=modulepreload>`。
2. 依框架補抓延遲載入的 chunk（Next.js 的 `_buildManifest.js`、Vite 的 `assets/*.js` 之間的 import）；存在 `.map` 時一併解析。
3. 以 regex 擷取 project URL（`https://<ref>.supabase.co` 與 `createClient(` 第一個參數附近的自訂網域）、JWT 形式的 key、`sb_publishable_…`／`sb_secret_…` 格式的 key。
4. JWT 以**不驗簽**方式解碼 payload，讀出 `role`、`ref`、`exp`。
5. 對候選字串計算 Shannon entropy，過濾不像 key 的字串。

**分類（FR-03）**：publishable／anon 出現在前端是正常設計，不產生漏洞 finding；secret／service_role 是 Critical；其餘標為 unverified，列為 Configuration warning 交人工確認。

**限制**：bundle 可能被壓縮、切割或動態載入，結果**不保證完整**；key 也可能由執行期 API 下發而不在 bundle 中。報告必須列出掃描範圍。無頭瀏覽器（Playwright）為 D2（§12）。

### M2 Discovery：列舉攻擊面

**輸入**：URL + anon key。**輸出**：`list[Target]`。

1. `GET /rest/v1/`（帶 `apikey` 與 `Authorization: Bearer <anon>`）取得 OpenAPI 文件；從 `paths` 取得 table、view、`/rpc/*`，從 `definitions` 取得欄位與主鍵。標記 confirmed。
2. OpenAPI 被關閉或限制時，改從 bundle 的 `.from('x')`、`.rpc('x')` 推測，標記 inferred。
3. 使用者在 expected policy 中列出、但兩種方式都找不到的表，標記 unknown。

報告列出覆蓋率，並明寫**未發現不代表安全**：沒暴露在 API schema 的表、只經 Edge Functions 存取的資料，都不在探測範圍內。RPC 需要參數時只記錄可呼叫性，不猜參數。

### M3 Probe：差分存取測試（核心）

**輸入**：targets、身分 sessions、expected policy、profile。**輸出**：`AccessMatrix` + `list[Finding]`。

**身分**：`anon`（只有 anon key）、`user_a`、`user_b`（以 `POST /auth/v1/token?grant_type=password` 取得有效 JWT）。

**探測方式**

| 操作 | 請求 | 判定依據 | profile |
| --- | --- | --- | --- |
| 讀取 | `HEAD /rest/v1/<t>?select=<pk>&<pk>=in.(<已知主鍵>)`，`Prefer: count=exact` | 已知主鍵的可見數（來自 `Content-Range`），不下載資料 | 全部 |
| 跨租戶讀取 | 以 B 的 JWT 查詢屬於 A 的已知主鍵 | B 看得到 A 的主鍵即為 BOLA | 全部（需測試帳號） |
| 新增 | `POST`，內容帶 canary 標記 `rlsentry_canary_<uuid>` | 成功後以擁有者身分讀回確認 | dev／ci |
| 修改／刪除 | 以已知主鍵為條件，`Prefer: return=representation` | 影響列數 **加上** 讀回最終狀態 | dev／ci |

**三態結果**：`count = 0` 不等於 denied，可能是對方沒有資料、查詢條件錯誤或表是空的。只有在「已知存在某筆屬於 B 的列」時，A 查不到它才算 denied。

- **dev／ci**：探測前一律以擁有者身分植入已知資料：每位測試使用者至少一筆私有列；有 `public_column` 的表各一筆公開與非公開列。判定依據是這些已知主鍵是否可見。
- **audit**：無法植入資料。若 A、B 各自看得到自己的列，就以主鍵交集判定；否則回報 inconclusive 並說明原因，絕不寫成「安全」。

**關鍵的 RLS 行為**：`USING` 擋下 UPDATE／DELETE 時，PostgREST 通常回傳成功但影響 0 列；只有違反 `WITH CHECK` 的 INSERT 會回錯誤。所以「沒報錯」不代表「寫入成功」，「回 200」也不代表「有漏洞」。寫入一律以讀回的最終狀態判定，以捕捉 trigger 或 `WITH CHECK` 造成的差異。

**差分**：`finding = actual_access − expected_access`。只有「實際允許但預期拒絕」是漏洞；「預期允許但實際拒絕」記為功能性提示。找不到擁有者欄位而無法判斷預期的表，產生 Review 提示，不判定為漏洞。

**清理**：canary 由同一身分刪除；刪不掉（本身也是一種發現）就記錄並提示，lab 中有 DB 連線時代為清理。

### M4 Whitebox：與 splinter 交叉比對（選配）

**輸入**：DB 連線（建議唯讀角色）。**輸出**：lint 結果與交叉比對標籤。

1. 以固定版本的 splinter SQL 透過 psycopg 執行。直接連 DB 時須先 `SET LOCAL pgrst.db_schemas = 'public, …'`，否則可能回傳空結果。
2. 讀取 `pg_policies`，把每張表的 policy 條件式放進報告。
3. 每個問題標為：**confirmed**（lint 有報、實測可存取）、**lint-only**（lint 有報、實測無法存取）、**probe-only**（lint 沒報、實測可存取）。

**解讀**：probe-only 表示動態測試發現了靜態檢查沒報的問題，**不代表 splinter 有缺陷**，兩者回答的是不同問題。SECURITY DEFINER **不一定**繞過 RLS，還取決於函式擁有者、`EXECUTE` 權限與函式內部邏輯；只有實測取得受保護資料時才是漏洞，否則是 Configuration warning。兩邊都沒報也不代表安全。

### M5 Report：報告與修補建議

**輸入**：所有 findings。**輸出**：JSON、靜態 HTML、SARIF（P1）。

每個 finding 包含：標題、證據等級、嚴重度、目標、身分、操作、證據（列數、狀態碼、遮罩後的 key）、`curl` 重現指令、修補 SQL、參考連結。修補 SQL 由模板產生（`ENABLE ROW LEVEL SECURITY`、`auth.uid() = <owner_column>` 的 policy、`security_invoker = true` 的 view、金鑰輪替步驟），**工具絕不自動執行**。

**證據等級**（與嚴重度是兩個獨立維度）：

| 等級 | 條件 |
| --- | --- |
| Confirmed | 已知不該看到的資料列實際可見，或寫入後讀回證實狀態改變；或 service_role／secret key 出現在前端 |
| Suspected | 有可疑行為但證據不足：inconclusive 的格子、只從 bundle 推測的目標 |
| Configuration warning | 只有設定層面的訊號：lint-only、SECURITY DEFINER 可執行但未取得資料、unverified key |

**嚴重度**：

| 等級 | 條件 |
| --- | --- |
| Critical | service_role／secret key 在前端；anon 可寫入；anon 可讀含敏感欄位（email、phone、token 等）的表 |
| High | anon 可讀 owner-scoped 表；跨租戶寫入或刪除 |
| Medium | 跨租戶讀取；anon 經 SECURITY DEFINER RPC 實際取得受保護資料 |
| Low | 只有設定層面的風險 |
| Review | 無法判斷預期權限，需人工確認 |

報告依「證據等級 → 嚴重度」排序。`fail_on` 預設只在 Confirmed 且嚴重度 ≥ high 時失敗。

## 6. 資料模型與設定

模組之間只交換下列 Pydantic v2 模型，放在 `rlsentry/contracts/models.py`（architect 擁有）。它們同時定義 JSON 報告格式。改動任何欄位都要寫 ADR。

```python
class Role(str, Enum):        ANON = "anon"; USER_A = "user_a"; USER_B = "user_b"
class Op(str, Enum):          SELECT = "select"; INSERT = "insert"; UPDATE = "update"; DELETE = "delete"
class Outcome(str, Enum):     ALLOWED = "allowed"; DENIED = "denied"; INCONCLUSIVE = "inconclusive"; NOT_TESTED = "not_tested"
class Evidence(str, Enum):    CONFIRMED = "confirmed"; SUSPECTED = "suspected"; CONFIG_WARNING = "config_warning"
class Severity(str, Enum):    CRITICAL = "critical"; HIGH = "high"; MEDIUM = "medium"; LOW = "low"; REVIEW = "review"

class KeyFinding(BaseModel):          # M1
    kind: str                         # publishable | secret | unverified
    masked: str                       # 原值不落地（NFR-03）
    source_file: str
    jwt_claims: dict | None           # role、ref、exp

class Target(BaseModel):              # M2
    name: str
    kind: str                         # table | view | rpc
    columns: list[str]
    primary_key: list[str]
    discovered_by: str                # openapi | bundle | policy
    confidence: str                   # confirmed | inferred | unknown

class ProbeResult(BaseModel):         # M3 單一格
    target: str
    role: Role
    op: Op
    outcome: Outcome
    known_rows_checked: int           # 用來判定的已知主鍵數；0 時必為 inconclusive
    reason: str                       # 尤其是 inconclusive 的原因
    http_status: int | None
    evidence_curl: str                # 已遮罩 key 的重現指令

class Finding(BaseModel):             # M3/M4/M1 → M5
    id: str                           # 內容雜湊：target+role+op+rule，跨次掃描穩定
    rule: str                         # 例如 ANON_READ_OWNER_SCOPED
    evidence: Evidence
    severity: Severity
    target: str | None
    probes: list[ProbeResult]
    lint: str | None
    correlation: str | None           # confirmed | lint_only | probe_only
    fix_sql: str | None
```

`Finding.id` 用內容雜湊，讓 CI 能分辨「新出現的問題」與「舊問題還沒修」。

### 設定檔 `rlsentry.yaml`

```yaml
target: https://my-app.example.com
authorized: true             # 等同 --i-own-this-target（NFR-02）
profile: audit               # dev | ci | audit（audit 強制唯讀）
rate_limit_rps: 5
test_users:
  - {name: user_a, email: a@test.dev, password_env: RLS_A_PW}
  - {name: user_b, email: b@test.dev, password_env: RLS_B_PW}
db_url_env: SUPABASE_DB_URL  # 選填，啟用 M4

# Expected access policy：表 × 操作 × 角色 → 列範圍
# 列範圍：deny | all | own_rows_only | public_rows_only | public_or_own_rows
tables:
  profiles:
    owner_column: id
    select: {anon: deny, user: own_rows_only}
    update: {anon: deny, user: own_rows_only}
    delete: {anon: deny, user: deny}
  posts:
    owner_column: author_id
    public_column: is_published
    select: {anon: public_rows_only, user: public_or_own_rows}
    insert: {anon: deny, user: own_rows_only}

defaults:                    # 未列出的表或操作
  anon: deny
  user: own_rows_only        # 找不到 owner_column 時改為 Review，不判定為漏洞
fail_on: {evidence: confirmed, severity: high}
```

密碼一律以環境變數名稱引用，設定檔可以安全提交到 Git。

`rlsentry init`（FR-15）依探索到的 schema 產生草稿：有 `user_id`、`owner_id`、`author_id` 等欄位的表預設 own_rows_only；有 `is_public`、`is_published` 等欄位的表提示可能是 public_rows_only；其餘標 `TODO`，要使用者決定。這份檔案同時是 CI 回歸測試的依據。

## 7. 安全、倫理與法律

RLSentry 只能用在自己擁有、或取得書面授權的目標上。這條規則寫進程式（授權閘門、audit 唯讀），而不只是寫在文件。

### 法律背景（台灣）

- **刑法第 358 條**：無故以他人帳密、破解保護措施或**利用電腦系統之漏洞**入侵他人電腦。用前端撿到的 key 讀別人的資料庫可能落入此條。
- **刑法第 359 條**：無故取得、刪除或變更他人電磁紀錄，致生損害。
- **刑法第 362 條**：製作專供犯上述之罪的電腦程式並致生損害；這是工具必須防禦導向的原因之一。
- 不確定是否屬於授權範圍時，先問授課老師或學校法務。

### 我們自己的資安衛生

- 測試帳號密碼與 DB 連線字串只放在環境變數，不提交。
- Lab 的 service_role key 只存在一次性的本機 Supabase 專案中。
- 發現真實外洩的 key 不寫進 issue、PR 或 log 原文；通知擁有者輪替。
- 在授權範圍內意外發現第三方問題（例如開源範本本身的漏洞），以私下管道通報原作者。

## 8. Lab Benchmark

Benchmark 是一組答案事先已知的本機 Supabase 專案，用來量化 RLSentry 的有效性；它本身也是可重用的交付物。

### 情境清單

| # | 情境 | 埋入方式 | 預期 finding |
| --- | --- | --- | --- |
| L01 | RLS 未啟用 | 建表後不 `ENABLE ROW LEVEL SECURITY` | anon 可讀寫，Confirmed／Critical |
| L02 | Policy 恆真 | `USING (true)` | anon 可讀，Confirmed／High 以上 |
| L03 | 依 user_metadata 授權 | policy 引用 `auth.jwt() -> 'user_metadata'` | 使用者自改 metadata 後越權 |
| L04 | 跨租戶讀取 | policy 只檢查已登入，未檢查擁有者 | B 讀得到 A 的列，Confirmed／Medium |
| L05 | 跨租戶修改 | UPDATE 的 `WITH CHECK` 寬鬆，可改擁有者欄位 | A 可把列轉給別人，Confirmed／High |
| L06 | SECURITY DEFINER view | view 以建立者權限執行 | anon 經 view 讀到受保護資料 |
| L07 | SECURITY DEFINER RPC | 函式可被 anon 執行並回傳資料；另有一個可執行但不回傳資料的對照函式 | 前者 Confirmed，後者 Configuration warning |
| L08 | service_role 進 bundle | 前端以 service_role 建立 client | Confirmed／Critical |
| L09 | INSERT 寬鬆 | 只有 SELECT policy 正確，`WITH CHECK (true)` | anon 可寫入，Confirmed／Critical |
| L10 | 敏感欄位外洩 | 列層級正確，但公開表含 email 欄位 | 敏感欄位提示 |
| L11 | 公開 Storage bucket | bucket 為 public 且含私人檔案 | P2 |
| L12 | OpenAPI 被限制 | 關閉 anon 存取 OpenAPI | M2 改由 bundle 推測仍找到目標（inferred） |
| C01–C04 | **安全對照組** | 正確的 owner-scoped policy、正確的公開表、空表、無資料的使用者 | **不應**產生漏洞 finding；空表與無資料者應為 inconclusive 而非 denied |

splinter 對每個情境會不會報，**必須實測**，不可預設。哪些情境成為 probe-only 案例，以 MS4 的結果為準。

### 每個情境的檔案

```text
lab/L04_cross_tenant_read/
├── migration.sql      # schema 與 policy（lab-dev）
├── seed.sql           # 以擁有者身分植入已知資料（lab-dev）
├── frontend/          # 最小前端，只為了產生 bundle（lab-dev）
└── expected.yaml      # ground truth（architect 撰寫並凍結）
```

`expected.yaml` 逐列寫出每個身分、每種操作的預期三態結果：

```yaml
scenario: L04
vulnerable_cases:            # 每一項是一個「漏洞案例」，benchmark 以此為單位計分
  - {table: notes, op: select, role: user_b, rows: [note_a1], expect: allowed, rule: CROSS_TENANT_READ}
safe_cases:                  # 應判定為 denied 或 inconclusive 的格子
  - {table: notes, op: select, role: anon, rows: [note_a1, note_b1], expect: denied}
  - {table: notes, op: select, role: user_a, rows: [note_b1], expect: denied}
inconclusive_cases:
  - {table: empty_table, op: select, role: user_b, expect: inconclusive}
splinter_expected: measure   # MS4 實測後由 architect 填入 reported | not_reported
```

### 植入資料範例

| 資料列 | 擁有者 | anon | User A | User B |
| --- | --- | --- | --- | --- |
| profiles #1 | User A | 不可讀 | 可讀 | 不可讀 |
| profiles #2 | User B | 不可讀 | 不可讀 | 可讀 |
| posts #1（已發佈） | User A | 可讀 | 可讀 | 可讀 |
| posts #2（草稿） | User A | 不可讀 | 可讀 | 不可讀 |

Lab 的 Postgres 開啟 `log_statement = mod`，所有寫入都留在資料庫 log，用來獨立驗證 audit 模式 0 次寫入。

### 執行方式

- `python -m rlsentry.bench --scenario L04`：以 Supabase CLI 啟動該情境、套用 migration 與 seed、執行 RLSentry、與 `expected.yaml` 比對。
- `python -m rlsentry.bench --json logs/bench.json`：跑全部情境，輸出 §9 定義的 JSON。

### 真實目標來源（只限有授權者）

1. **Lab**：唯一有完整 ground truth 的集合，**所有量化指標只在這裡計算**。
2. **自行部署的開源 Supabase 專案**：部署到自己的帳號。
3. **自己用 AI builder 生成的 app**：以一般使用者的 prompt 生成，連到自己的 Supabase；最接近真實威脅族群。
4. **他人專案**：僅限取得書面同意並約定範圍與時間。

第 2 至 4 組只回報「找到哪些問題、人工確認是否屬實」，不與第 1 組混算指標。

## 9. 測試與評估

### 測試層級

| 層級 | 對象 | 工具 | 何時跑 |
| --- | --- | --- | --- |
| 單元測試 | regex 擷取、JWT 解碼、key 分類、expected policy 解析與合併、三態判定、差分、嚴重度與證據等級、報告模板 | pytest、respx | 每次 accept |
| 整合測試 | 對本機 Supabase lab 跑完整管線 | pytest + Supabase CLI | 每個 milestone |
| 安全不變式 | audit 0 次寫入、無授權不執行、輸出無完整 key | pytest（標記 `safety`）+ 資料庫 log | 每次 accept |
| Profile 端到端 | dev、ci、audit 各跑一次完整情境 | pytest（標記 `e2e_profiles`） | MS6、MS7 |
| Benchmark | §8 全部情境 | `python -m rlsentry.bench` | MS4 起每個 milestone、MS7 |
| Holdout | architect 在派工前寫好、subagent 看不到的測試 | `.holdout/<MS>/` | 每個 milestone 驗證 |

單元測試的 fixture 要包含真實框架產出的 bundle 片段（Next.js、Vite、Create React App 各一），避免 regex 只在自己寫的範例上有效。

### 評估指標（以漏洞案例為單位）

- **Recall**：`vulnerable_cases` 中被以 Confirmed 找出的比例。目標 ≥ 95%。
- **Precision**：被判為 Confirmed 的案例中確實是漏洞的比例。目標 ≥ 95%。
- **FPR**：`safe_cases` 中被誤判為漏洞的比例。目標 ≤ 5%。
- **Coverage**：實際測到的（表 × 操作 × 身分）組合佔應測組合的比例，以及 inconclusive 的比例。
- **Runtime**：5、20、50 張表下的執行時間；50 張以內 < 60 秒。
- **Probe-only 案例**：splinter 未報、RLSentry 以 Confirmed 證實的漏洞類型，目標 ≥ 2 類，每類附證據。

```text
Recall = TP / (TP + FN)    Precision = TP / (TP + FP)    FPR = FP / (FP + TN)
```

`logs/bench.json` 必須包含：`tp`、`fp`、`fn`、`tn`、`recall`、`precision`、`fpr`、`coverage`、`runtime`，以及逐情境明細。

**統計上的誠實**：情境數量少，百分比的變異很大。報告必須同時列出原始數量（例如 38/40），也不宣稱可推論到所有 Supabase 專案。

### 展示情境

最有說服力的 demo 是：splinter 沒報，RLSentry 以 Confirmed 證據顯示 User A 透過正常的 Supabase API 讀到 User B 的私人資料，並附重現指令與修補 SQL。L04 是最可能的候選，但必須以 MS4 實測結果選定。

## 10. 技術棧與專案結構

| 用途 | 選用 | 理由 |
| --- | --- | --- |
| 語言 | Python 3.12 | 資安工具生態成熟 |
| HTTP | httpx（async） | async、易於 mock |
| 並行與限速 | asyncio + semaphore／token bucket | 標準庫 |
| JWT | PyJWT（不驗簽解碼） | 輕量 |
| DB（M4） | psycopg 3 | 官方推薦 |
| 白箱 lint | splinter（固定版本 SQL） | Supabase 官方規則 |
| 資料模型 | Pydantic v2 | 驗證 + JSON 序列化 |
| CLI | Typer | 型別註記產生 CLI |
| 報告 | Jinja2（HTML）、SARIF 2.1.0 | 標準格式 |
| 測試 | pytest、pytest-asyncio、respx、coverage、mutmut | 標準組合 |
| 本機 Supabase | Supabase CLI + Docker | 完整重現 PostgREST、Auth、RLS |
| 品質 | ruff、mypy | 自動化檢查 |
| CI | GitHub Actions | 也是交付的介面之一 |

```text
rlsentry/
├── contracts/          # 型別與函式簽名（architect）
├── safety/             # gate.py、mask.py、ratelimit.py、mode.py
├── recon/              # M1
├── discovery/          # M2
├── probe/              # M3：read.py、cross_tenant.py、write.py、seed.py、diff.py
├── whitebox/           # M4
├── report/             # M5：json、html、sarif、fix_sql 模板
├── rules/              # 嚴重度與證據等級規則
├── policy/             # expected policy 解析、init 草稿
├── pipeline.py         # run_scan()
├── cli.py              # Typer
├── bench/              # python -m rlsentry.bench
└── action/             # GitHub Action（action.yml）
lab/                    # §8 情境
tests/                  # 可見測試（architect）
.holdout/               # holdout 測試（architect；subagent 不可讀）
```

所有安全相關邏輯集中在 `safety/`，審查時看一個套件就能確認唯讀、授權與遮罩是否被正確套用。

## 11. 開發流程：雲端全自主開發加模組關卡

產品在 Claude Code 雲端 session（claude.ai/code）中由代理自主開發。ticket 層級的驗收全部自動化；每個 milestone 結束時流程暫停，專案負責人以 SSH 簽章核准後才進入下一個。機制細節以 `harness/` 與 `README_HARNESS.md` 為準。

### 角色

| 角色 | 負責 | 不可做 |
| --- | --- | --- |
| `architect`（主 session） | 規劃 ticket、撰寫合約（`rlsentry/contracts/`）、可見測試、holdout 測試、ground truth（`lab/**/expected.yaml`）；派工；執行驗收；撰寫 ADR、驗證清單、`PRODUCTION_LOG.md`、`USAGE.md` | 撰寫產品實作程式；修改凍結檔；手動合併；寫入 approvals 分支 |
| `recon-dev` | safety 層、M1 | 修改測試、合約、docs、expected.yaml |
| `probe-dev` | M2、M3、`policy/` | 同上 |
| `whitebox-dev` | M4、M5、CLI、Python API、GitHub Action、bench runner | 同上 |
| `lab-dev` | `lab/` 的 migration、seed、前端 | 撰寫 expected.yaml 或偵測規則 |
| `auditor`（唯讀，不同模型等級） | 對照 SPEC 產出追溯表、審查 safety 與寫入路徑、找 overfitting | 修改任何檔案 |
| 專案負責人 | 在每個 milestone 獨立驗證並簽章核准或要求修改 | — |

### Milestone

| MS | 內容 | 審查重點 |
| --- | --- | --- |
| STAGE0 | 護欄測試（玩具 ticket） | hook 有記錄、守衛會擋、worktree 隔離、Stop hook 會暫停 |
| MS0 | 合約、expected policy 格式、ticket 計畫、ground truth 格式 | 合約與 ground truth 忠於 SPEC：這裡的錯會傳到所有下游 |
| MS1 | Lab（L01–L12、C01–C04，含植入資料與 `log_statement`）+ safety 層 | 情境真的埋了漏洞、對照組安全；唯讀與授權閘門擋得住 |
| MS2 | M2 + M3 讀取（三態、跨租戶讀取、差分、`rlsentry init`） | inconclusive 沒被當成安全；沒有下載資料 |
| MS3 | M3 寫入（讀回驗證、canary 清理） | 寫入只在 disposable DB；最終狀態驗證正確 |
| MS4 | M4 Whitebox；第一次完整 benchmark | probe-only 案例真實；SECURITY DEFINER 只在取得資料時算漏洞 |
| MS5 | M1 Recon | service_role 偵測；anon key 沒被誤報 |
| MS6 | M5 報告、CLI、Python API、GitHub Action、三種 profile | audit 無法寫入；報告分證據等級；CI 只在 Confirmed 時失敗 |
| MS7 | 整合、benchmark 五項指標、`USAGE.md`、demo | 照 `USAGE.md` 親手跑一次；指標達標並附原始數量 |

順序理由：先建立 Lab 與 ground truth，再做最核心的動態探測，最後才做 Recon 與介面。Recon 延後但不刪除，因為 service_role 外洩成本低、衝擊高，且 audit profile 需要它。

### Ticket

- 一張 ticket 只做一件事：一個函式或一個合約、或一個 lab 情境；最多 3 個檔案、約 200 行、不超過 10 個測試；只有一個負責的 subagent 類型。
- 格式見 `harness/templates/ticket.md`；`depends_on` 與 `allowed_paths` 必填。
- 排程器只派出依賴都已**合併**的 ticket；改到同一檔案的 ticket 不並行；同時最多 6 個；關鍵路徑優先。
- 同一張 ticket 失敗 5 次即 blocked，依賴它的 ticket 一併 blocked 並記錄原因。

### 驗收閘門（每張 ticket）

`python3 harness/tickets.py accept <ID> --branch <branch>` 是進入主線的唯一路徑：範圍檢查（只改 `allowed_paths`）→ 作弊檢查（不得新增 skip、xfail、`type: ignore`、`noqa`）→ 試合併 → ruff、該 ticket 的測試、已驗收 ticket 的回歸測試 → 以帶 `RLSentry-Accepted: <ID>` trailer 的 merge commit 合併，並推送狀態。

### 模組關卡（每個 milestone）

1. 所有 ticket 完成或 blocked 後，architect 派 auditor 審查，修正真實問題。
2. architect 撰寫 `docs/verification/<MS>-v<N>.md`（範本見 `harness/templates/verification.md`）：最多 16 項，第一項固定為獨立驗證，每一項附指令或檔案行號與預期結果；列出與 SPEC 的偏差與已知限制。
3. Stop hook 允許暫停並推送狀態。
4. 專案負責人在自己的電腦或一個全新的雲端 session 上：`git diff harness-frozen -- <凍結路徑>` 必須為空 → `make verify-milestone MS=<MS>` → `python3 host/approve.py` 簽章並推送到 `rlsentry-approvals` 分支。
5. 要求修改時，architect 把每條意見轉成同一 milestone 的 ticket，產出 v<N+1> 清單並列出差異。
6. 已核准的 milestone 被發現有錯時，architect 必須開 `reopen` ticket；修好後該 milestone 需重新核准，之後的 milestone 一併重新鎖定。

### 紀錄與交付

| 檔案 | 內容 | 誰寫 |
| --- | --- | --- |
| `logs/events.jsonl`、`logs/messages/` | 每次派工指示、subagent 回報、阻擋、驗收、停止 | hook 自動 |
| `CHECKLIST.md` | 從 ticket 檔與 git 歷史自動產生的進度清單 | harness |
| `docs/DECISIONS.md` | ADR；D2–D4 必須在交付前決定並記錄 | architect |
| `PRODUCTION_LOG.md` | 每個 milestone 的時間軸、嘗試次數、失敗與修正、holdout 雜湊、指標 | architect |
| `docs/verification/` | 各 milestone 驗證清單與 `traceability.md`（auditor 追溯表） | architect、auditor |
| `USAGE.md` | 安裝、設定、三種 profile（每種附 `<!-- doctest -->` 可執行範例）、已知限制 | architect |
| `BENCHMARK_REPORT.md` | §9 五項指標、原始數量、逐情境結果、probe-only 案例 | architect |

人看的文件一律使用繁體中文。

### Token 使用原則

開發期間大部分成本來自代理之間的溝通與反覆讀取上下文。以下原則用來降低成本，但**不得降低品質**：測試、holdout、auditor、驗收閘門、ADR 與驗證清單的必要內容一律不變；兩者衝突時以正確性為準。

| 原則 | 做法 | 強制方式 |
| --- | --- | --- |
| 每個 milestone 開新 session | 核准後由專案負責人開新 session；architect 從檔案重建狀態 | 流程規定（README） |
| 派工只引用，不貼上 | 派工訊息只寫 `Ticket: T-xxx` 與必要的新資訊，subagent 自己讀 ticket 檔 | 派工 hook 拒絕超過 2000 字元的訊息 |
| 回報固定格式 | subagent 回報最多 15 行：分支、commit、檔案、測試數量、模糊處 | agent 定義 |
| 只讀需要的規格 | 以 `harness/spec.py` 讀取指定章節或需求列，不讀整份 SPEC | CLAUDE.md |
| 失敗只傳摘要 | 驗收失敗時只回傳失敗的測試與錯誤行，完整輸出存在 logs/ | harness 自動壓縮 |
| 單一語言 | 人看的文件只用繁體中文（專業術語保留英文），絕不雙語 | CLAUDE.md |
| auditor 只看本 milestone | 審查範圍限定為本 milestone 的 diff | 派工時提供 Base commit |
| 重複失敗就改 ticket | 同一原因失敗兩次，改寫 ticket 而不是繼續重派 | architect 規則 |

### 開發期間的安全邊界

- 雲端 environment 的網路白名單只允許套件來源與 GitHub；RLSentry 在開發中只對 localhost 的 lab 發出請求。
- 不在 environment 中放任何真實秘密。
- 禁止強制推送、改寫歷史、建立標籤、寫入 approvals 分支。

## 12. 決策

| 編號 | 主題 | 狀態 |
| --- | --- | --- |
| D1 | 主打情境 | **已決定**：dev、ci、audit 三種 profile 共用同一核心 |
| D2 | 是否支援無頭瀏覽器（Playwright）抓動態 chunk | 由 architect 於 MS5 決定並寫 ADR |
| D3 | Web 介面範圍 | **已決定**：移除 Web 報告頁，改由 CLI 產生靜態 HTML |
| D4 | 是否延伸到 Firebase Security Rules | 由 architect 決定並寫 ADR；預設列為未來工作 |
| D5 | 開發環境 | **已決定**：Claude Code 雲端 session，SSH 簽章核准 |

## 13. 風險

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| Expected policy 預設錯誤，誤報過多 | 工具不可信 | 無法判斷時給 Review；`rlsentry init` 產生草稿讓使用者確認 |
| 測試資料不足造成漏報（把 count=0 當成 denied） | 漏報 | 三態結果；lab 一律植入資料；inconclusive 不得寫成安全 |
| 寫入探測造成副作用 | 資料被改動 | audit 禁止寫入；dev／ci 僅限 disposable DB；讀回驗證；資料庫 log |
| Supabase 改變 API 或 key 格式 | M1、M2 失效 | fixture 鎖定版本；bundle 推測作為 fallback |
| splinter 已涵蓋我們以為它抓不到的情境 | probe-only 論點變弱 | 先實測再下結論；重點轉向跨租戶與金鑰外洩 |
| 測試與實作出自同一模型家族，共享盲點 | 錯誤通過驗收 | holdout、auditor 用不同模型等級、專案負責人每個 milestone 獨立驗證 |
| 代理修改護欄 | 驗收失去意義 | 本機 `harness-frozen` 標籤比對；簽章核准；provenance 從 git 歷史重算 |
| 範圍過大 | 交付不完整 | P0 優先、P2 延後；每個 milestone 都是可用版本 |
| 法律爭議 | 嚴重 | 只測 §8 授權目標；授權閘門；不確定就先問 |

## 14. 參考資料

- CVE-2025-48757：Lovable 應用的 RLS 不足事件（NVD；Pluto Security 技術分析）
- Supabase：splinter（Postgres linter）、Database Advisors、Row Level Security、API Keys、Postgres Roles 文件
- PostgreSQL：Row Security Policies（CREATE POLICY）、System Catalogs
- PostgREST：Tables and Views、Prefer header、OpenAPI
- OWASP API Security Top 10, 2023
- M. Meli, M. R. McNiece, B. Reaves, "How Bad Can It Git? Characterizing Secret Leakage in Public GitHub Repositories," NDSS 2019
- RFC 7519：JSON Web Token
- 中華民國刑法第 358–362 條
- Anthropic：Claude Code 文件（Subagents、Hooks、Claude Code on the web）
