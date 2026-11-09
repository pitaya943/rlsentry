# MS0 高風險 ticket 審查說明（ADR-005）

每張 ticket 推送了兩個分支：`review/T-xxx`（ticket 的 commit）與 `review/T-xxx-base`（它的 parent）。
在 GitHub 以下列 compare 連結開 PR（base = `-base`），diff 只會含該 ticket，且永遠不需合併。
本 session 沒有建立 PR 的工具權限，所以由人類點連結開 PR，內容可直接貼本節。

## T-012 計分規則與 ground truth 格式（類別 4）
- 連結：https://github.com/pitaya943/rlsentry/compare/review/T-012-base...review/T-012
- 逐段說明：
  - `rlsentry/contracts/ground_truth.py:9-26`：計分定義（TP／FP／FN／TN、inconclusive、profile）。重點：FP 包含 ground truth 沒預料到的 confirmed finding。
  - `:47-50`：key 案例以標籤比對，避免把 anon key 誤判為 secret 卻被算 TP。
  - `:128-145`：單一 case 的形狀檢查（寫入案例不可列 audit）。
  - `:172-230`：整份檔案的結構檢查；`:209-211` 禁止同一格同時是漏洞與 safe。
- 驗證：`python3 -m pytest -q tests/ground_truth/test_gt_format.py` → 全部通過；把任一 expected.yaml 的 safe case 角色改成與漏洞案例相同 → 該檔驗證失敗並列出 `cells both vulnerable and safe/inconclusive`。

## T-015–T-020 Ground truth（類別 5）
| ticket | 連結 |
| --- | --- |
| T-015 L01–L03 | https://github.com/pitaya943/rlsentry/compare/review/T-015-base...review/T-015 |
| T-016 L04–L06 | https://github.com/pitaya943/rlsentry/compare/review/T-016-base...review/T-016 |
| T-017 L07–L09 | https://github.com/pitaya943/rlsentry/compare/review/T-017-base...review/T-017 |
| T-018 L10–L12 | https://github.com/pitaya943/rlsentry/compare/review/T-018-base...review/T-018 |
| T-019 C01–C02 | https://github.com/pitaya943/rlsentry/compare/review/T-019-base...review/T-019 |
| T-020 C03–C04 | https://github.com/pitaya943/rlsentry/compare/review/T-020-base...review/T-020 |

- 每個檔案的閱讀順序：`plant`（要植入什麼）→ `policy`（應有的權限）→ `vulnerable_cases`（policy 禁止、但 plant 讓它成立）→ `safe_cases`／`inconclusive_cases`。
- 值得特別看的地方：
  - `lab/L04_cross_tenant_read/expected.yaml` 開頭註解：偏離 SPEC §8 範例（ADR-011）。
  - `lab/L01_rls_disabled/expected.yaml`：12 格全是漏洞；anon 讀取為 critical 因為有 email 欄位。
  - `lab/L07_security_definer_rpc/expected.yaml`：ping_definer 只能是 inconclusive＋config warning。
  - `lab/L12_openapi_restricted/expected.yaml`：audit_log 沒人看得到 → 只能 inconclusive。
  - `lab/C03_empty_table/expected.yaml`、`lab/C04_user_without_data/expected.yaml`：inconclusive 對照組。
- 驗證：`python3 -m pytest -q tests/ground_truth` → 全部通過（T-024 的一致性測試以實作好的 policy 函式逐案檢查）。

## T-021 resolve_expected、T-022 row_permitted（類別 4）
- 連結：https://github.com/pitaya943/rlsentry/compare/review/T-021-base...review/T-021 、
  https://github.com/pitaya943/rlsentry/compare/review/T-022-base...review/T-022
- 逐段說明：
  - `rlsentry/policy/resolve.py:24-34`：角色鍵、已列出表用表內設定、未列出表依候選欄位推斷。
  - `:35-39`：anon 簡化（own_rows_only ≡ deny）。
  - `:40-44`：缺擁有者／公開欄位 → Review，不判為漏洞。
  - `rlsentry/policy/visibility.py:14`：None 永遠不算擁有（anon 不擁有無主的列）。
- 驗證：`python3 -m pytest -q tests/policy` → 全部通過。

## T-029、T-030 稽核後的 ground truth 修正（類別 5）
- 連結：https://github.com/pitaya943/rlsentry/compare/review/T-029-base...review/T-029 、
  https://github.com/pitaya943/rlsentry/compare/review/T-030-base...review/T-030
- 逐段說明：
  - `lab/L05_cross_tenant_write/expected.yaml` 的 plant：新增 `created_by`，SELECT 允許建立者讀取。原因：UPDATE 帶 WHERE 時 Postgres 會對新列套用 SELECT policy，原寫法下轉移會以 42501 失敗、漏洞不存在（auditor G1）。
  - `lab/L07_security_definer_rpc/expected.yaml`：兩個函式宣告 STABLE（GET／HEAD 才能呼叫）；`get_all_accounts` 在 policy 中列出 `primary_key`。
  - `lab/L09_insert_permissive/expected.yaml`、`lab/L01_rls_disabled/expected.yaml`：anon 新增時偽造 owner 為 user_a（`new_owner: user_a`），由 user_a 讀回；INSERT 用 `return=minimal`。
  - `lab/L11_public_bucket/expected.yaml`：物件以 SQL 設定 `owner_id`；`lab/L12_openapi_restricted/expected.yaml`：關閉 OpenAPI 的實際 SQL 與 `primary_key`。
- 驗證：`python3 -m pytest -q tests/ground_truth` → 全部通過。真實 Postgres 上的行為在 MS1 由 lab 驗證測試確認（驗證清單第 3 段）。

## Milestone PR（session 分支 → main）
- 連結：https://github.com/pitaya943/rlsentry/compare/main...claude/busy-darwin-asvox3
- 說明可直接使用 `docs/verification/MS0-v1.md` 第 1、4、5、6 節。
