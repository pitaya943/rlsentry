# 追溯表（auditor）

## MS0（Base 3a3c611；auditor 報告 2026-11-02，修正見 ADR-014、T-026–T-032）
| 需求／主張 | 檢查它的測試 | 審查時狀態 | 修正後 |
| --- | --- | --- | --- |
| FR-10 expected policy 解析 | tests/contracts/test_policy_contract.py、tests/policy/test_load.py | OK | — |
| FR-10 resolve_expected 規則 1–5 | tests/policy/test_resolve.py | OK | — |
| FR-10 row_permitted | tests/policy/test_visibility.py | OK | — |
| FR-15 未列出表的公開欄位推斷 | 只有 holdout 涵蓋 | PARTIAL | 不變（holdout 有測） |
| NFR-01 audit 為預設 profile | test_policy_contract.py::test_safe_defaults_when_omitted | OK | — |
| NFR-01 audit 中沒有寫入案例 | test_gt_format.py::test_structural_errors_are_rejected | OK | — |
| NFR-01 資料庫 log 0 次寫入 | 無；登入會讓 GoTrue 寫入 auth.* | MISSING（設計） | ADR-014 #2：判準待人類確認，MS1 實作 |
| NFR-02 authorized 預設 false | test_safe_defaults_when_omitted | OK | — |
| NFR-02 確認者與時間（AuthorizationRecord） | 無 | MISSING P2 | MS1 safety/gate.py |
| NFR-03 設定檔無密碼、不讀環境變數 | test_passwords_cannot_be_written_into_the_file、test_env_vars_are_not_read | OK | — |
| NFR-03 ConfigError 不含秘密 | 無，且被違反（F5） | MISSING P1 | tests/policy/test_load_safety.py（T-031、T-032） |
| NFR-04 限速預設 5、>0 | test_safe_defaults_when_omitted、test_invalid_configs_are_rejected | OK | — |
| NFR-06 案例數量 | test_gt_complete.py::test_p0_case_counts | WEAK | 已知限制（O3） |
| §6 known_rows_checked==0 不得為判定 | test_models.py::test_zero_known_rows_can_never_be_a_verdict | OK | — |
| §6 Finding.id 穩定 | test_finding_id_is_stable_and_content_based | OK | — |
| Finding.rule 必須在 RULES | 無 | MISSING P2 | test_finding_rule_must_be_in_catalog（T-026） |
| §5 M5 嚴重度與證據表 | test_rule_catalog_matches_spec_severity_table、test_only_confirmed_rules_are_vulnerabilities | OK | — |
| §8 16 個情境齊全、結構正確 | test_gt_complete.py、test_gt_format.py | OK | — |
| §8 ground truth 與自身 policy 一致 | test_gt_consistency.py | OK（只是自我一致） | — |
| §8 ground truth 與真實 Postgres 一致 | 無；L05 紙上即不成立（G1） | MISSING P0 | L05 已修（T-029）；實測在 MS1 tests/lab |
| §9 bench.json 鍵 | 無 | MISSING P1 | test_bench_report_has_spec_section_9_keys（T-028） |
| §9／ADR-011 計分規則 | 只有 docstring | MISSING P1 | MS4 bench ticket 前補測試 |
| ADR-011 #9 key 以標籤比對 | 無，docstring 矛盾（O5） | MISSING P1 | docstring 已修（T-028）；測試隨 MS4 bench |
| ground truth 隔離（O2） | 無 | — | tests/contracts/test_contract_imports.py（T-028） |

## MS1（auditor 兩部分：safety、lab；Base `c01d68c61`）

