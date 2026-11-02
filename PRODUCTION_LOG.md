# RLSentry 生產紀錄

事件編號格式：`events.jsonl#L<行號>`。沒有 id 的事件用行號引用；有 id 的事件同時附上 id。

## STAGE0：護欄測試（玩具 ticket）

### 時間線（2026-11-02，UTC）
- 11:29：Session 開始。雲端 setup script 結束碼為 1，原因是 Docker daemon 未啟動，`cloud/setup.sh` 最後一行的 `&&` 鏈因此失敗。
  pytest、ruff、mypy、supabase 2.122.0 都已經安裝好。
- 11:31：`make harness-test` → 23 passed。
- 11:31:43：`start T-000`（attempt 1，#L1）。
- 11:31:51：第一次派工 recon-dev（#L2，dispatch `c5ea280b`）。Canary 1、2a、2b 被擋下（#L4–L6），**canary 3 沒有被擋**。
  回報 `CANARY FAILED`（#L8，report `c87e54fc`）。
- 11:32:38：architect 手動把同一個 payload 交給 `guard_paths.py` 重現（#L9 是這次手動測試寫入的，不是 subagent 觸發）。
  找到根因：全域 hook 不涵蓋 Read/Grep/Glob，frontmatter hook 沒有觸發，`_is_holdout` 也不認得 worktree 內的副本。
- 11:33:01：第二次派工（#L10，dispatch `d24fa12b`），只做診斷讀取與實作。4 種讀取寫法全部沒擋。commit `b6a45e9`（#L13，report `d35d9c5c`）。
- 11:33:29：`accept` 失敗（#L14），原因是凍結的 harness/host 讓 `ruff check .` 報了 105 個錯誤。
- 11:34：ADR-002，commit `6ec9124`（pyproject 排除凍結路徑）。
- 11:34:11–12：`start T-000`（attempt 2，#L15）→ accepted at `a594b0b96`（#L16）。
- 11:34:22：`acceptance.py --milestone STAGE0 --no-vc` → ALL PASSED（#L17）。
- 11:34–11:35：手動啟動 `dockerd`。Docker 29.9.2 可以運作，`public.ecr.aws` 可以拉取。

### Tickets
| Ticket | Agent | Attempts | 結果 | 說明 |
|---|---|---|---|---|
| T-000 | recon-dev | 2 | done（`a594b0b96`） | attempt 1 的 accept 是因為 lint 設定失敗，不是程式本身有錯；canary 3 失敗 |

### 失敗與修正
1. **Canary 3（holdout 讀取）沒被擋**：這是 harness 的缺陷。architect 不能修改 harness，所以只記錄並建議修法
   （見 `docs/verification/STAGE0-v1.md` 第 4 段），並建議人工審查者**不要核准** STAGE0。
2. **`make check` 的 ruff 檢查凍結檔**：用 ADR-002 在 `pyproject.toml` 排除 `harness`、`host`、`.claude`。

### ADR
- ADR-002：ruff 不檢查凍結的 harness/host 與 subagent worktree。

### Holdout 雜湊
- 本階段沒有 holdout 檔。

### 指標
- tickets：1 完成、0 blocked；平均 attempt 2.0；派工 2 次；guard_block 3 次來自 subagent，1 次來自 architect 手動重現。
