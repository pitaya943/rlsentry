# RLSentry Benchmark 報告（MS5 更新；MS4 初版的數字列在各節的「與 MS4 的差異」）

- 原始輸出：`docs/benchmark/MS5-bench.json`（MS5 最終程式碼，T-193 accept `ec0d1d6b3` 之後執行；MS4 的原始輸出保留在 `docs/benchmark/MS4-bench.json`）。
- 量測：`python -m rlsentry.bench --json <path>`；本機 Supabase lab（Supabase CLI 3.0.0）。MS5 起每個情境先以 M1 recon 掃描 `labctl.serve_frontend` 在 127.0.0.1 提供的前端，M2 的 bundle 推測改用 recon 實際抓到的檔案（ADR-036）。
- splinter：固定版本 `2026.09.1`（commit `e74a9e3`，sha256 `d8d558ba…9349`），ADR-032。
- 計分規則：ADR-011、ADR-033。指標只來自 **dev** profile 的 P0／P1 情境；audit 逐情境另跑，只檢查唯讀與 inconclusive。
- **統計上的誠實**：只有 16 個情境、32 個漏洞案例，百分比的變異很大；以下數字只描述這個 lab，**不推論到所有 Supabase 專案**（SPEC §9）。

## 1. 指標（原始數量優先）

| 指標 | 原始數量 | 比例 | SPEC 目標 | 狀態 |
| --- | --- | --- | --- | --- |
| Recall | TP 30／(TP 30＋FN 2) | 0.938 | ≥ 0.95 | 未達（2 個 FN 皆為 L03，已核准延後至 MS6，見 §2）；MS4 為 29/32 |
| Precision | TP 30／(TP 30＋FP 0) | 1.000 | ≥ 0.95 | 達成 |
| FPR | fp_safe 0／(0＋TN 72) | 0.000 | ≤ 0.05 | 達成 |
| Coverage | 應測格子全部測到 | 1.000 | — | inconclusive 比例 0.073 |
| safe_decided_ratio | 應為 denied 的 safe 案例全部判定為 denied | 1.000 | — | 沒有以「全部 inconclusive」換取低 FPR |
| Runtime（audit、rps 5） | 5 張 7.5 s；20 張 28.5 s；50 張 70.7 s | — | 50 張 < 60 s | **未達**（見 §5；MS5 未改 M2／M3，數字與 MS4 相同） |
| Probe-only 類別 | L02、L04（另有 L12 同類案例；共 6 個案例） | **2 類** | ≥ 2 類 | 達成 |

audit 的 16 個情境：PostgREST 角色在 DB log 的寫入次數全部為 **0**（NFR-01）。

## 2. False negative（2 個，皆為已知且已核准的延後項）

| 案例 | 原因 | 處理 |
| --- | --- | --- |
| L03-V1、L03-V2（USER_METADATA_ESCALATION） | 提權後需以密碼重新登入；`probe()` 只拿到 token（NFR-03）。`metadata.py` 已實作並單元測試，尚未串進 pipeline | MS6 串進 `run_scan` 並以 lab 驗證（MS3 核准意見第 1 點） |
| ~~L08-V1（SECRET_KEY_IN_BUNDLE）~~ | MS4 時 M1 尚未實作 | **MS5 已轉為 TP**（dev 與 audit 皆是；anon key 的 L08-S1 為 TN） |

L11（公開 Storage bucket）是 P2，只列結果、不計分：目前沒有 storage 探測，兩個案例都是 FN。

與第一次執行的差異：第一次 recall 為 27/32，多出的 2 個 FN 是 L05-V1／V2（`work row could not be seeded`）。原因是寫入探測把 `created_by`（uuid）當成文字欄位；T-171／T-172 改為依 OpenAPI 型別挑選文字欄位後，L05 被正確偵測（ADR-034 補記）。

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
| L03 | `rls_references_user_metadata:reports` | reported | （延後 MS6） | lint_only |
| L04 | 無 | not_reported | confirmed | **probe_only** |
| L05 | `rls_policy_always_true:projects` | reported | confirmed | confirmed |
| L06 | `security_definer_view:invoice_summary` | reported | confirmed | confirmed |
| L07 | `anon_／authenticated_security_definer_function_executable` × `get_all_accounts`、`ping_definer` | reported | `get_all_accounts` confirmed；`ping_definer` 無資料 | `get_all_accounts` confirmed；`ping_definer` 只有 SECURITY_DEFINER_EXECUTABLE（config_warning） |
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

**展示情境（SPEC §9）**：選 **L04**。splinter 對 L04 沒有任何 SECURITY lint，RLSentry 以 Confirmed 證據顯示 User B 透過正常 Supabase API 讀到 User A 的私人列（ADR-035）。重現指令與修補 SQL 由 MS6 的報告產生。

## 5. Runtime 未達標

50 張表在 audit、rps 5 下需 70.7 s（目標 < 60 s）。時間幾乎全花在限速：每張表約 1.4 s，以 rps 5 推算約 7 個 GET／HEAD 請求（3 個身分的可見數與已知列查詢）。可能的方向（未實作）：同一身分合併多個主鍵到一個 `in.(...)` 查詢、或在使用者明確同意時提高 rps。ADR-033 決定**不**為了達標而調高預設 rps。

## 6. 下一次量測
- MS4 核准意見第 1 點：MS6（L03 串接）完成後，於 MS7 重新跑完整 benchmark，更新本報告的原始數量（`docs/benchmark/MS7-bench.json`）。
- MS4 核准意見第 2 點：同一身分多筆主鍵合併為單一請求後，重新量測 5／20／50 張表；不調高預設 rps（PLAN 的 MS6 表）。

## 7. 限制
- probe-only 的成立依賴預期政策（expected policy）：L02、L04 之所以能被判為漏洞，是因為掃描器知道「這張表應該只屬於擁有者」。沒有提供預期政策的專案，L04 這類問題不會被判定為 confirmed。
- L07-W1 等 warning 案例只在有提供 DB 連線時才可能出現（M4 是選配）。
- M4 以「物件名」比對（ADR-032）：同一張表上若 lint 與漏洞類型不同，也會標成 confirmed。
- 每個情境只有一種漏洞；真實專案的組合情況不在本 benchmark 的範圍。
- M1 只有 L08 一個計分案例（另有 L08-S1 safe），key 偵測的統計意義很低；主要證據是三個真實框架 fixture 與 holdout。
