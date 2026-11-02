# RLSentry 自主開發護欄（harness）· 雲端版（claude.ai/code）

產品由 architect 與 subagent 依 `docs/SPEC.md` 在 Claude Code 雲端 session 中自主開發。
你是唯一的人工審查者：每個 milestone 結束時，流程暫停，等你核准後才繼續。

## 信任模型：為什麼雲端也可以

雲端 VM 是 repo 的 clone，沒有唯讀掛載，所以 harness 檔在技術上可以被代理修改。
設計因此從「防止」改成「**偵測 + 只有你能簽核准**」：

| 機制 | 由誰保證 |
| --- | --- |
| 核准必須有你的 SSH 簽章（`ssh-keygen -Y`） | 私鑰只在你的電腦上；代理無法偽造 |
| 你在核准前執行 `git diff harness-frozen -- …` | 標籤在你的本機 repo；任何對護欄的修改都會被看到 |
| 驗收紀錄存在 git 歷史（`RLSentry-Accepted` trailer） | VM 被回收也不會遺失 |
| `make verify-milestone` 從 git 歷史重算範圍、作弊、測試 | 偽造 trailer 或繞過閘門的 commit 會被列出 |
| hook（路徑守衛、派工閘門、Stop hook） | 擋住大多數意外與越界；Bash 層是啟發式，不是保證 |

## 一次性準備（你的電腦）

**Windows 不需要 WSL。** 只要安裝：

1. Git for Windows（https://git-scm.com/download/win）：附帶 Git Bash、`git`、`ssh-keygen`。
2. Python 3.10 以上（https://www.python.org/downloads/）：安裝時勾選「Add python.exe to PATH」。
3. 在 VS Code 按 `Ctrl+Shift+P` →「Terminal: Select Default Profile」→ 選 **Git Bash**，之後新開的終端機就能直接執行下面的腳本。

GitHub CLI（`gh`）是選用的；沒有它就先在 GitHub 網頁建立私有空 repo，再用 `--remote` 指定網址。
Windows 上 bootstrap 會跳過 harness 自我測試（測試假設 POSIX shell），改由雲端在 Stage 0 第一步執行。

```bash
bash host/bootstrap.sh            # 或 --remote git@github.com:<you>/rlsentry.git
```

腳本會依序：檢查工具 → 確認 SPEC → 確認簽章金鑰 → 寫入 `harness/allowed_signers` → 跑 harness 測試 →
commit → 建立 GitHub repo 並推送 → 在本機打上 `harness-frozen` 標籤（不推送）。可重複執行，已完成的步驟會跳過。

**簽章金鑰只能由你建立，而且必須有密碼。** 腳本偵測到沒有金鑰或金鑰沒有密碼時，會停下來印出指令請你自己執行。
不要把它加進 ssh-agent：每次簽章都輸入密碼，正是讓任何代理（包括本機的 Claude Code）無法替你核准的原因。

想讓本機 Claude Code 代勞，請看 `host/LOCAL_CLAUDE_CODE.md`：**在 VS Code 開上一層資料夾**，不要直接開這個 repo。

## 雲端環境設定（claude.ai/code）

1. 連結 GitHub，選這個 repo。
2. 建立一個 cloud environment：
   - **Setup script**：貼上 `cloud/setup.sh` 的內容。
   - **Network**：先用 Trusted。若 Stage 0 時 Supabase 映像拉不下來，改用自訂白名單並加入 `public.ecr.aws`。
3. 不要在 environment 放任何真實秘密；lab 只用本機一次性的 Supabase 專案。

## Stage 0：護欄測試（必做）

在 claude.ai/code 開一個 session，選這個 repo 與 environment，送出：

> Stage 0：先執行 `make harness-test`，再只執行 STAGE0 milestone，完成後產出驗證清單並暫停。

`.claude/settings.json` 設有 `"agent": "architect"`，讓主 session 以 architect 身分執行。
如果你的版本不支援這個設定，改在開頭加一句「請完全依照 .claude/agents/architect.md 行事」；
派工閘門仍會擋下非指定的 subagent。

Stage 0 結束後，在你的電腦上：

```bash
git fetch && git switch <session 的分支> && git pull
git diff --stat harness-frozen -- harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud .gitattributes   # 必須為空
```

然後逐項確認：

- [ ] `make verify-milestone MS=STAGE0` 最後一行為 `ALL PASSED`（見下方「在哪裡跑驗證」）
- [ ] `logs/events.jsonl` 有 `dispatch`、`report`，`ticket` 欄位是 `T-000`
- [ ] `logs/raw-hook-samples/` 的欄位名稱與 harness 預期相同（`tool_input.subagent_type`、`tool_input.prompt`、`tool_response`）
- [ ] 四個 canary 全被擋下，`events.jsonl` 有對應的 `guard_block`
- [ ] subagent 回報的 worktree 路徑不是主 checkout
- [ ] `events.jsonl` 有 `stop_allowed`，`reason` 為 `awaiting_human`，且狀態已推送到 GitHub
- [ ] `docs/verification/STAGE0-v1.md` 符合範本

任何一項不符就**不要核准**：在本機修正 harness，commit，`git tag -f harness-frozen`，推送後重開 session。

## 每個 milestone 的核准流程

```bash
bash host/review.sh MS3 <session 的分支>
```

腳本會：同步分支 → 比對 `harness-frozen`（有差異就拒絕繼續）→ 執行或指引獨立驗證 → 列出清單 →
最後由你輸入決定、意見與金鑰密碼，簽章並推送到 `rlsentry-approvals` 分支。完成後回到雲端 session 送出「繼續」。

### 在哪裡跑驗證

`verify-milestone` 必須在**代理碰不到的環境**跑，二選一：

- **你的電腦**：需要 Python 3.12、Docker、Supabase CLI（與 `cloud/setup.sh` 相同的工具）。
- **一個全新的雲端 session**：先在本機確認 `git diff harness-frozen` 為空，再開一個新 session，只送出
  「只執行 `make verify-milestone MS=MS3`，不要修改任何檔案，回報完整輸出」。新 VM 從已檢查過的 commit clone，
  不受原本 architect session 影響。

## 執行中觀察

- 雲端 session 畫面：即時看到 architect 與 subagent 的工作
- `CHECKLIST.md`：自動產生的進度清單（每次驗收與暫停都會推送）
- `logs/events.jsonl`：派工、回報、阻擋、驗收、停止；長文字在 `logs/messages/`
- `logs/INCOMPLETE.md`：停止預算（30 次）耗盡時才會出現

## 雲端特有的注意事項

- **VM 會在閒置後被回收**：harness 在每次驗收與暫停時都會 commit 並推送狀態；未推送的工作會遺失。
- **用量**：雲端 session 與你其他的 Claude 用量共用額度，並行 subagent 越多消耗越快。
- **holdout 測試**放在 repo 的 `.holdout/`，subagent 讀取只靠 hook 阻擋（較弱）；你的獨立驗證才是保證。

## 尚未驗證的假設（Stage 0 要確認）

1. hook 輸入的欄位名稱；subagent 的工具呼叫是否帶 `agent_type`
2. `isolation: worktree` 在雲端的行為，以及 subagent 分支能被主 checkout 看到
3. settings 的 `"agent": "architect"` 是否生效
4. 雲端 Docker 可以啟動 Supabase lab，且映像能在網路白名單下拉取
5. `git push` 在雲端 session 中可以推送到工作分支
