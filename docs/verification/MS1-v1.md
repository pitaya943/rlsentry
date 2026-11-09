# MS1 驗證清單 v1（main @ 7d99422ef）

## 1. 本模組做了什麼
- ticket：37 張（T-040–T-085），36 張 done、1 張 blocked。T-077、T-078 各用 2 次，其餘 1 次；平均 1.05 次。
  - **blocked**：T-071（L11）。被拒的原因是 labctl 沒有清掉 storage policy，不是情境本身有錯。L11 的情境檔改由 T-080 連同 labctl 修正一起交付。
  - architect：
    - T-040：pyproject package discovery（MS0 核准意見第 1 點）
    - T-041：safety／lab 合約、ci `write_hosts`
    - T-042–T-045：safety 可見測試、lab oracle 與 16 個情境測試
    - T-078、T-079、T-081、T-082：稽核與 lab 回報的修正
  - recon-dev：`rlsentry/safety/` 的 gate、mode、mask、ratelimit、http（T-050–T-054），以及稽核修正 T-083、T-084。
  - lab-dev：
    - 共用 lab（T-060）
    - 16 個情境（T-061–T-076；L11 由 T-080 交付）
    - labctl 修正 T-077、T-080、T-085
- ADR：
  - **016**：spec.py 的 code fence 缺陷，你修在 `ddedd60`；影響範圍是 SPEC.md:342-365。
  - **017**：ci 寫入遠端時用 `write_hosts`，host 必須完全比對。
  - **018**：lab 架構是一個常駐的本機 Supabase，逐情境載入，再由 oracle 驗證。
  - **019**：PostgREST 的寫入在 `log_statement=mod` 下看不到，改為 authenticator 記錄全部語句，再以寫入關鍵字分類。
  - **020**：safety 稽核的處理方式，其中「授權綁定」延到 MS6。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS1 --no-vc`：ALL PASSED。
  - 回歸測試：602 passed（含 lab 177）
  - holdout：17 passed（MS0＋MS1）
  - safety：90 passed
  - provenance、ruff、mypy 皆通過
  - mutation：略過
- lab 在冷啟動（`supabase stop` 後）重跑全部測試：177 passed。連跑兩次結果相同。
- auditor 分兩部分執行（第一次在 30 回合上限時中止、沒有報告）：
  - safety 部分：P1 ×1、P2 ×6
  - lab 部分：P1 ×5、P2 ×6
  - 處理方式見 ADR-019 補記、ADR-020，以及 `docs/verification/traceability.md` 的 MS1 段
- 你的 MS0 核准意見逐點對應到 ticket 或 ADR，見 PRODUCTION_LOG MS1 段。

## 3. 請你親手驗證（逐項打勾）
- [ ] 在容器內執行 `make verify-milestone MS=MS1`。執行前先在你的機器上跑 `git diff --stat harness-frozen -- harness .claude CLAUDE.md Makefile docs/SPEC.md host tests/toy cloud .gitattributes`。需要 Docker（CLAUDE.md 的啟動指令）。
      預期：diff 為空；最後一行為 `MS1: ALL PASSED`。第一次會拉 Supabase 映像，約 1–3 分鐘。
- [ ] `(cd lab/_shared && supabase stop --no-backup); python3 -m pytest -q tests/lab`
      預期：`177 passed`。這是從冷啟動開始的測試，可確認 lab 不依賴先前留下的狀態。
- [ ] 把 `lab/C04_user_without_data/migration.sql:10` 的 `USING (owner_id = auth.uid())` 改成 `USING (false)`，執行 `python3 -m pytest -q tests/lab/test_c04.py`，再用 `git restore` 還原。
      預期：`test_rows` 失敗，訊息含 `positive control`。這證明「全部拒絕」的壞 lab 無法冒充安全對照組（稽核 P1-3）。
- [ ] 在 `lab/L05_cross_tenant_write/migration.sql` 末尾加一行 `ALTER TABLE public.projects DISABLE ROW LEVEL SECURITY;`，執行 `python3 -m pytest -q tests/lab/test_l05.py`，再還原。
      預期：11 failed，其中包含 `L05-S4`。被拒的寫入現在必須是 RLS 拒絕，不能是 NOT NULL 錯誤（稽核 P1-1）。
- [ ] 重現 ADR-019 的盲點：
      `docker exec -i supabase_db_rlsentry-lab psql -U postgres -c "create table public.zz(id int)" -c "with s as (insert into public.zz values (1) returning *) select count(*) from s" -c "insert into public.zz values (2)" -c "drop table public.zz"`，接著執行 `docker logs --since 1m supabase_db_rlsentry-lab 2>&1 | grep "public.zz"`。
      預期：有 create、`values (2)`、drop 三行，沒有 CTE 包住的 `values (1)`。SPEC §8 原本的驗證方法對 PostgREST 寫入是盲的。
- [ ] `python3 -m pytest -q tests/lab/test_shared_writes.py tests/lab/test_shared.py -k "postgrest or login"`
      預期：2 passed。PostgREST 的寫入歸屬於 authenticator；讀取不算寫入；GoTrue 的寫入不算 PostgREST 角色（ADR-014 #2、ADR-019）。
- [ ] 閱讀 `rlsentry/contracts/lab.py:77-86`（`WRITE_KEYWORD_RE`）與 `tests/lab/oracle_cases.py:142-170`（`_rls_denied`、`_check_status`）
      確認：你接受以關鍵字分類寫入。字串常值中的關鍵字可能讓寫入被多算，這個誤差方向是保守的。
- [ ] `python3 -c "from rlsentry.safety.mode import require_write_allowed as g; g('AUDIT','POST','http://localhost:54321/rest/v1/x')"`
      預期：`WriteRefused`，訊息含 `unknown profile`。字串形式的 profile 不會落到「localhost 允許」（稽核 P2-1）。
- [ ] `python3 -c "from rlsentry.safety.mode import require_write_allowed as g; from rlsentry.contracts.models import Profile as P; g(P.DEV,'POST','http://localhost:54321/rest/v1/%72pc/f')"`
      預期：`WriteRefused`，訊息含 `RPC`（稽核 P2-2）。
- [ ] `python3 -c "from rlsentry.safety.mode import require_write_allowed as g; from rlsentry.contracts.models import Profile as P; g(P.CI,'POST','https://preview.example.test/rest/v1/t',['preview.example.test']); print('ci ok'); g(P.DEV,'POST','https://preview.example.test/rest/v1/t',['preview.example.test'])"`
      預期：先印出 `ci ok`，再出現 `WriteRefused`。dev 即使列在清單中也不能寫遠端（你的 MS0 意見 #4、ADR-017）。不會發出任何網路請求。
- [ ] 閱讀 `rlsentry/safety/mode.py:50-80`
      確認：規則順序是 profile → URL → GET／HEAD → RPC → 登入 → audit → localhost → ci 清單 → 拒絕。RPC 的檢查排在登入例外與 profile 之前。
- [ ] 閱讀 ADR-020 第 6 點，並**做出決定**：「SafeClient 必須綁定 AuthorizationRecord」（稽核 P1-1）延到 MS6，改由 pipeline 的靜態測試加上計數測試保證。
      若你要求在 MS2 之前就改，請寫在核准意見中。
- [ ] `python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md`
      預期：沒有差異（ADR-015）。
- [ ] `git show origin/rlsentry-holdout:MS1/test_holdout_safety.py | sha256sum`
      預期：`304a5c374b6a6469de388329f20a73a13650d0aa7212d07e2aa4566836154f6b`。
- [ ] 開啟 `docs/reviews/MS1-high-risk.md` 中任一 compare 連結（例如 T-051、T-065）
      確認：diff 只含該 ticket 的檔案。

## 4. 與 SPEC 的偏差與假設
- **§8「`log_statement = mod` 驗證 0 次寫入」**：此前提不成立，因為 PostgREST 以 CTE 包住寫入。全域仍保留 `mod`，另外讓 authenticator 記錄全部語句，再以關鍵字分類（ADR-019）。
- **§2 ci 寫入遠端**：依你的 MS0 核准意見開放。必須列在 `write_hosts`，host 完全比對，dev 一律不寫遠端（ADR-017）。
- **§5 Safety**：非 GET 請求一律過閘門，唯一例外是登入（ADR-014 #1）；未知 profile 一律拒絕；RPC 路徑先正規化再比對（ADR-020）。
- **§8 每個情境的 `frontend/`**：手寫的模擬打包輸出，不跑 npm 建置。真實框架的 bundle 留到 MS5（ADR-018 #3）。
- **lab 由單一常駐 Supabase 逐情境載入**，不是每個情境各自 `supabase start`（ADR-018）。
- **ticket 指引「最多 3 個檔案」**：情境 ticket 有 4 個檔案（ADR-018 後果）。

## 5. 已知限制
- **lab 需要 Docker**：從 MS1 起，每次 accept 與 verify-milestone 都要 Docker；沒有 Docker 時 lab 測試會失敗，不會略過（ADR-018）。
- **`apply()` 的清除範圍**：只涵蓋 public schema、storage、auth.users、`pgrst.openapi_mode`。情境若建立 role 或其他 role 層級設定，不會被清除（稽核 lab P2-2）；目前沒有情境這樣做。
- **NFR-02 授權綁定、NFR-03 遮罩套用到所有輸出、NFR-04 預設 5 rps 的整合測試**：要等 MS6 的 pipeline 才能完成（ADR-020、追溯表）。
- **`trust_env=False` 只能靠程式審查**：沒有不連網又可行的行為測試。
- **重設連線後第一次登入可能 HTTP 500**：labctl 重設 role 設定後，第一次 GoTrue 登入曾回 500。T-077 改為輪詢到可登入才返回；冷啟動重跑兩次都通過，但仍可能偶發。
- **blocked**：T-071（見第 1 段）。
- **流程問題**：
  - push protection 曾擋下 `sb_secret_` 格式的測試字串（你已放行，之後的測試改為執行時組字串）。
  - T-061、T-065 一度在 labctl 修正前通過驗收，原因是共用 lab 殘留了狀態。之後已以冷啟動重新驗證（PRODUCTION_LOG）。
