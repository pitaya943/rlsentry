# RLSentry 生產檢核清單

自動產生，請勿手改 · 完成 113/118 · 進行中 2 · blocked 1

## [x] STAGE0 護欄測試（玩具 ticket）（已核准）
- [x] T-000 Stage 0 toy ticket — add() plus harness canaries（recon-dev，done，1 次）
- [x] T-001 Stage 0 canary 重跑（人類授權）（recon-dev，done，1 次）
- 驗證清單：docs/verification/STAGE0-v2.md（v2）

## [x] MS0 基礎：合約、expected policy 格式、ground truth（已核准）
- [x] T-010 合約：§6 資料模型與 rule catalog（architect，done，1 次）
- [x] T-011 合約：expected policy 與 rlsentry.yaml（architect，done，1 次）
- [x] T-012 合約：ground truth 格式與 benchmark 輸出（architect，done，1 次）
- [x] T-013 合約：模組介面與相依套件（architect，done，1 次）
- [x] T-014 可見測試：policy 解析三函式（architect，done，1 次）
- [x] T-015 Ground truth：L01–L03（architect，done，1 次）
- [x] T-016 Ground truth：L04–L06（architect，done，1 次）
- [x] T-017 Ground truth：L07–L09（architect，done，1 次）
- [x] T-018 Ground truth：L10–L12（architect，done，1 次）
- [x] T-019 Ground truth：C01–C02（architect，done，1 次）
- [x] T-020 Ground truth：C03–C04（architect，done，1 次）
- [x] T-021 policy/resolve.py：resolve_expected（probe-dev，done，1 次）
- [x] T-022 policy/visibility.py：row_permitted（probe-dev，done，1 次）
- [x] T-023 policy/load.py：load_config（probe-dev，done，1 次）
- [x] T-024 Ground truth 與預期 policy 一致性測試（architect，done，1 次）
- [x] T-025 MS1–MS7 ticket 計畫（architect，done，1 次）
- [x] T-026 稽核修正：ProbeResult 已知列語意、Finding.rule 檢查（architect，done，2 次）
- [x] T-027 稽核修正：TablePolicy.primary_key、寫入閘門與 profile 規則（architect，done，1 次）
- [x] T-028 稽核修正：計分定義、lab 慣例、ground truth 隔離（architect，done，1 次）
- [x] T-029 稽核修正：ground truth L05、L07、L09（architect，done，1 次）
- [x] T-030 稽核修正：ground truth L01、L11、L12（architect，done，1 次）
- [x] T-031 可見測試：設定檔 YAML 錯誤不得回顯內容（architect，done，1 次）
- [x] T-032 policy/load.py：YAML 錯誤只回報位置與種類（probe-dev，done，1 次）
- 驗證清單：docs/verification/MS0-v1.md（v1）

