# MS1 高風險 ticket 審查說明（ADR-005）

做法同 MS0：`review/T-xxx` 指向 `review/T-xxx-base` 開 PR，diff 只含該 ticket，不需合併。

## T-050–T-054 Safety 層（類別 1；T-051、T-054 另屬類別 2，T-052 屬類別 3）
| ticket | 檔案 | 連結 |
| --- | --- | --- |
| T-050 授權閘門 | `rlsentry/safety/gate.py` | https://github.com/pitaya943/rlsentry/compare/review/T-050-base...review/T-050 |
| T-051 寫入閘門 | `rlsentry/safety/mode.py` | https://github.com/pitaya943/rlsentry/compare/review/T-051-base...review/T-051 |
| T-052 遮罩 | `rlsentry/safety/mask.py` | https://github.com/pitaya943/rlsentry/compare/review/T-052-base...review/T-052 |
| T-053 限速 | `rlsentry/safety/ratelimit.py` | https://github.com/pitaya943/rlsentry/compare/review/T-053-base...review/T-053 |
| T-054 HTTP client | `rlsentry/safety/http.py` | https://github.com/pitaya943/rlsentry/compare/review/T-054-base...review/T-054 |

逐段重點：
- `mode.py` 規則順序：URL 檢查 → GET／HEAD → RPC 一律拒絕 → 登入完全比對 → audit 拒絕 → localhost → ci `write_hosts`。順序本身就是安全性質：RPC 檢查在登入例外與 profile 之前，所以任何 profile 都不會 POST RPC。
- `mode.py` `_host_listed`：無埠號項目比對任意埠；`host:port` 項目只在 URL 明寫該埠時相符。
- `http.py` `request`：寫入閘門看的是含 params 的最終 URL，且在限速之前；`follow_redirects=False`。
- `gate.py`：`confirmed_by` 以去除空白後的值記錄（subagent 回報的唯一模糊處，architect 同意）。

驗證：`python3 -m pytest -q -m safety tests/safety` → 全部通過；holdout 見 PRODUCTION_LOG。
