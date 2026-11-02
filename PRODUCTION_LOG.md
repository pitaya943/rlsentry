# RLSentry 生產紀錄

## STAGE0（護欄測試）

### Holdout hashes（派工前記錄）
| 檔案 | sha256 |
| --- | --- |
| STAGE0/test_holdout.py | `98a15db50f7b081b71fa6626f418383b6ba4a545a2f4a9185d80f3d75e63b5e1` |

內容：`add(0, 0) == 0` 與交換律（3 組不同輸入）。

### Tickets
| ticket | agent | 嘗試 | 結果 | 事件 |
| --- | --- | --- | --- | --- |
| T-000 | recon-dev | 1 | accepted @ 027424ccb | dispatch `80b1eec5`、report `97cdbc86` |
| T-001 | recon-dev | 1 | accepted @ 3a3c6110e（canary 仍未跑） | dispatch `2060c40c`、report `6f773391` |

### 失敗與處理
| 問題 | 處理 |
| --- | --- |
| subagent 拒絕執行 canary 1–5 | 重新派工附加確認被 classifier（Self-Approval）拒絕；記錄於 ADR-003，交由人類決定 |
| 拒絕的派工仍被記為 dispatch `cb492439` | 列入驗證清單已知限制 |
| 人類授權後 subagent 仍拒絕（只見轉述） | ADR-004；改由人類選擇親手執行或授權 architect |
| Bash guard 誤判 2 次（events 第 11、18 行） | 改用 Write 工具寫 ticket |

### ADR
- ADR-003：canary 1–5 未執行仍驗收 add()
- ADR-004：人類授權無法傳到 subagent
- 驗證清單：STAGE0-v2

### 指標
- harness-test 29 passed；acceptance ALL PASSED（tests 1、holdout 2）；subagent tokens 約 14k

## MS0（基礎：合約、expected policy 格式、ground truth）

### Holdout hashes（派工前記錄）
| 檔案 | sha256 |
| --- | --- |
| MS0/test_holdout_policy.py | `d347875d5857eb9fb02883ad466f936f574a6a566c67407366c5a8e02b7eb0ba` |
| MS0/__pycache__/test_holdout_policy.cpython-313-pytest-9.2.0.pyc | `bfb8d974ce37b7e805cb2ff06b09a4fb535a9f530b79dd19b347928ae7628409`（誤帶入的位元組碼，pytest 不會收集；來自 architect 以 scratchpad 參考實作確認測試可滿足） |

內容：resolve_expected、row_permitted、load_config 的不同輸入（部分 op／role 覆寫、未列出表的欄位推斷順序、anon 簡化、錯誤鍵路徑）。