## [x] MS1 Lab benchmark + Safety（已核准）
- [x] T-040 pyproject：限定 package discovery，讓 pip install -e .[dev] 在乾淨環境可用（architect，done，1 次）
- [x] T-041 合約：safety 層、ci write_hosts、lab 工具；ADR-016–018（architect，done，1 次）
- [x] T-042 可見測試：safety gate、mode、mask（architect，done，1 次）
- [x] T-043 可見測試：ratelimit、http client（architect，done，1 次）
- [x] T-044 Lab 驗證測試基礎：conftest、oracle、共用 lab 測試（architect，done，1 次）
- [x] T-045 Lab 驗證測試：16 個情境的測試檔（architect，done，1 次）
- [x] T-050 safety/gate.py：authorize 授權閘門（recon-dev，done，1 次）
- [x] T-051 safety/mode.py：require_write_allowed 寫入閘門（recon-dev，done，1 次）
- [x] T-052 safety/mask.py：mask、mask_text（recon-dev，done，1 次）
- [x] T-053 safety/ratelimit.py：RateLimiter（recon-dev，done，1 次）
- [x] T-054 safety/http.py：SafeClient（唯一的 HTTP client）（recon-dev，done，1 次）
- [x] T-060 Lab 共用：Supabase 專案設定與 labctl（lab-dev，done，1 次）
- [x] T-061 Lab L01：RLS 未啟用（lab-dev，done，1 次）
- [x] T-062 Lab L02：Policy 恆真（lab-dev，done，1 次）
- [x] T-063 Lab L03：依 user_metadata 授權（lab-dev，done，1 次）
- [x] T-064 Lab L04：跨租戶讀取（lab-dev，done，1 次）
- [x] T-065 Lab L05：跨租戶修改（lab-dev，done，1 次）
- [x] T-066 Lab L06：SECURITY DEFINER view（lab-dev，done，1 次）
- [x] T-067 Lab L07：SECURITY DEFINER RPC（lab-dev，done，1 次）
- [x] T-068 Lab L08：service_role 進 bundle（lab-dev，done，1 次）
- [x] T-069 Lab L09：INSERT 寬鬆（lab-dev，done，1 次）
- [x] T-070 Lab L10：敏感欄位外洩（lab-dev，done，1 次）
- [ ] T-071 Lab L11：公開 Storage bucket（lab-dev，blocked，1 次） ⚠ blocked：labctl 缺陷（storage policy 未重設）使驗收失敗；情境檔改由 T-080 連同 labctl 修正一起交付
- [x] T-072 Lab L12：OpenAPI 被限制（lab-dev，done，1 次）
- [x] T-073 Lab C01：對照組：owner-scoped（lab-dev，done，1 次）
- [x] T-074 Lab C02：對照組：公開表（lab-dev，done，1 次）
- [x] T-075 Lab C03：對照組：空表（lab-dev，done，1 次）
- [x] T-076 Lab C04：對照組：無資料的使用者（lab-dev，done，1 次）
- [x] T-077 labctl：讓 PostgREST 的寫入出現在 DB log（ADR-019）（lab-dev，done，2 次）
- [x] T-078 合約與測試：DB log 寫入判定改為關鍵字分類（ADR-019）（architect，done，2 次）
- [x] T-079 合約與測試：apply 重設 storage policy、上傳 storage/ 檔案（architect，done，1 次）
- [x] T-080 labctl：apply 清除 storage policy、上傳 storage/ 檔案（lab-dev，done，1 次）
- [x] T-081 稽核修正：oracle 強化（拒絕必須是 RLS 拒絕、正向對照、獨立於掃描器）（architect，done，1 次）
- [x] T-082 稽核修正：safety 合約與測試（fail-closed、RPC 路徑正規化、預設埠、限速數值）（architect，done，1 次）
- [x] T-083 safety/mode.py：未知 profile 拒絕、RPC 路徑正規化（recon-dev，done，1 次）
- [x] T-084 safety/http.py、ratelimit.py：不讀環境 proxy、不保留 cookie、rps 必須有限（recon-dev，done，1 次）
- [x] T-085 labctl：ensure_up 明確設定 log_line_prefix（lab-dev，done，1 次）
- 驗證清單：docs/verification/MS1-v1.md（v1）

## [x] MS2 M2 Discovery + M3 讀取（已核准）
- [x] T-090 合約：M2 Discovery、M3 讀取、labctl.execute；ADR-023、ADR-024（architect，done，1 次）
- [x] T-091 可見測試：M2、M3 讀取單元測試與 labctl.execute 測試（architect，done，1 次）
- [x] T-092 labctl：execute()、query() 唯讀、寫入分類排除字串常值（ADR-022、ADR-024）（lab-dev，done，1 次）
- [x] T-093 可見測試：oracle 變異測試與設計前提測試（ADR-022（architect，done，1 次）
- [x] T-100 discovery/openapi.py：fetch_openapi、parse_openapi（FR-04）（probe-dev，done，1 次）
- [x] T-101 discovery/bundle.py：infer_from_bundle（FR-05）（probe-dev，done，1 次）
- [x] T-102 discovery/merge.py 與 discover.py：合併與 M2 進入點（probe-dev，done，1 次）
- [x] T-103 probe/session.py：測試帳號登入取得 JWT（FR-07）（probe-dev，done，1 次）
- [x] T-104 probe/evidence.py：遮罩後的 curl 重現指令（probe-dev，done，1 次）
- [x] T-105 probe/cross_tenant.py：已知列（主鍵交集，FR-08）（probe-dev，done，1 次）
- [x] T-106 probe/read.py：HEAD + count 的可見數（FR-06）（probe-dev，done，1 次）
- [x] T-107 probe/verdict.py：三態判定（probe-dev，done，1 次）
- [x] T-108 rules/severity.py 與 probe/diff.py：規則、嚴重度與差分（FR-10）（probe-dev，done，1 次）
- [x] T-109 probe/run.py：Probe 階段（MS2 只做讀取）（probe-dev，done，1 次）
- [x] T-110 policy/init.py：rlsentry init 草稿（FR-15）（probe-dev，done，1 次）
- [x] T-111 Lab 整合測試：audit 掃描對照 ground truth（MS2 讀取）（architect，done，1 次）
- [x] T-112 稽核修正（架構師）：寫入分類合約、變異測試理由片語、掃描測試流量檢查、RPC 前提（architect，done，1 次）
- [x] T-113 labctl：write_command、識別字與 $$ 感知的常值移除、log flush sentinel（ADR-024 補記）（lab-dev，done，1 次）
- 驗證清單：docs/verification/MS2-v1.md（v1）

