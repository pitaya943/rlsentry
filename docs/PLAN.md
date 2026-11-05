# Ticket 計畫（MS1–MS7）

MS0 產出。每個 milestone 開始時 architect 會依此計畫寫出正式 ticket（`docs/tickets/`），屆時可能再拆細；
與本計畫不同之處記錄在該 milestone 的 PRODUCTION_LOG。⚠ = 高風險（ADR-005，類別編號附在括號內），
會另開僅供審查的分支／PR。合約與可見測試的 architect ticket 每個 milestone 都有，以下不另列。

## MS1 Lab benchmark + Safety
| 預計 ticket | agent | 檔案 | 依賴 |
| --- | --- | --- | --- |
| lab 共用設定：Supabase CLI config、`log_statement = mod`、兩個測試帳號（LAB_USERS） | lab-dev | `lab/_shared/**` | — |
| ⚠(5) L01–L12、C01–C04 各一張：migration + seed + 最小前端，依 expected.yaml 的 `plant`／`schema`／`rows` | lab-dev | `lab/<id>/**`（不含 expected.yaml） | lab 共用設定 |
| lab 驗證測試：每個 case 的 `expect` 對實際 lab 成立（architect 測試，需 Docker） | architect | `tests/lab/**` | 各情境 |
| ⚠(1) `safety/gate.py` 授權閘門（NFR-02） | recon-dev | `rlsentry/safety/gate.py` | — |
| ⚠(1)(2) `safety/mode.py` `require_write_allowed`（audit 一律拒絕；登入例外；dev 只限 localhost；ci 另可寫 `write_hosts` 明列的主機，ADR-014 補記） | recon-dev | `rlsentry/safety/mode.py` | 合約加 `write_hosts`（architect） |
| ⚠(1)(3) `safety/mask.py`（前 6 後 4） | recon-dev | `rlsentry/safety/mask.py` | — |
| ⚠(1) `safety/ratelimit.py`（semaphore + token bucket） | recon-dev | `rlsentry/safety/ratelimit.py` | — |
| `safety/http.py`：唯一的 HTTP client（User-Agent、限速、寫入閘門） | recon-dev | `rlsentry/safety/http.py` | mode、ratelimit |

## MS2 M2 Discovery + M3 讀取
| 預計 ticket | agent | 檔案 |
| --- | --- | --- |
| OpenAPI 解析（FR-04） | probe-dev | `discovery/openapi.py` |
| bundle 推測 `.from()`／`.rpc()`（FR-05） | probe-dev | `discovery/bundle.py` |
| 目標合併與 unknown 標記 | probe-dev | `discovery/merge.py` |
| ⚠(3) 登入取得 JWT（FR-07） | probe-dev | `probe/session.py` |
| ⚠(4) 三態讀取（HEAD + count，FR-06） | probe-dev | `probe/read.py` |
| ⚠(4) 跨租戶讀取與 audit 主鍵交集（FR-08） | probe-dev | `probe/cross_tenant.py` |
| ⚠(4) 差分 `actual − expected`（FR-10） | probe-dev | `probe/diff.py` |
| ⚠(4) 證據等級與嚴重度（含敏感欄位升級） | probe-dev | `rules/severity.py` |
| `rlsentry init` 草稿（FR-15） | probe-dev | `policy/init.py` |

## MS3 M3 寫入
| 預計 ticket | agent | 檔案 |
| --- | --- | --- |
| ⚠(2) 植入已知資料（dev／ci） | probe-dev | `probe/seed.py` |
| ⚠(2)(4) INSERT／UPDATE／DELETE 探測與讀回驗證（FR-09） | probe-dev | `probe/write.py` |
| ⚠(2) canary 清理與清理失敗回報 | probe-dev | `probe/cleanup.py` |
| ⚠(2)(3) L03 user_metadata 前置條件（修改後還原） | probe-dev | `probe/metadata.py` |

## MS4 M4 Whitebox + 第一次完整 benchmark
| 預計 ticket | agent | 檔案 |
| --- | --- | --- |
| ⚠(2) splinter 固定版本 SQL 執行（唯讀連線、`SET LOCAL pgrst.db_schemas`） | whitebox-dev | `whitebox/splinter.py` |
| `pg_policies` 讀取 | whitebox-dev | `whitebox/policies.py` |
| ⚠(4) confirmed／lint_only／probe_only 交叉比對 | whitebox-dev | `whitebox/correlate.py` |
| ⚠(4) bench runner 與計分（ADR-011） | whitebox-dev | `bench/**` |
| 依實測填入 `splinter_expected` | architect | `lab/**/expected.yaml` |

## MS5 M1 Recon（D2 於此決定；實際 ticket 見 docs/tickets/T-180–T-195）
| 預計 ticket | agent | 檔案 |
| --- | --- | --- |
| HTML／chunk 抓取（Next.js、Vite、CRA fixture；FR-01） | recon-dev | `recon/fetch.py` |
| ⚠(3) URL 與 key 擷取、entropy 過濾（FR-02） | recon-dev | `recon/extract.py` |
| ⚠(3) JWT 不驗簽解碼與 key 分類（FR-03；`target` 標籤見 ADR-011） | recon-dev | `recon/classify.py` |

