# MSx 驗證清單 v1（main @ <milestone 最後一個 accept commit 的前 9 碼>）

## 1. 本模組做了什麼
- 完成哪些 ticket（數量、平均嘗試次數、blocked 的有哪些與原因）
- 本模組新增的 ADR（編號與一句話）

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- tests、holdout、safety、mutation、provenance 的結果摘要

## 3. 請你親手驗證（逐項打勾，含第一項最多 16 項）
- [ ] 在你自己的機器（或一個全新的雲端 session）執行
      `git diff --stat harness-frozen -- harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud`
      然後 `make verify-milestone MS=MSx`
      預期：diff 為空；最後一行為 ALL PASSED
- [ ] （指令）
      預期：（具體可觀察的結果）
- [ ] 閱讀 `<檔案>` 第 a–b 行
      確認：（要確認的事）

## 4. 與 SPEC 的偏差與假設
- 

## 5. 已知限制
- 