## [x] MS3 M3 寫入（已核准）
- [x] T-120 ADR：驗證清單標籤與 Codespaces 準備、必做變異分級、worktree 規則、verification_steps.html 維護（MS2 核准意見第 1、2、4、6、7 點）（architect，done，1 次）
- [x] T-121 可見測試：write_command 分類測試移出 tests/lab/；labctl 在沒有 fcntl 時仍可 import（MS2 核准意見第 5 點）（architect，done，2 次）
- [x] T-122 labctl：只在 lock() 內 import fcntl（MS2 核准意見第 5 點）（lab-dev，done，1 次）
- [x] T-123 合約：M3 寫入探測（seed／write／cleanup／metadata）、CLEANUP_FAILED 規則、write_rule；ADR-029（architect，done，1 次）
- [x] T-124 可見測試：寫入三態判定、plan_writes、after_filter、seed／write／cleanup／metadata（純函式與 fake client）（architect，done，1 次）
- [x] T-125 Lab 整合與變異測試：dev profile 寫入掃描對照 ground truth、寫入 oracle 變異、holdout（architect，done，1 次）
- [x] T-126 probe/seed.py：dev／ci 植入 canary 已知列（FR-09）（probe-dev，done，1 次）
- [x] T-127 probe/write.py：plan_writes、seed_work_row、send_write、read_back、after_filter（INSERT／UPDATE／DELETE，FR-09）（probe-dev，done，1 次）
- [x] T-128 probe/verdict.py、diff.py、cleanup.py、rules/severity.py：寫入三態判定、規則、清理（probe-dev，done，1 次）
- [x] T-129 probe/metadata.py：L03 user_metadata 提權（修改後還原），USER_METADATA_ESCALATION（probe-dev，done，1 次）
- [x] T-130 probe/run.py：dev／ci 寫入探測串接（seed→plan→work row→write→read_back→verdict→cleanup，含 L03 提權 pass）（probe-dev，done，1 次）
- [x] T-131 修正 test_import.py：以子行程檢查無 fcntl，避免 reload 破壞 lab 的 session flock（T-121 缺陷）（architect，done，1 次）
- [x] T-132 修訂寫入合約與可見測試：每個破壞性寫入探測使用各自新植入的 work row（修正共享列順序危害）（architect，done，1 次）
- [x] T-133 修訂 plan_writes 合約：第 4 參數改為 text_column 名稱（str｜None），不用布林或佔位字串（architect，done，1 次）
- [x] T-134 可見測試：probe() 寫入路徑的 fast fake-client 測試（test_run_writes），並讓 MS2 的寫入 cell 斷言與 milestone 無關（architect，done，1 次）
- [x] T-135 修訂寫入判定合約：依 HTTP 狀態分類（401／403→denied、2xx→讀回、其餘→inconclusive）；run() 不做讀取植入、清理所有 canary（architect，done，2 次）
- [x] T-136 可見測試：寫入狀態分類（新檔 test_write_status）、誠實化 test_scan_writes、test_run_writes 加入 400→inconclusive 與 cleanup 全涵蓋（architect，done，1 次）
- [x] T-137 probe/verdict.py：write_cell 改為依 HTTP 狀態分類（401／403→denied、2xx→讀回、其餘→inconclusive）（probe-dev，done，1 次）
- [x] T-138 修正清理斷言：CLEANUP_FAILED 以 (target, owner) 去重（每位擁有者一筆，非每列一筆）（architect，done，1 次）
- [x] T-139 寫入路徑只對 table（RPC／view 不寫）合約釐清；變異測試改用 disable RLS（architect，done，1 次）
- [x] T-140 test_scan_writes 補上 NFR-01 流量證據：DB log 寫入只由 PostgREST 角色發出、seed.sql 既有列未被更動（稽核 P1）（architect，done，1 次）
- 驗證清單：docs/verification/MS3-v1.md（v1）