## MS6 M5 Report + 介面 + profiles
| 預計 ticket | agent | 檔案 |
| --- | --- | --- |
| JSON 報告 | whitebox-dev | `report/json.py` |
| HTML 報告（Jinja2） | whitebox-dev | `report/html.py` |
| 修補 SQL 模板 | whitebox-dev | `report/fix_sql.py` |
| SARIF 2.1.0 與 `fail_on` exit code（FR-13） | whitebox-dev | `report/sarif.py`、`report/exit_code.py` |
| ⚠(1) `pipeline.run_scan`（授權 → M1 → M2 → M3 → M4 → M5） | whitebox-dev | `pipeline.py` |
| CLI（Typer）與 Python API（FR-16） | whitebox-dev | `cli.py` |
| GitHub Action | whitebox-dev | `action/**` |
| profile 端到端測試（`e2e_profiles`） | architect | `tests/e2e/**` |
| ⚠(2) MS3 核准意見第 1 點：L03 `USER_METADATA_ESCALATION`（metadata.py 的 escalate→重新登入→重讀→restore）串進 `run_scan`，以 lab 驗證 L03 能被偵測到 | whitebox-dev | `pipeline.py` |
| ⚠(2) MS3 核准意見第 1 點：dev／ci 讀取植入（`seed_known_rows`）串進 `run_scan`，以 lab 驗證（C04 在 dev 可判定） | whitebox-dev | `pipeline.py` |
| ⚠(1) MS3 核准意見第 1 點：遠端 dev／ci 寫入被拒（`WriteRefused`）轉為 inconclusive 寫入 cell 並記入報告，不讓掃描崩潰 | whitebox-dev | `pipeline.py`／`probe/run.py` |
| SPEC §5 M4 第 2 點：pipeline 以 `read_policies` 填入 `ScanReport.policies`，並把設定檔的曝露 schema 傳給 M4（`db_schemas`；MS4 稽核） | whitebox-dev | `pipeline.py` |
| MS3 核准意見第 1 點：L01／L05 寫入植入覆蓋（MS4 以 OpenAPI 欄位型別處理，ADR-034；若仍有缺口於此補齊並更新 benchmark） | probe-dev | `probe/**` |
| ⚠(4) MS4 核准意見第 5 點、稽核 P2 (a)：任一角色在某物件取得資料時，不得抑制**其他角色**的 SECURITY DEFINER 警告（correlate 依 (物件, 角色) 判斷）。**須以測試證明**：一個角色有 confirmed、另一角色只有 lint 的案例仍產生該角色的 SECURITY_DEFINER_EXECUTABLE | whitebox-dev | `whitebox/correlate.py` |
| ⚠(4) MS4 核准意見第 5 點、稽核 P2 (b)：SECURITY_DEFINER_RPC_DATA 只用於確實是 SECURITY DEFINER 的函式；其他 RPC 越權讀取改用正確的規則名稱（新規則需 ADR 與 rule catalog）。**須以測試證明**：SECURITY INVOKER 的 RPC 越權讀取不再標為 SECURITY_DEFINER_RPC_DATA | probe-dev | `rules/severity.py`、`probe/**` |
| ⚠(2) MS4 核准意見第 5 點、稽核 P2 (c)：`splinter_status` 不得寫死 `public`；pipeline 把設定檔的曝露 schema 傳給 M4（`db_schemas`），並與「以 read_policies 填入 ScanReport.policies」一起完成。**須以測試證明**：非 public schema 的 lint 被正確計入，且 ScanReport.policies 有內容 | whitebox-dev | `bench/score.py`、`pipeline.py` |
| ⚠(2) MS4 核准意見第 5 點、稽核 P2 (d)：`read_policies` 補上以 DB log 驗證唯讀的 lab 測試。**須以測試證明**：執行期間 DB log 沒有任何寫入 | architect | `tests/lab/**` |
| MS4 核准意見第 3 點：展示情境 L04 的報告附**重現指令**（curl，key 遮罩）與**修補 SQL**（owner-scoped policy），以 lab 驗證修補後重掃為無漏洞 | whitebox-dev | `report/**` |
| MS4 核准意見第 2 點：runtime 改善——同一身分的多筆主鍵查詢合併為**單一請求**（`id=in.(…)`）以減少請求數；**不得調高預設 rps**（NFR-04、ADR-033）。完成後重新量測 audit、rps 5 下 **5／20／50 張表**；仍未達 50 張 < 60 s 就在 BENCHMARK_REPORT 如實揭露 | probe-dev | `probe/read.py`、`probe/cross_tenant.py` |

## MS7 整合與交付
`make acceptance` 修正、`BENCHMARK_REPORT.md`（五項指標附原始數量）、`USAGE.md`（dev、ci、audit 各一個 doctest）、demo。

- MS4 核准意見第 1 點：MS5（M1）與 MS6（L03 串接等）完成後，於 MS7 **重新跑完整 benchmark**（`python -m rlsentry.bench`），在 BENCHMARK_REPORT 更新 TP／FN／FP／TN 等**原始數量**與 runtime；原始 JSON 存 `docs/benchmark/MS7-bench.json`。
- MS4 核准意見第 2 點：若 MS6 的請求合併未完成，於 MS7 完成並重新量測 5／20／50 張表（同上，不得調高預設 rps）。