| SPEC／決定 | 實作 | 測試 | 狀態（處理後） |
| --- | --- | --- | --- |
| NFR-01 audit 不寫、GET／HEAD 放行 | `rlsentry/safety/mode.py` | `tests/safety/test_mode.py`、`test_http.py` | OK |
| NFR-01 未知 profile 拒絕（fail-closed） | mode.py（T-083） | `tests/safety/test_hardening_mode.py` | 稽核 P2-1 → 已修 |
| ADR-014 #1 登入例外完全比對、只限 POST | mode.py | test_mode.py、test_http.py | OK |
| ADR-014 #3 RPC 不得 POST（含編碼路徑） | mode.py（T-083） | test_mode.py、test_hardening_mode.py | 稽核 P2-2 → 已修 |
| ADR-017 ci write_hosts 完全比對、dev 不寫遠端 | mode.py、`contracts/policy.py` | test_mode.py、test_safety_contract.py、test_hardening_mode.py（預設埠） | OK；P2-3 → 已修 |
| NFR-02 未授權拒絕、記錄確認者與時間 | `rlsentry/safety/gate.py` | `tests/safety/test_gate.py` | OK |
| NFR-02 授權必在任何請求之前 | 無（MS6 pipeline） | 無 | 稽核 P1-1 → ADR-020 #6 延到 MS6（靜態測試＋計數測試） |
| NFR-03 遮罩 6+4、mask_text 冪等 | `rlsentry/safety/mask.py` | `tests/safety/test_mask.py` | OK；套用到所有輸出待 MS6 |
| NFR-04 token bucket、並行上限、rps 有限 | `rlsentry/safety/ratelimit.py` | test_ratelimit.py、test_hardening_client.py | OK；整合測試（預設 5 rps）待 MS6 |
| §5 User-Agent、不跟隨 redirect、不讀 proxy 環境、不留 cookie | `rlsentry/safety/http.py` | test_http.py、test_hardening_client.py | OK（trust_env 只能程式審查） |
| §8 lab 情境植入漏洞、對照組安全 | `lab/<id>/migration.sql`、`seed.sql` | `tests/lab/test_<id>.py`（oracle） | OK：冷啟動 175 passed；oracle 經變異驗證會失敗 |
| oracle 能分辨錯的 lab | `tests/lab/oracle*.py` | 手動變異（C04 USING false、L05 RLS off） | 稽核 P1-1–P1-4 → T-081 已修 |
| NFR-01 DB log 驗證（含 PostgREST CTE 寫入） | `lab/_shared/labctl.py` | test_shared.py、test_shared_writes.py | ADR-019；稽核 P1-5 經實測不成立（GET 唯讀交易） |
| log 前綴明確設定 | labctl.py（T-085） | test_shared_prefix.py | 稽核 P2-1 → 已修 |
| apply 清除前一情境 | labctl.py | test_shared_storage.py（storage） | storage 已涵蓋；role／cluster 層級物件為已知限制（稽核 P2-2） |

## MS2（auditor 兩部分：discovery／probe 邏輯、lab 與測試；Base `eee985f`）

| SPEC／決定 | 實作 | 測試 | 狀態（處理後） |
| --- | --- | --- | --- |
| FR-04 OpenAPI → confirmed 目標、欄位、主鍵 | `rlsentry/discovery/openapi.py` | `tests/discovery/test_openapi.py`；lab：test_design_assumptions（view＝table、PGRST126） | OK |
| FR-05 bundle 推測 inferred | `discovery/bundle.py`、`merge.py`、`discover.py` | test_bundle.py、test_merge.py、test_discover.py；lab：L12 discovery_cases | OK；覆蓋率聲明屬報告 → MS6（ADR-023 補記） |
| FR-06 三態、不下載資料 | `probe/read.py`、`verdict.py`、`run.py` | test_read.py、test_verdict.py、test_run.py；lab：test_scan_reads（只下載主鍵）、test_design_assumptions（*/0 與空表相同、400 非空結果） | OK；稽核 F5 → T-112 收緊 |
| FR-07 測試帳號 JWT | `probe/session.py` | test_session.py（三個 profile、錯誤不洩漏） | OK |
| FR-08 跨租戶讀取、無資料 → inconclusive | `probe/cross_tenant.py`、`verdict.py` | test_cross_tenant.py、test_run.py；lab：C03、C04、L04 | OK（寫入延到 MS3） |
| FR-10 差分 actual − expected | `probe/diff.py`、`rules/severity.py` | test_diff.py、test_severity.py；lab：15 情境、FP = 0 | OK；D1–D3 列為已知限制 |
| FR-15 init 草稿 | `policy/init.py` | tests/policy/test_init.py（load_config 往返） | OK |
| NFR-01 audit 掃描零寫入 | 整個 MS2 只送 GET／HEAD＋登入 | test_run.py（三 profile）、lab test_scan_reads（DB log） | OK |
| ADR-014 #3 RPC 以 GET 呼叫不會寫入 | — | test_design_assumptions（VOLATILE → 405、STABLE 不能 INSERT） | 稽核 S1 → T-112 新增 |
| NFR-03 遮罩 curl 與錯誤訊息 | `probe/evidence.py`、session.py | test_evidence.py、test_session.py | OK；主鍵值進 curl → 已知限制（S2） |
| ADR-022 #3 query 唯讀、execute 原子 | `lab/_shared/labctl.py` | test_shared_execute.py | OK；F4 → T-112 收緊 |
| ADR-022 #3 變異測試以預期原因失敗 | tests/lab/test_oracle_mutations.py | 同左＋holdout 變異版本 | F3 → T-112 改為 case id＋失敗片語 |
| ADR-024 寫入分類排除引號內關鍵字 | labctl.py `write_command` | test_shared_classify.py（純函式）、test_shared_execute.py（端到端） | F1（P1）、F2、F6 → T-112、T-113 |

