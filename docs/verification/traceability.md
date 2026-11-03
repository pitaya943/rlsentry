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
