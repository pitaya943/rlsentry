# 給本機 Claude Code 的指示（貼給它即可）

Windows 使用者：先把 VS Code 的預設終端機設為 **Git Bash**（`Ctrl+Shift+P` →「Terminal: Select Default Profile」）。不需要 WSL。

在 VS Code 開啟**上一層資料夾**（例如 `~/work/`，裡面有 `rlsentry/`），不要直接開 `rlsentry/`。
否則本機 Claude Code 會載入專案的 hook，變成 architect，Stop hook 也會讓它停不下來。

## 第一次設定：貼給 Claude Code

```text
請幫我完成 RLSentry 的本機設定：
1. 執行 `bash rlsentry/host/bootstrap.sh`（若我給你 GitHub 網址，加上 `--remote <網址>`）。
2. 如果腳本停在「HUMAN STEP」，把那行指令原樣告訴我，等我自己在終端機執行完再重跑腳本。
   不要替我產生簽章金鑰，也不要移除金鑰的密碼。
3. 腳本完成後，把最後印出的瀏覽器步驟整理給我。
不要修改 rlsentry/harness、rlsentry/.claude、rlsentry/host、rlsentry/docs/SPEC.md 底下的任何檔案。
```

## 每個 milestone 審查：貼給 Claude Code

```text
雲端 session 已在 <MS> 暫停，分支是 <branch>。請執行 `bash rlsentry/host/review.sh <MS> <branch>`，
然後：
1. 如果第 2 步報告 frozen files changed，立刻停下並把 diff 給我看，不要做任何修改。
2. 如果第 3 步說本機無法驗證，把它印出的「新雲端 session」指示給我。
3. 打開驗證清單，逐項說明第 3 段每一項要我做什麼、預期看到什麼；能在本機執行的指令先替我跑並回報結果。
4. 最後的簽章步驟由我自己執行，你只要把指令告訴我。
```

## 修改規格或護欄後重新凍結

只有你自己可以決定修改凍結檔。改完後執行：

```bash
bash rlsentry/host/bootstrap.sh --refreeze
```

它會重跑 harness 測試、commit、推送，並把本機的 `harness-frozen` 標籤移到新的 commit。