## MS3 M3 寫入（auditor base bd79ce0；最後 accept 24b347327）

| 需求／ADR-029 決定 | 合約 | 實作 | 真正驗證的測試 | 狀態 |
| --- | --- | --- | --- | --- |
| FR-09 寫入列舉（只列禁止的寫入） | plan_writes | probe/write.py | test_plan_writes.py（all-deny／permit／review／no-token 的精確 plan 集合） | OK |
| FR-09 送 INSERT／UPDATE（值改＋轉移）／DELETE | send_write | probe/write.py | test_write_requests.py（逐 op 的 method／path／params／token／body） | OK |
| FR-09 每個破壞性探測各自新 work row | seed_work_row、WritePlan.work_owner | probe/write.py、run.py | test_write_requests、test_run_writes（stateful fake） | OK |
| FR-09 讀回驗證最終狀態（HEAD count，不下載列） | read_back、write_outcome | probe/write.py、verdict.py | test_write_requests、test_write_verdict | OK |
| 2xx 不等於寫入 → denied 非 allowed | write_cell 步驟 4 | verdict.py | test_write_verdict、test_write_status、test_run_writes（USING→0 列） | OK |
| 狀態分類：401／403→denied、2xx→讀回、其餘→inconclusive（非誤判安全） | write_cell、WRITE_OK_STATUS | verdict.py | test_write_status.py | OK |
| 每筆寫入帶 return=minimal | send_write、seed_* | write.py、seed.py | test_write_requests | OK |
| 清理全涵蓋或回報 CLEANUP_FAILED（不悄悄遺留） | cleanup_seeded、cleanup_findings | cleanup.py、diff.py | test_write_requests、test_write_findings、test_run_writes、test_scan_writes | OK |
| 規則對應（anon→ANON_WRITE/Critical、user→CROSS_TENANT_WRITE/High） | write_rule、RULES | rules/severity.py | test_write_findings.py | OK |
| 寫入只對 kind=="table"（RPC／view 不寫） | probe() docstring | run.py（guard）＋gate RPC ban | test_run_writes（只用 table）＋gate 測試（MS1） | OK |
| audit 不送寫入、寫入 cell NOT_TESTED（NFR-01） | probe() audit 分支 | run.py、safety/mode.py | test_run_writes、test_write_requests、test_metadata、test_scan_reads（DB log 0 寫入） | OK |
| NFR-01 dev 流量證據：真實列未變、PostgREST 寫入只有 I/U/D | — | — | test_scan_writes.traffic_problems（直接讀 DB＋db_writes_since；稽核 P1 → T-140） | OK |
| L03 escalate／restore user_metadata | escalate/restore_user_metadata | probe/metadata.py | test_metadata.py | 單元 OK；MS3 未串接（延後 MS6） |
| dev／ci 讀取植入 seed_known_rows | seed_known_rows | probe/seed.py | test_write_requests | 單元 OK；MS3 未串接（延後 MS6） |

