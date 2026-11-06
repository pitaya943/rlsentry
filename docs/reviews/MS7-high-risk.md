# MS7 高風險 ticket 審查說明（ADR-005 補記：分級＋合併）

本 milestone 以 worktree accept 合併。要看單張 diff：`git show <sha>`，或 `https://github.com/pitaya943/rlsentry/compare/<sha>~1...<sha>`（`<sha>` 換成下表的 accept commit）。

## 清單與預估閱讀時間（約 25 分鐘）
**逐張審查**（第 1 類寫入、第 2 類判定）：
- T-243 `probe/metadata.py`、`probe/escalation.py`（提權前以 GET 讀出 `user_metadata.role`；讀不到或已是 admin 就不寫入；還原為原值；原值不進 note／finding），約 8 分鐘 — 7854ace
- T-241 `whitebox/correlate.py`（改標 SECURITY_DEFINER_RPC_DATA 時嚴重度取較高者；`keep_higher=None` 於呼叫時讀合約常數），約 4 分鐘 — dc06714
- T-245 合約常數切換為 True、L07-V1 改為 high、既有測試與新 e2e（architect），約 5 分鐘 — 8a6c633

**建議抽查**：
- T-242 `report/fix_sql.py`（DROP POLICY 依 roles、policy 名稱 63 bytes）42ee957
- T-244 `lab/_shared/__main__.py`（lab 命令列入口，只綁 127.0.0.1；測試基礎設施）53c19b1
- 合約、測試與 ADR：T-240 ab0ff50；文件：T-246 23ca9e7、T-247 7b857e2

## 重點
- **嚴重度不會因提供 DB 連線而下降**（MS6 核准意見第 1 點，ADR-049）：單元測試涵蓋 Critical／High／Medium 與三種 fail_on；e2e 在 lab 以 L07 比對有無 M4 的 ci exit code（皆為 1）。
- **分段上線**：每一次合併的回歸測試都是綠的（T-240 常數 False → T-241 實作 → T-245 切換常數與 ground truth）。
- **第 5 類（ground truth）變更**：只有 L07-V1 的 severity（medium → high）。
