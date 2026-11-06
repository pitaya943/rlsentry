# RLSentry Benchmark 報告（MS7 交付版；先前的數字列在各節的「與前次的差異」）

- 原始輸出：`docs/benchmark/MS7-bench.json`（MS7 最終程式碼，T-245 accept `8a6c6339b` 之後執行，依 MS4 核准意見第 1 點；MS4–MS6 的原始輸出保留在 `docs/benchmark/MS4-bench.json`、`MS5-bench.json`、`MS6-bench.json`）。
- **MS7 與 MS6 的差異**：計分欄位（TP／FN／FP／TN、coverage、inconclusive、probe-only、splinter_match、audit 寫入次數）逐情境完全相同；只有逐情境的 `runtime_s` 有 ±0.05 s 以內的差異。MS7 的程式修改（ADR-049 嚴重度、ADR-051 修補 SQL 與提權還原、lab 命令列入口）不影響計分：benchmark 以（目標, 角色, 操作, 規則）比對案例，不比對嚴重度；L07-V1 的嚴重度（MS7 改為 high）由 `tests/lab/test_scan_reads.py` 與 `tests/e2e/test_ci_definer_severity.py` 在 lab 驗證。
- 量測：`python -m rlsentry.bench --json <path>`；本機 Supabase lab（Supabase CLI 3.0.0）。**MS6 起 bench 直接呼叫產品的 `run_scan`**（授權 → M1 → S4 → M2 → M3 → M4 → M5，ADR-042 #7），所以量到的就是使用者實際執行的路徑；dev 包含讀取植入、寫入探測與 L03 提權。
- splinter：固定版本 `2026.09.1`（commit `e74a9e3`，sha256 `d8d558ba…9349`），ADR-032。
- 計分規則：ADR-011、ADR-033。指標只來自 **dev** profile 的 P0／P1 情境；audit 逐情境另跑，只檢查唯讀與 inconclusive。
- **統計上的誠實**：只有 16 個情境、32 個漏洞案例，百分比的變異很大；以下數字只描述這個 lab，**不推論到所有 Supabase 專案**（SPEC §9）。

## 1. 指標（原始數量優先）

| 指標 | 原始數量 | 比例 | SPEC 目標 | 狀態 |
| --- | --- | --- | --- | --- |
| Recall | TP 32／(TP 32＋FN 0) | 1.000 | ≥ 0.95 | 達成（MS5 為 30/32：L03 ×2 在 MS6 轉為 TP） |
| Precision | TP 32／(TP 32＋FP 0) | 1.000 | ≥ 0.95 | 達成 |
| FPR | fp_safe 0／(0＋TN 72) | 0.000 | ≤ 0.05 | 達成 |
| Coverage | 應測格子全部測到 | 1.000 | — | inconclusive 比例 0.064（MS5 為 0.073） |
| safe_decided_ratio | 應為 denied 的 safe 案例全部判定為 denied | 1.000 | — | 沒有以「全部 inconclusive」換取低 FPR |
| Runtime（audit、rps 5） | 5 張 5.6 s；20 張 20.7 s；50 張 **50.8 s** | — | 50 張 < 60 s | **達成**（與 MS6 相同；MS5 為 7.5／28.5／70.7 s；同一身分的已知主鍵合併為單一請求，ADR-040；rps 未調整） |
| Probe-only 類別 | L02、L04（另有 L12 同類案例；共 6 個案例） | **2 類** | ≥ 2 類 | 達成 |

audit 的 16 個情境：PostgREST 角色在 DB log 的寫入次數全部為 **0**（NFR-01）。16 個情境 dev 與 audit 的 `splinter_match` 全為 true。

## 2. False negative
沒有計分的 FN。L11（公開 Storage bucket）是 P2，只列結果、不計分：沒有 storage 探測，兩個案例都是 FN（不變）。

與前次的差異：
- **L03-V1、V2 轉為 TP**：pipeline 在 dev 執行 L03 提權（使用者把自己的 user_metadata 設成 role=admin、以密碼重新登入、重讀不該看到的已知列），結束後一律還原（ADR-042 #6、ADR-047）。
- 派工前的參考 benchmark 曾在 L05 出現 2 個 USER_METADATA_ESCALATION 偽陽性（寫入探測的擁有者轉移改變了基準）；改為「提權前重測基準」後消失（ADR-042 補記）。
- C04 在 dev 仍為 inconclusive（沒有 INSERT policy，植入回 403）；這是正確的結果，不是 FN（ADR-042 #5）。

## 2b. M1 Recon（MS5 新增）
- L08：前端以 `createClient(url, <service_role JWT>)` 與 `createClient(url, <anon JWT>)` 打包。recon 在 dev 與 audit 都只產生一個 finding：`target = jwt:service_role`、SECRET_KEY_IN_BUNDLE、Critical、confirmed；anon key 只記為 publishable 的 KeyFinding（L08-S1 為 TN）。報告中的 key 皆為前 6 後 4 遮罩。
- 其他 15 個情境的前端都含 anon key：recon 全部沒有 finding（`tests/recon/test_lab_frontends.py`）。
- key finding 不經 M4 correlate，所以 L08 **不在** probe-only 清單（否則會被灌水成第 3 類）。
- 真實框架驗證（不屬於 benchmark 計分）：Next.js 15、Vite 8、CRA 5 三個實際建置的 fixture，延遲載入的 chunk 全部找到、key 清單完全正確、無誤報（`tests/recon/test_recon_fixtures.py`，見 `tests/recon/fixtures/README.md`）。

## 3. splinter 實測與交叉比對