稽核結果：無 P0；P1 ×1（NFR-01 DB log 流量證據缺失）已由 T-140 補上；P2 數項列入 MS3-v1 §5 已知限制。

## MS4 M4 Whitebox（auditor，base 24b3473；第 1 次派工用罄回合未回報，第 2 次只讀程式碼）

| SPEC 項目 | 程式 | 測試 | 狀態 |
| --- | --- | --- | --- |
| FR-11／§5 M4 #1 兩層唯讀連線 | rlsentry/whitebox/db.py:16-18 | tests/lab/test_whitebox_lab.py（Docker） | OK（無單元測試，P2） |
| §5 M4「固定版本」雜湊鎖定 | whitebox/splinter.py:21-31；contracts/whitebox.py:30-41 | tests/whitebox/test_vendored.py | OK |
| §5 M4 #1 `pgrst.db_schemas`（參數化）＋識別字驗證 | splinter.py:78-85 | test_vendored.py（驗證）；test_whitebox_lab.py（實效） | OK |
| M4 交易一律 rollback、不 commit | splinter.py:96-98；policies.py:31-33 | test_whitebox_lab.py（DB log 無寫入） | OK |
| §5 M4 #2 pg_policies | whitebox/policies.py | tests/lab/test_policies_lab.py | OK |
| §5 M4 #3 confirmed／probe_only／lint_only | whitebox/correlate.py | tests/whitebox/test_correlate.py | OK |
| 焦點：SECURITY DEFINER 有資料才是漏洞，否則 config warning | correlate.py:43-62；rules.py（SECURITY_DEFINER_EXECUTABLE vuln=False） | test_correlate.py；tests/lab/test_whitebox_run_lab.py（L07） | OK |
| 焦點：M4 不產生 confirmed | correlate.py:24-28（evidence 取自 RULES） | test_correlate.py | OK |
| 焦點：probe-only 案例真實 | correlate.py:50；bench/score.py:83-84 | test_whitebox_run_lab.py（L02、L04；L12 由 T-175 補上） | OK |
| §9／ADR-011 計分 | bench/score.py:66-135 | tests/bench/test_score.py | OK |
| ADR-033 aggregate、0/0 | score.py:142-160 | tests/bench/test_aggregate.py | OK |
| ADR-033 splinter_status | score.py:30-40 | test_score.py | OK |
| §8 splinter_expected 必須實測 | lab/*/expected.yaml | tests/lab/test_splinter_expected.py（Docker 逐情境實測） | OK |
| NFR-01 audit 寫入 0；破壞時 exit 1 | bench/run.py:54；bench/__main__.py:58 | test_bench_audit_m4.py；exit 1 由 T-175 的 test_main_exit.py 補上 | OK |
| ADR-034 fill_required／OpenAPI 型別／pick_text_column | probe/fill.py；discovery/openapi.py:59-76；probe/run.py:42-54 | test_fill.py、test_seed_fill.py、test_openapi_types.py、test_text_column.py | OK（P1-1 由 T-175／T-176 修正） |

**發現**：P0 無。
- P1-1（採納）：INSERT 探測以受害者 id 填其他 uuid 必填欄位，`WITH CHECK (created_by = auth.uid())` 類政策會得到 403→denied（把可能的漏洞說成安全）。→ T-175／T-176：改填攻擊者自己的 id（anon 仍用 new_owner）。
- P1-2（不成立）：「anon INSERT 送出空字串 uuid」。plan_writes 對所有 INSERT plan 都設定 new_owner（合約），不會發生。
- P2：correlate 以裸物件名比對（多 schema 同名會合併；不同類型 lint 也標 confirmed，已揭露於 BENCHMARK_REPORT §6）；finally 中的 rollback 在連線已斷時可能蓋掉原始錯誤；BENCHMARK_REPORT 章節引用錯誤（已修）；lab 以 superuser 執行 splinter（唯讀由 GUC＋BEGIN READ ONLY 保證，真實專案應建議低權限角色，記入 MS6 USAGE）；test_splinter_expected 的非 Docker 部分是固定值釘選，真正的實測證據是 Docker 參數化部分。
- 抽查情境：L07（W1 在 audit 為 warning_seen、get_all_accounts confirmed、ping_definer 無 confirmed）、L02／L04（probe_only）、L12（diary_entries probe_only、audit_log lint_only）。

### MS4 auditor 第 1 次派工的遲到報告（審到 aa7a8e6，早於 T-175／T-176；實跑全套 `pytest -q`：955 passed）
- 已由 T-175 處理：bench 的 NFR-01 exit 1 路徑沒有測試（現有 tests/bench/test_main_exit.py）；L12 probe-only 沒有測試（現已加入 test_whitebox_run_lab.py）。
- P1（採納，文件更正）：probe-only「3 類」灌水。L12 的漏洞與 L02 同為 SELECT `USING (true)`，「OpenAPI 受限」是發現方式而非漏洞類型 → 更正為 2 類（ADR-035 補記）。
- P1（延後，已記入 PLAN 的 MS6 表）：`ScanReport.policies` 尚無人填入（ADR-032 #8）。
- P2（文件）：BENCHMARK_REPORT 的數字缺原始檔 → 提交 docs/benchmark/MS4-bench.json。
- P2（列入 MS4-v1 第 5 段）：SECURITY DEFINER 警告會因任一角色有資料而全部被抑制；SECURITY_DEFINER_RPC_DATA 名稱套用於所有 RPC 越權讀取；splinter_status 寫死 public、DEFAULT_DB_SCHEMAS 尚未由設定傳入；read_policies 沒有 DB log 唯讀測試；runtime 沒有自動化測試（數字見 bench JSON）。
- P2（不成立）：write.py 在 new_owner 為 None 時送出空字串 uuid —— 所有 INSERT plan 都有 new_owner。
- 安全：P0 無；寫入閘門未變；M4 兩層唯讀、一律 rollback。上游 splinter 2026.09.1 的 sha256 與 vendored 檔相同（auditor 也獨立確認）。

## MS5 M1 Recon（auditor，Base 93e03445d；只讀程式碼的審查，但 auditor 違反派工指示跑了完整測試含 lab：1051 passed）

| 需求（宣稱者） | 真正檢查它的測試 | 狀態 |
| --- | --- | --- |
| FR-01 HTML＋script／modulepreload（T-184／T-186） | test_links.py::test_html_script_urls；test_fetch.py::test_crawl_order_and_scope | OK |
| FR-01 延遲 chunk：Vite import、Next _buildManifest、webpack u()／e()（T-184／T-186） | test_links.py::test_js_chunk_urls_*、test_webpack_*；test_fetch.py::test_webpack_chunks_after_queue_drains；test_recon_fixtures.py::test_framework_lazy_chunks_scanned（三個真實建置） | OK |
| FR-01 source map（註解、header、inline、index map）（T-185／T-186） | test_sourcemap.py；test_fetch.py::test_inline_map_and_header_map；test_links.py::test_source_map_url | OK |
| FR-01／M1「存在 .map 時一併解析」但沒有任何東西指向 map | 無（ADR-036 #2：不盲猜 `<url>.map`） | P2：刻意偏離 SPEC 字面，交人類決定 |
| FR-01 記錄掃描範圍（T-187） | test_recon_fixtures.py::test_framework_lazy_chunks_scanned、::test_cra_missing_map_is_listed_as_skipped；test_fetch.py；test_lab_frontends.py | OK |
| FR-02 Supabase URL（hosted＋自訂網域）（T-183／T-187） | test_extract.py::test_supabase_hosts、::test_client_pairs_*；fixtures（cra 為自訂網域）；test_lab_frontends.py | OK |
| FR-02 疑似 key、M1 第 5 步 entropy（T-183） | test_extract.py::test_generic_*、::test_sb_placeholder_filtered_by_entropy；fixtures 以完整 key 清單斷言（真實 bundle 無誤報） | OK |
| M1 第 4 步 JWT 不驗簽，只留 role／ref／exp（T-182） | test_classify.py::test_decode_* | OK |
| FR-03 service_role／sb_secret → Critical（T-182／T-187） | test_classify.py::test_findings_service_role_is_critical_anon_is_silent；fixtures（nextjs、vite）；test_lab_frontends.py L08 | OK（sb_secret 端到端只有單元測試，P2） |
| FR-03 anon／sb_publishable 永不產生 finding（T-182／T-187） | test_classify.py::test_findings_only_publishable_gives_nothing；test_lab_frontends.py（15 個非 L08 情境 `findings == []`）；fixtures | OK |
| FR-03 unverified → Configuration warning（T-182） | test_classify.py；cra、nextjs fixture | OK |
| NFR-03 遮罩：key、finding、repr、skipped（T-187） | test_recon_masking.py；test_lab_frontends.py::test_l08_report_has_no_raw_key；test_classify.py | OK |
| NFR-03 遮罩：`chunks_scanned`、`KeyFinding.source_file` | 稽核時無 | **P1 S1 → T-192／T-193 修正**（test_report_urls.py） |
| Safety：只 GET、不帶憑證、同源、不跟隨轉址、上限（T-186） | test_fetch.py 多項 | OK（cookie 檢查為空轉：假網站不送 Set-Cookie，P2） |
| serve_frontend：loopback、靜態、離開即關閉（T-188） | tests/labctl/test_serve_frontend.py | OK（「只允許 GET／HEAD」未測，stdlib 預設，P2） |
| bench：key finding 不經 correlate（T-189） | tests/lab/test_bench_recon.py::test_l08_key_is_scored（Docker） | OK（無 Docker-free 單元測試） |
| bench：runtime_s 只計 M2＋M3（T-189） | 無 | P2（程式正確：bench/run.py:46-53） |
| bench：M2 使用 recon 抓到的 sources（T-189） | test_bench_recon.py::test_l12_bundle_inference_uses_recon_sources；test_recon_fixtures.py::test_sources_feed_bundle_inference | OK |
| KeyFinding.label、ReconResult.chunks_skipped（T-180） | test_models.py::test_key_finding_label_is_restricted | OK |

安全審查：
- **S1（P1）**：同源且回 200 的 URL 原樣進入 `chunks_scanned` 與 `KeyFinding.source_file`（含 source map 的 source 名稱）→ T-192／T-193（`report_url`）。
- S2（P2）：`mask_text` 只遮 JWT／sb_ 格式，query string 中的其他 token 不會被遮 → `report_url` 一律省略 query string。
- S3（P2）：帶 userinfo 的 URL 通過同源，httpx 會送 `Authorization: Basic` → `same_origin` 拒絕 userinfo。
- S4（P2，MS6 風險）：`supabase_url` 來自目標 bundle → PLAN 的 MS6 表（pipeline 送請求前必須經設定檔或使用者確認）。
- S5（P2）：大檔先完整下載才檢查大小；重疊檢查為 O(literals × spans) → 已知限制。
- S6（P2）：`KeyFinding` 不檢查 kind／label 一致、`masked` 是否遮罩 → T-192 加 validator。
- 已確認：只送 `GET` 且無 header；同源檢查在上限檢查與請求之前；service_role → CRITICAL／CONFIRMED；bench 中 recon 在計時之前、只有 probe findings 經 correlate。
- 過擬合疑慮：無依測試資料的特例；ENTROPY_MIN 依 fixture 量測；generic key 需要 key 語境名稱，壓縮後名稱無意義時會漏；URL 在執行期組出時 `supabase_url=None`（無測試覆蓋 None 路徑）；16 個 lab 前端形狀相同。
- 交人類親手檢查：(1) S1 修正後，同源 200 URL 的 query 中的 key 不出現在報告；(2) bench/run.py 的計時與 correlate 順序；(3) `.map` 範圍決定（ADR-036 #2）。

## MS6 M5 Report + 介面 + profiles（auditor 兩部分，base 5a41a7327；只讀程式碼）

| 需求 | 程式 | 測試 | 狀態 |
| --- | --- | --- | --- |
| NFR-01 audit 不寫入 | safety/mode.py；probe/run.py（audit 寫入 cell）；pipeline.py（dev／ci 才植入、提權） | tests/pipeline/test_run_scan_safety.py（加上非空斷言，ADR-047）、tests/e2e/test_profiles.py::test_audit_never_writes_by_the_database_log（DB log）、tests/lab/test_policies_readonly.py | 已涵蓋（稽核 P1-4 已修正） |
| NFR-02 授權後才建立唯一的 SafeClient | pipeline.py；safety/gate.py | test_run_scan_safety.py（未授權 0 請求、恰好一個 client）、tests/pipeline/test_static_client.py | 已涵蓋 |
| NFR-03 報告遮罩 | report/{json,html,sarif}.py（最終 mask_text）、cli.py | tests/report/*、tests/cli/test_cli.py、tests/report/test_recon_url.py、tests/pipeline/test_run_scan_errors.py（CLI 崩潰不印祕密） | 稽核 P1-3、P2-1 → T-234／T-235 |
| FR-12 JSON／HTML、證據等級＋嚴重度、curl、修補 SQL | report/{enrich,fix_sql,json,html}.py | tests/report/*、tests/e2e/test_demo_l04.py（套用修補 SQL 後重掃無漏洞） | 已涵蓋 |
| FR-13 SARIF 2.1.0、fail_on exit code | report/{sarif,exit_code}.py、action/action.yml | tests/report/test_sarif.py（官方 schema）、test_exit_code.py、tests/e2e/test_profiles.py::test_ci_fails_only_on_confirmed_high、tests/action/test_action.py | 已涵蓋 |
| FR-15 `rlsentry init` | pipeline.run_init、cli.py | tests/cli/test_cli.py::test_init_writes_a_draft_and_refuses_to_overwrite | 已涵蓋（CLI 層） |
| FR-16 Python API＝CLI＝Action | rlsentry/__init__.py、pipeline.py | tests/e2e/test_profiles.py::test_python_api_is_the_pipeline | 已涵蓋 |
| MS5 第 4 點：高權限 JWT → Critical | contracts/recon.SECRET_JWT_ROLES、recon/classify.py | tests/recon/test_classify_privileged.py、holdout | 已涵蓋 |
| MS5 第 6 點／ADR-043：S4 | safety/endpoint.py、pipeline.py | tests/safety/test_endpoint.py、test_run_scan_safety.py、tests/e2e/test_endpoint_lab.py（lab：API 埠 0 請求） | 已涵蓋 |
| MS5 第 7 點 | tests/lab/test_whitebox_lab.py | 同左 | 已處理（ADR-045） |
| MS4 第 5 點 (a)(b) | whitebox/correlate.py、rules/severity.py | tests/whitebox/test_correlate_roles.py、tests/probe/test_rule_rpc.py | 已涵蓋；(b) 的嚴重度下降交人類決定（ADR-047） |
| MS4 第 5 點 (c)(d) | bench/score.py、pipeline.py（db_schemas）；whitebox/policies.py | tests/bench/test_splinter_schemas.py、test_run_scan.py::test_m4_correlates_m3_only_and_fills_policies、tests/lab/test_policies_readonly.py | 已涵蓋 |
| MS4 第 2 點：合併讀取 | probe/read.py、probe/run.py | tests/probe/test_read_merge.py、holdout | 已涵蓋；稽核 P1「limit」不成立（ADR-047） |
| MS4 第 3 點：L04 展示 | report/*、tests/e2e/test_demo_l04.py | 同左 | 已涵蓋 |
| MS3 第 1 點：L03、讀取植入、WriteRefused | probe/{escalation,seed_pass,run}.py | tests/probe/test_{escalation,seed_pass,write_refused,failure_paths}.py、tests/lab/test_l03_escalation_lab.py | 稽核 P1（例外時清理／還原）→ T-233／T-234 |
| ADR-036 #7：M1 不經 correlate | pipeline.py（順序）、correlate.py（排除 KEY_RULES） | test_run_scan.py::test_m4_correlates_m3_only_and_fills_policies、test_run_scan_errors.py::test_key_findings_are_never_correlated | 已涵蓋（雙重把關） |

稽核發現的處理：ADR-047。auditor 第一次派工因 30 回合上限未交報告，改為兩個範圍較小的部分重派。