## [ ] MS4 M4 Whitebox（進行中）
- [x] T-150 ADR：驗證清單指令品質、progress.py 文件同步；MS6 待辦記入 PLAN（MS3 核准意見第 1–3 點）（architect，done，1 次）
- [x] T-151 合約：M4 Whitebox（splinter 固定版本、唯讀連線、pg_policies、交叉比對）；psycopg 相依；ADR-032（architect，done，1 次）
- [x] T-152 合約：bench runner 與計分（ScenarioResult／BenchReport 增補、splinter_status、probe-only）、labctl.apply_synthetic；ADR-033（architect，done，1 次）
- [x] T-153 合約：由 OpenAPI 取得欄位型別以植入必填欄位（MS3 核准意見第 1 點 L01／L05）；ADR-034（architect，done，1 次）
- [x] T-154 可見測試：whitebox（correlate 純函式、vendored splinter 雜湊、lab 實跑 run_splinter／read_policies 與唯讀）（architect，done，1 次）
- [x] T-155 可見測試：bench 計分（score_scenario、aggregate、splinter_status、probe_only）與 apply_synthetic（architect，done，1 次）
- [x] T-156 可見測試：OpenAPI 必填欄位與型別、fill_required、植入／寫入 body 帶入填值（architect，done，1 次）
- [x] T-157 修正 tests/bench/helpers.py：ProbeResult 缺少必填的 evidence_curl（T-155 缺陷，T-163 回報）（architect，done，1 次）
- [x] T-160 whitebox/db.py 與 splinter.py：唯讀連線、固定版本 splinter SQL、SET LOCAL pgrst.db_schemas（whitebox-dev，done，1 次）
- [x] T-161 whitebox/policies.py：唯讀讀取 pg_policies（whitebox-dev，done，1 次）
- [ ] T-162 whitebox/correlate.py 與 whitebox/run.py：confirmed／lint_only／probe_only 交叉比對、SECURITY DEFINER 規則（whitebox-dev，in_progress，1 次） ← 依賴 T-160✓
- [x] T-163 bench/score.py：score_scenario、aggregate、splinter_status（ADR-011、ADR-033）（whitebox-dev，done，1 次）
- [ ] T-164 labctl：apply_synthetic(n)（runtime 量測用的 n 張 owner-scoped 表）（lab-dev，in_progress，1 次） ← 依賴 T-155✓
- [ ] T-165 bench/run.py 與 bench/__main__.py：`python -m rlsentry.bench`（逐情境 dev＋audit、whitebox、runtime、JSON）（whitebox-dev，todo，0 次） ← 依賴 T-162… T-163✓ T-164… T-167✓
- [x] T-166 discovery/openapi.py：擷取 required 與 column_formats（probe-dev，done，1 次）
- [x] T-167 probe/fill.py＋seed.py＋write.py：植入與 INSERT body 填入必填欄位（probe-dev，done，1 次）
- [ ] T-170 第一次完整 benchmark：依實測填入 splinter_expected、lab 測試、BENCHMARK_REPORT 初版；ADR-035（probe-only 與 demo 情境）（architect，todo，0 次） ← 依賴 T-161✓ T-165… T-166✓

## [ ] MS5 M1 Recon（鎖定）

## [ ] MS6 M5 Report + 介面 + profiles（鎖定）

## [ ] MS7 整合與交付（鎖定）