| 情境 | splinter（SECURITY 類）| `splinter_expected` | 實測 M3 | 交叉比對 |
| --- | --- | --- | --- | --- |
| L01 | `rls_disabled_in_public:customers` | reported | confirmed | confirmed |
| L02 | 無 | not_reported | confirmed | **probe_only** |
| L03 | `rls_references_user_metadata:reports` | reported | USER_METADATA_ESCALATION confirmed（dev） | confirmed |
| L04 | 無 | not_reported | confirmed | **probe_only** |
| L05 | `rls_policy_always_true:projects` | reported | confirmed | confirmed |
| L06 | `security_definer_view:invoice_summary` | reported | confirmed | confirmed |
| L07 | `anon_／authenticated_security_definer_function_executable` × `get_all_accounts`、`ping_definer` | reported | `get_all_accounts` confirmed；`ping_definer` 無資料 | `get_all_accounts` confirmed（M3 給 ANON_READ_OWNER_SCOPED／CROSS_TENANT_READ，M4 依 lint 改標 SECURITY_DEFINER_RPC_DATA，ADR-039；MS7 起改標時保留較高的嚴重度：anon High、使用者 Medium，ADR-049）；`ping_definer` 只有 SECURITY_DEFINER_EXECUTABLE（config_warning） |
| L08 | 無 | not_reported | M1：`jwt:service_role` → SECRET_KEY_IN_BUNDLE（Critical）；`jwt:anon` 無 finding | 不適用（key finding 不經 correlate，ADR-036 #7） |
| L09 | `rls_policy_always_true:feedback` | reported | confirmed | confirmed |
| L10 | 無 | not_reported | 只有 SENSITIVE_COLUMN_PUBLIC 警告 | — |
| L11 | 無（沒有任何 lint） | not_reported | （P2，未探測） | — |
| L12 | `rls_enabled_no_policy:audit_log`（不在漏洞目標上） | not_reported | `diary_entries` confirmed | `diary_entries` **probe_only**；`audit_log` lint_only |
| C01–C04 | 無 | not_reported | 無漏洞 | — |

`tests/lab/test_splinter_expected.py` 逐情境重跑 splinter，斷言實測結果等於 `expected.yaml`。

## 4. Probe-only 案例（SPEC §9：splinter 未報、RLSentry 以 Confirmed 證實）

| 類別 | 案例 | 證據 | splinter 為何沒報（不是 splinter 的缺陷） |
| --- | --- | --- | --- |
| L02 Policy 恆真（SELECT `USING (true)`） | L02-V1（anon）、V2、V3 | 以已知主鍵 HEAD count 讀到預期不可見的列 | 0024 `rls_policy_always_true` 依設計排除 SELECT（原始碼註解：SELECT `USING (true)` 常是刻意的公開讀取） |
| L04 跨租戶讀取（只檢查已登入） | L04-V1（user_b 讀 A 的列）、V2 | 同上，以對方的已知主鍵 | 靜態 lint 無法知道「這張表應該只屬於擁有者」；這需要預期政策（expected policy） |
| （與 L02 同類）L12 | L12-V1（anon 讀 `diary_entries`） | 同上；目標由 bundle／policy 找到 | 漏洞本身是 `TO anon USING (true)` 的 SELECT policy，與 L02 同類；「OpenAPI 受限」是發現方式而非漏洞類型，所以**不另計一類**（MS4 auditor） |

**展示情境（SPEC §9）**：選 **L04**。splinter 對 L04 沒有任何 SECURITY lint，RLSentry 以 Confirmed 證據顯示 User B 透過正常 Supabase API 讀到 User A 的私人列（ADR-035）。MS6 的報告附遮罩後的 curl 重現指令與修補 SQL（DROP 過寬的 `notes_select`、建立 `auth.uid() = owner_id` 的 policy）；`tests/e2e/test_demo_l04.py` 原樣套用修補 SQL 後重掃，沒有任何 confirmed 漏洞。

## 5. Runtime
50 張表在 audit、rps 5 下為 50.8 s（目標 < 60 s，達成）。改善來自 ADR-040：每個（目標, 身分）原本送兩個 HEAD count（不該看到／應該看到的已知列各一），改為一個只取主鍵的 GET，每張表的請求由 7 個降為 5 個。預設 rps 5 與並行數 4 都沒有調整（NFR-04、ADR-033）。runtime 只計 M2＋M3（`report.timings`）。

## 6. 量測紀錄
- MS7（交付）：已依 MS4 核准意見第 1 點以最終程式碼重跑（`docs/benchmark/MS7-bench.json`，2026-11-06，`python -m rlsentry.bench --json docs/benchmark/MS7-bench.json`，總耗時 5 分 20 秒）。
- runtime 與 MS6 到 0.1 s 都相同，原因是時間由限速器決定：每張表 5 個請求（ADR-040）、rps 5、並行 4，請求數不變時時間幾乎固定。這也表示 runtime 對 lab 的機器效能不敏感，但對**請求數**敏感：表的數量或角色增加時會線性增加。

## 7. 限制
- probe-only 的成立依賴預期政策（expected policy）：L02、L04 之所以能被判為漏洞，是因為掃描器知道「這張表應該只屬於擁有者」。沒有提供預期政策的專案，L04 這類問題不會被判定為 confirmed。
- L07-W1 等 warning 案例只在有提供 DB 連線時才可能出現（M4 是選配）。
- M4 以「物件名」比對（ADR-032）：同一張表上若 lint 與漏洞類型不同，也會標成 confirmed。
- 每個情境只有一種漏洞；真實專案的組合情況不在本 benchmark 的範圍。
- dev 的 M3 計時包含讀取植入、寫入探測、提權與清理；runtime 目標以 audit 量測，不受影響。
- M1 只有 L08 一個計分案例（另有 L08-S1 safe），key 偵測的統計意義很低；主要證據是三個真實框架 fixture 與 holdout。
