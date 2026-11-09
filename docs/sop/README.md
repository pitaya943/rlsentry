# 收尾 SOP：`/final-question` 與 `/approved`（草稿，待你安裝）

## 為什麼需要
- `progress.html` 原本只在「milestone 收尾、高風險驗收後、暫停前」重跑（ADR-015、031），**沒有「你核准之後」這個時間點**，所以核准狀態要等到下一個 milestone 收尾才會出現。
- 核准意見每次由你手寫，格式不一。

## 流程
1. agent 交付清單後，你在雲端 session 輸入 **`/final-question`**。agent 會列出所有待你決定的事，每項附來源、選項與建議；沒有就回「沒有待決事項。」
2. 你逐題回答。agent 產生一段標準格式的核准意見，可直接貼到 `host/approve.py` 的「Notes」提示，並附上簽章指令。
3. 你照常驗證，在本機簽章（`host/approve.py`）。
4. 你在雲端 session 輸入 **`/approved MS6`**。agent 依序檢查 approvals 分支：
   - `decision: approve`；
   - `.sig` 存在；
   - 清單的 sha256 與核准紀錄一致；
   - harness 狀態不再是等待審查。

   全部通過後，agent 重跑 `progress.py`，把 `system_overview.html` 的該列改為已核准，只提交這三個檔並 push。任一項不符就只回報、不修改。
5. 開新 session 輸入「繼續」，開始下一個 milestone（這一步不變）。

## 安裝步驟
在你本機的 Git Bash 或終端機執行。`.claude/` 是凍結路徑，agent 不能寫入，所以由你安裝。

前提：
- 本機 repo 沒有未提交的修改；
- 已執行過 `bash host/bootstrap.sh`。

1. 同步 session 分支：
```bash
git fetch origin && git switch claude/busy-darwin-asvox3 && git pull --ff-only origin claude/busy-darwin-asvox3
```
2. 建立兩個 skill 目錄：
```bash
mkdir -p .claude/skills/final-question .claude/skills/approved
```
3. 複製 skill 檔：
```bash
cp docs/sop/final-question/SKILL.md .claude/skills/final-question/SKILL.md && cp docs/sop/approved/SKILL.md .claude/skills/approved/SKILL.md
```
4. 確認工作樹只多了這兩個檔（預期只列出兩行 `?? .claude/skills/...`，或一行 `?? .claude/skills/`）：
```bash
git status --short
```
5. 重新凍結。這一步會依序：跑 harness 自我測試、commit（`harness: refreeze`）、push 到目前分支，最後把本機的 `harness-frozen` tag 移到新 commit（tag 只留在本機，不會 push）：
```bash
bash host/bootstrap.sh --refreeze
```
6. 確認凍結比對乾淨（預期沒有輸出）：
```bash
git diff --stat harness-frozen HEAD -- harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud .gitattributes
```

## 注意
- 第 5 步會執行 `git add -A`，所以第 4 步一定要確認工作樹只有這兩個新檔。
- **時機**：建議在**簽 MS6 之前**安裝，這樣簽完就能直接用 `/approved MS6`。
  - 安裝的 commit 不改任何程式。MS6 清單的 sha 比對指令只比對 `rlsentry tests lab action pyproject.toml`，不受影響。
  - GitHub Actions 的 verify-milestone 請在安裝**之後**再跑（ref 仍是 `claude/busy-darwin-asvox3`），這樣 Actions 驗的 sha 就包含安裝 commit，與你本機一致。
- 雲端 session 要**重新開**才會載入新的 skill，因為 skill 是在 session 啟動時讀取的。
- 安裝後請告訴我。我會寫 ADR-048，並在同一個 commit 更新 `docs/verification_steps.html` 步驟 8（ADR-028）。
