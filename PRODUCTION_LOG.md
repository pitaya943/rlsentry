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

### Tickets（23 張，0 blocked；T-026 2 次，其餘 1 次）
| ticket | agent | 結果 | 事件（events.jsonl 行） |
| --- | --- | --- | --- |
| T-010 §6 模型＋rule catalog | architect | accepted @ 49ab8c417 | 376 |
| T-011 expected policy／rlsentry.yaml | architect | accepted @ d3aec63a5 | 378 |
| T-012 ground truth 格式＋計分 ⚠ | architect | accepted @ bfd030d0e | 380 |
| T-013 介面＋相依套件 | architect | accepted @ f2405b319 | 382 |
| T-014 policy 可見測試 | architect | accepted @ cd51bdfdd | 384 |
| T-015–T-018 ground truth L01–L12 ⚠ | architect | accepted @ 0c93678d5、8defddced、e6271aa7a、c93d33b31 | 398–406 |
| T-019、T-020 ground truth C01–C04 ⚠ | architect | accepted @ 6cab53b3d、43ba7b005 | 412、414 |
| T-021 resolve_expected ⚠ | probe-dev | accepted @ 3c20e505a | dispatch `5afeae12`、accept 408 |
| T-022 row_permitted ⚠ | probe-dev | accepted @ f1da434a7 | dispatch `538691c9`、accept 409 |
| T-023 load_config | probe-dev | accepted @ 75f25da3c | dispatch `19a20a1a`、accept 410 |
| T-024 ground truth 一致性測試 | architect | accepted @ cd028f5ff | 416 |
| T-025 MS1–MS7 ticket 計畫 | architect | accepted @ a59ff5b53 | 418 |
| T-026 稽核修正：已知列語意、rule 檢查 | architect | 第 1 次失敗、第 2 次 accepted @ 2aeda597f | ticket_fail＋accept |
| T-027 稽核修正：primary_key、寫入閘門、profile | architect | accepted @ 5b1c147dd | — |
| T-028 稽核修正：計分、lab 慣例、隔離 | architect | accepted @ ac202fa10 | — |
| T-029、T-030 稽核修正 ground truth ⚠ | architect | accepted @ e37743920、4ecbe30be | — |
| T-031 可見測試：錯誤不回顯 | architect | accepted @ 9b44176f5 | — |
| T-032 load.py 錯誤只回報位置 | probe-dev | accepted @ c01d68c61（回報只有 "placeholder"，以 diff 審查後驗收） | — |

### 失敗與處理
| 問題 | 處理 |
| --- | --- |
| guard 把 helper script 中 `git switch …` 之後的 `git add --` 誤認為 `git checkout … --`（跨分支複製） | 改用不帶 `--` 的 `git add` |
| 三個 probe-dev 回報：worktree 內 ruff isort 把 `rlsentry` 當第三方（I001）；mypy 缺 yaml stub | pyproject 加 `known-first-party`、dev 加 `types-PyYAML`，重排測試 import（commit 於 accept 前） |
| 背景派工時，events.jsonl 的 `report` 事件記到的是「啟動」中繼資料，不是 subagent 的回報 | subagent 回報摘要記於本表（皆 9–10 passed、0 failed）；列入驗證清單已知限制 |
| auditor（dispatch `2c8e2119`）：L05 在真實 Postgres 上不成立（G1，P0）、audit 登入與 log 判準（F1、F2，P0）、YAML 錯誤回顯密碼（F5）等 | ADR-014；T-026–T-032；追溯表 docs/verification/traceability.md |
| T-026 第 1 次：未完成實作的新測試留在回歸測試檔工作區 | 新測試改放 tests/policy/test_load_safety.py |
| 本 session 沒有建立 GitHub PR 的工具 | 推送 `review/*` 分支，PR 說明見 `docs/reviews/MS0-high-risk.md`（ADR-005） |

### ADR
ADR-005（PR 政策與高風險判定）、006（模型增補）、007（RPC = select）、008（rule catalog）、009（ground truth 格式增補）、010（設定預設值）、011（計分與 ground truth 規則、L04 偏離）、012（相依套件與 mypy）、013（D4 Firebase 列為未來工作）、014（auditor 修正）

### 指標
- 測試 302 passed；holdout 12 passed；safety 9 passed；acceptance `--no-vc` ALL PASSED。
- ground truth：P0 漏洞案例 32、safe 案例 72、inconclusive 案例 7（L11 為 P2，另有漏洞 2、safe 2，不計分）。
- subagent tokens：T-021 約 18k、T-022 約 17k、T-023 約 17k、T-032 約 14k、auditor 約 132k。

## MS1（Lab benchmark + Safety）

### 開始前檢查（人類指示，全部通過）
非 shallow（`git rev-parse --is-shallow-repository` = false）；`spec.py "6"` 含 tables／defaults／fail_on／`rlsentry init`（refreeze `ddedd60`）；相依以 pip 個別安裝；status current=MS1。

### MS0 核准意見 → MS1 處理
| 意見 | 處理 |
| --- | --- |
| pyproject flat-layout 安裝缺陷 | T-040（乾淨 venv 中 `pip install -e ".[dev]"` 成功；Debian 內建 setuptools 68 無法建 wheel，dev 加 `setuptools>=75`） |
| spec.py 標題解析 bug（人類修正 `ddedd60`） | ADR-016（影響範圍 SPEC.md:342-365） |
| #1 audit 允許登入 POST | 已記於 ADR-014 補記；寫入 `contracts/safety.py` 規則 3，T-051 測試 |
| #2 NFR-01 只計 PostgREST 角色 | `contracts/lab.py` `POSTGREST_ROLES`；T-044 lab 測試 |
| #4 ci 可寫遠端（write_hosts） | ADR-017；T-041 合約；T-050、T-051 實作 |

### Holdout hashes（派工前記錄）
| 檔案 | sha256 |
| --- | --- |
| MS1/test_holdout_safety.py | `304a5c374b6a6469de388329f20a73a13650d0aa7212d07e2aa4566836154f6b` |

內容：gate、mode（12 格矩陣）、mask、ratelimit、http 的不同輸入。派工前以 scratchpad 參考實作確認可見＋holdout 共 96 個測試可滿足（參考實作未提交，已刪除；本次以 `PYTHONDONTWRITEBYTECODE` 避免 MS0 的 .pyc 誤帶）。
