# MS2 高風險 ticket 審查說明（ADR-005 補記：分級＋合併）

連結格式：`https://github.com/pitaya943/rlsentry/compare/<base>...<branch>`。這些 PR 只供審查，不需合併。

## 清單與預估閱讀時間（約 50 分鐘）
**逐張審查**（第 1、2 類）：
- T-092：labctl 寫入路徑，約 5 分鐘
- T-113：寫入分類，NFR-01 的驗證工具，約 10 分鐘
- T-103：送出登入 POST、處理密碼與 JWT，約 8 分鐘

**建議抽查**：
- 第 3、4 類合併為一個分支 `review/MS2-probe`（T-104–T-109），約 20 分鐘
- 第 6 類：T-090 修改既有合約，約 7 分鐘

MS2 沒有第 5 類（ground truth 或植入漏洞）的變更。

## 逐張審查
| ticket | 檔案 | 連結 |
| --- | --- | --- |
| T-092 execute、唯讀 query | `lab/_shared/labctl.py` | https://github.com/pitaya943/rlsentry/compare/review/T-092-base...review/T-092 |
| T-113 write_command、flush sentinel | `lab/_shared/labctl.py` | https://github.com/pitaya943/rlsentry/compare/review/T-113-base...review/T-113 |
| T-103 登入 | `rlsentry/probe/session.py` | https://github.com/pitaya943/rlsentry/compare/review/T-103-base...review/T-103 |

重點：
- **`labctl.query`**：以 `PGOPTIONS=-c default_transaction_read_only=on` 執行。這只防誤寫：一個明確執行 `SET … off` 的語句仍能寫入（合約已註明）。
- **`labctl.execute`**：`psql -1 -f -`。psql 的 `-1` 只在搭配 `-f` 或 `-c` 時有效，所以讀 stdin 時要加 `-f -`（lab-dev 回報）。
- **`write_command`**：單次掃描 `SQL_QUOTED_RE`，取代方式如下，之後才比對寫入關鍵字：
  - 單引號常值換成 `''`
  - 雙引號識別字換成 `"x"`
  - `$$` 字串換成 `''`
- **`db_writes_since`**：先送出 `RAISE LOG` sentinel，等它出現在 log 後才分類，而且只看 sentinel 之前的記錄。
- **`session.login`**：
  - 例外訊息只含狀態碼或例外類別名稱。
  - 只捕捉 `httpx.HTTPError`，所以 `WriteRefused` 仍會往外拋。
  - 路徑寫成字面值 `/auth/v1/token`，沒有引用 `LOGIN_PATH`；寫入閘門是完全比對，結果相同。

## 建議抽查（合併分支）
| 範圍 | 連結 |
| --- | --- |
| T-104–T-109 probe（evidence、cross_tenant、paths、read、verdict、severity、diff、run） | https://github.com/pitaya943/rlsentry/compare/review/MS2-probe-base...review/MS2-probe |
| T-090 合約（含 interfaces 簽名變更） | https://github.com/pitaya943/rlsentry/compare/review/T-090-base...review/T-090 |

建議抽查的位置：
- `rlsentry/probe/verdict.py` 的 `read_cell`：只有在狀態為 200 或 206、有總數、且總數不超過查詢數時才下判定。這段是「inconclusive 不會被寫成安全」的核心。
- `rlsentry/probe/run.py`：沒有 session 的角色記為 not_tested；寫入 cell 一律記為 not_tested。
- `rlsentry/probe/cross_tenant.py`：每位使用者只用自己的 token、只列出自己的列。
- `rlsentry/probe/evidence.py`：apikey 與 Authorization 先用 `mask`，整串再經過 `mask_text`。

## 驗證
- `python3 -m pytest -q -m safety tests/probe tests/lab/test_shared_classify.py`：應全部通過。
- `python3 -m pytest -q tests/lab/test_scan_reads.py`：15 passed（需 Docker）。
