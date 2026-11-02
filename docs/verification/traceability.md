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
