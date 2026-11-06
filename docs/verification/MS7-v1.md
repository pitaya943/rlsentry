# MS7 驗證清單 v1（main @ 0ef14ba0a）

## 1. 本模組做了什麼
- **MS6 核准意見第 1 點（ADR-049）**：M4 把 proven 讀取改標為 SECURITY_DEFINER_RPC_DATA 時，嚴重度取 max(原本的嚴重度, Medium)。anon 經 SECURITY DEFINER RPC 讀到含敏感欄位的資料 → Critical，一般 → High，使用者 → Medium；有無 DB 連線時 ci 的 fail_on 結果相同（單元測試三種門檻；lab 的 L07 e2e）。L07-V1 ground truth 改為 high。**分段上線**：合約常數先為 False（T-240）→ 實作（T-241）→ architect 在同一個 merge 切換常數、ground truth 與既有測試（T-245），每一次合併的回歸測試都是綠的。
- **ADR-047 已知限制（ADR-051）**：修正三項——DROP POLICY 只刪可能服務該角色的 policy、policy 名稱 ≤ 63 bytes（超過時加 sha256 前 8 碼）、L03 提權還原為**原值**（讀不到或已是 admin 就完全不寫入）；維持五項並揭露。
- **USAGE.md**（繁體中文）：安裝、設定檔每個欄位、S4、三種 profile、報告與 exit code 0–5、GitHub Action、`rlsentry init`、Python API、已知限制；**6 個 doctest**（init、dev L04、ci L05、audit L08 含 S4 拒絕與確認、展示情境 L04、Python API），`make acceptance` 全部執行通過。lab 的 shell 入口 `python -m lab._shared up|apply|env|sql|serve`（T-244，ADR-052）。範例設定檔 `docs/examples/`。
- **Benchmark**（MS4 核准意見第 1 點；`docs/benchmark/MS7-bench.json`，最終程式碼）：recall **32/32**、precision 32/32、FPR **0/72**、coverage **109/109**、inconclusive 7/109、safe_decided 69/69、probe-only 2 類；audit 16 個情境 DB 寫入皆 0；runtime 5／20／50 張 5.6／20.7／**50.8 s**（rps 5 未調）。與 MS6 相比只有逐情境 `runtime_s` 不同。
- **D2–D4**：D2 ADR-037（不支援無頭瀏覽器）；D3 **ADR-050**（新增：不提供 Web 介面，CLI 產生靜態 HTML）；D4 ADR-013＋補記（Firebase 列為未來工作）。
- **`make acceptance`**：第一次失敗兩項（3 個舊 holdout 被已核准的行為變更打破；traceability 中一列已解決的 MS0 P0 仍寫著缺）→ T-248、**ADR-053** → 第二次 **final: ALL PASSED**。
- ticket：T-240–T-248 共 9 張，全部 1 次通過；blocked 僅 T-071（MS1 遺留，已由 T-080 交付）。
- ADR：049（嚴重度）、050（D3）、051（已知限制處理）＋補記、052（USAGE／lab 入口／demo）、053（holdout 更新）；ADR-013 補記（D4、更正過時描述）。
- 收尾 SOP（ADR-048）本 milestone 未修改，`.claude/skills/` 不需要重新複製或 refreeze。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `make acceptance`：**final: ALL PASSED**（tickets、provenance、ruff、mypy、tests、全部 milestone 的 holdout、safety、checklist sync、prior milestones approved、benchmark thresholds、profile end-to-end、6 個 USAGE doctest、ADR D2–D4、traceability）。紀錄：`logs/acceptance-final.json`。
- `python3 harness/acceptance.py --milestone MS7 --no-vc`：**MS7: ALL PASSED**（holdout 7 項）。
- auditor（兩部分，base b3c8c2bb2，只讀程式碼與文件，未執行任何測試或 lab 指令）：Part A safety 判定 PASS，P0、P1 無；P2 列為已知限制（ADR-051 補記）。Part B：P1 三項（demo doctest 沒有斷言修補前的 Confirmed、「splinter 沒報」沒有斷言、沒有 doctest 執行紀錄）→ T-247 補斷言，執行紀錄由 `make acceptance` 產生。詳見 `docs/verification/traceability.md` 的 MS7 段。
- 派工前參考實測（scratchpad 的獨立 worktree，草稿程式未提交）：草稿實作後跑可見測試、lab 與 e2e 319 passed、MS7 holdout 7 passed；派工前抓到 3 個測試本身的問題（PRODUCTION_LOG）。真實 GoTrue：`user_metadata.role = editor` 的帳號在提權與還原後仍為 `editor`。

## 3. 請你親手驗證（逐項打勾）
在容器內執行 `make verify-milestone MS=MS7`（下面第一項）。每條指令都在獨立的 code block 中、都是單行，都在 lab 以本清單標頭的 sha 實跑過（ADR-030 與補記）。審查流程新增「MS7（交付）的額外步驟」（`docs/verification_steps.html` 步驟 8 之後，本次同一個 commit 更新）。

**Codespaces 準備（ADR-025；完整說明見 `docs/verification_steps.html` 步驟 4.5）**：在 `claude/busy-darwin-asvox3` 開 Codespace，依序執行：
```bash
pip install -e ".[dev]"
```
```bash
curl -fsSL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.tar.gz | sudo tar -xz -C /usr/local/bin supabase && supabase --version
```
```bash
docker info >/dev/null 2>&1 || (sudo dockerd >/tmp/dockerd.log 2>&1 &); sleep 5; docker info >/dev/null 2>&1 && echo DOCKER_OK
```
```bash
python -m lab._shared up
```
最後一行預期印出 `http://127.0.0.1:54321`（MS7 新增的 lab 入口；MS7 沒有新增相依套件）。確認 Codespace 的 sha：
```bash
git rev-parse HEAD
```
不一致時（中間多了只改 logs/ 或文件的紀錄 commit），把本機 sha 填入下面的 `LOCAL` 再執行，必須沒有輸出（唯一需要你填值的指令）：
```bash
LOCAL=請貼上本機sha; git diff --stat $LOCAL HEAD -- rlsentry tests lab action pyproject.toml USAGE.md docs/examples
```
測完一律還原、不提交、不推送，再刪除 Codespace：
```bash
git restore .
```

- [ ] 【本機】＋【Actions 涵蓋】在容器內執行 `make verify-milestone MS=MS7`。依 ADR-022 三段信任鏈：(a) 本機 `host/review.sh` 第 1、2 步（同步＋防竄改，須看到 `✓ no changes to frozen files`）；(b) GitHub Actions `verify-milestone`，ref=`claude/busy-darwin-asvox3`，最後一行 `MS7: ALL PASSED`；(c) 兩個 sha 的差異排除 logs/ 後為空。容器內的指令：
  ```bash
  make verify-milestone MS=MS7
  ```
  (c) 的比對（把兩個 sha 填入後執行，預期沒有輸出）：
  ```bash
  LOCAL=請貼上本機sha; ACTIONS=請貼上Actions的sha; git diff --stat $LOCAL $ACTIONS -- . ':!logs'
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提，ADR-026）MS6 核准意見第 1 點：改標不得降低嚴重度**。讓 `rlsentry/whitebox/correlate.py:66` 永遠不保留較高的嚴重度（等於回到 SPEC 表一律 Medium）：
  ```bash
  sed -i 's/if higher and SEVERITY_RANK/if False and SEVERITY_RANK/' rlsentry/whitebox/correlate.py && python3 -m pytest -q tests/whitebox/test_correlate_severity.py
  ```
  預期：`5 failed, 7 passed`，失敗的是 `test_relabel_keeps_the_higher_severity[anon-columns0-critical]`、`[anon-columns1-high]`、`test_default_reads_the_contract_flag_at_call_time[True-high]`、`test_ci_fail_on_is_the_same_with_and_without_a_db_connection[anon-columns0-critical]`、`[anon-columns1-high]`，訊息含 `anon high fail_on=high: 1 != 0`（沒有 M4 時 ci 失敗、有 M4 時通過）。使用者角色的兩個案例仍通過（本來就是 Medium）。還原：
  ```bash
  git restore rlsentry/whitebox/correlate.py
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提）USAGE doctest 的關鍵斷言：「splinter 沒報」**。讓 correlate 把沒有 lint 的 finding 也標成 confirmed（`rlsentry/whitebox/correlate.py:58`），再執行 USAGE.md 3.1 的 dev doctest（這條指令從 USAGE.md 取出該區塊交給 sh 執行，與 `make acceptance` 執行的是同一段文字）：
  ```bash
  sed -i 's/update={"correlation": "probe_only", "lint": None}/update={"correlation": "confirmed", "lint": None}/' rlsentry/whitebox/correlate.py && sed -n "/^### 3.1 dev/,/^預期/p" USAGE.md | sed -n '/^```bash$/,/^```$/p' | sed '1d;$d' | sh; echo "doctest exit=$?"
  ```
  預期：掃描摘要照常印出，最後是 `AssertionError: [('CROSS_TENANT_READ', 'user_a', 'medium', 'confirmed'), ('CROSS_TENANT_READ', 'user_b', 'medium', 'confirmed')]` 與 `doctest exit=1`。意義：doctest 真的斷言了 `probe_only`（MS7 auditor Part B P1-2），`make acceptance` 會因此失敗。還原：
  ```bash
  git restore rlsentry/whitebox/correlate.py
  ```
- [ ] 【Codespaces 必做變異】（非簽章前提）**提權還原為原值**（ADR-051 #3）。讓還原改回 MS6 的「設為 null」（`rlsentry/probe/escalation.py:150`）：
  ```bash
  sed -i 's/^                    original)$/                    None)/' rlsentry/probe/escalation.py && python3 -m pytest -q tests/probe/test_escalation_restore.py
  ```
  預期：`1 failed, 16 passed`，失敗的是 `test_original_role_is_put_back_after_the_finding`。還原：
  ```bash
  git restore rlsentry/probe/escalation.py
  ```
- [ ] 【Codespaces 必做】還原後確認回到全綠：
  ```bash
  python3 -m pytest -q tests/whitebox/test_correlate_severity.py tests/probe/test_escalation_restore.py
  ```
  預期：`29 passed`。
- [ ] 【Codespaces 必做】**照 USAGE.md 親手跑一次 dev／ci／audit**（SPEC §11 MS7 審查重點）。可以直接複製 USAGE.md 3.1–3.3 與第 4 節的區塊逐行貼上；或用下面四條（每條把 USAGE.md 中對應的區塊原樣交給 sh）。dev（L04）：
  ```bash
  sed -n "/^### 3.1 dev/,/^預期/p" USAGE.md | sed -n '/^```bash$/,/^```$/p' | sed '1d;$d' | sh
  ```
  預期最後一行：`dev OK [('CROSS_TENANT_READ', 'user_a', 'medium', 'probe_only'), ('CROSS_TENANT_READ', 'user_b', 'medium', 'probe_only')]`。ci（L05）：
  ```bash
  sed -n "/^### 3.2 ci/,/^預期/p" USAGE.md | sed -n '/^```bash$/,/^```$/p' | sed '1d;$d' | sh
  ```
  預期最後兩行：`exit=1`、`ci OK [('CROSS_TENANT_WRITE', 'user_a', 'high'), ('CROSS_TENANT_WRITE', 'user_b', 'high')]`。audit（L08，含 S4）：
  ```bash
  sed -n "/^### 3.3 audit/,/^預期/p" USAGE.md | sed -n '/^```bash$/,/^```$/p' | sed '1d;$d' | sh
  ```
  預期：先印出 S4 拒絕訊息（`the frontend bundle points at http://127.0.0.1:54321; to scan it, add ...`），之後 `CRITICAL SECRET_KEY_IN_BUNDLE jwt:service_role - -`、`first=3 second=0`、`audit OK [('SECRET_KEY_IN_BUNDLE', 'jwt:service_role', 'critical')]`。展示情境（L04）：
  ```bash
  sed -n '/^## 4. 展示情境/,/^逐步說明/p' USAGE.md | sed -n '/^```bash$/,/^```$/p' | sed '1d;$d' | sh
  ```
  預期依序看到：`correlation: probe_only`、`2/2 known rows outside the expected scope are visible`、以 `curl -sS -X GET 'http://127.0.0.1:54321/rest/v1/notes?select=id&id=in.%28` 開頭且 key 為 `eyJhbG****…` 的重現指令、修補 SQL 三行（ENABLE RLS、`DROP POLICY "notes_select"`、`CREATE POLICY "rlsentry_notes_select_user" ... USING (auth.uid() = "owner_id");`）、`before fix: [...probe_only...]`、`ok`、修補後 `Confirmed: 0 (none)`，最後 `demo OK: no confirmed finding after the fix`。dev 報告可用瀏覽器開 `/tmp/rlsentry-dev/rlsentry-report.html`。
- [ ] 【Codespaces 必做】MS6 核准意見第 1 點的 lab 證明：L07 在 ci，有無 DB 連線的 exit code 都是 1，anon 為 High、使用者為 Medium：
  ```bash
  python3 -m pytest -q tests/e2e/test_ci_definer_severity.py
  ```
  預期：`2 passed`（約 7 秒）。（我另外實測過：把 correlate.py:66 照第 2 項變異後，這個 lab 測試的「有 M4」參數會失敗，anon 變成 Medium。）
- [ ] 【Codespaces 必做】三種 profile 的端到端（SPEC §9）：
  ```bash
  python3 -m pytest -q -m e2e_profiles tests
  ```
  預期：`16 passed, 1283 deselected`（約 50 秒）。比 MS6 多 2 個（L07 有無 DB 連線）；`test_ci_fails_only_on_confirmed_high[L07-1]` 的期望由 0 改為 1（ADR-049）。
- [ ] 【Codespaces 必做】MS7 的最終檢查（`docs/verification_steps.html`「MS7（交付）的額外步驟」）：
  ```bash
  make acceptance
  ```
  預期：最後一行 `final: ALL PASSED`（約 45 分鐘，含完整 benchmark：`recall=1.000 precision=1.000 fpr=0.000`、`6 USAGE.md doctests passed`）。
- [ ] 【本機】benchmark 重跑沒有改變任何計分（MS4 核准意見第 1 點），預期沒有輸出：
  ```bash
  git diff --no-index -U0 docs/benchmark/MS6-bench.json docs/benchmark/MS7-bench.json | grep '^[+-] ' | grep -v runtime_s
  ```
- [ ] 【本機】閱讀 `rlsentry/contracts/whitebox.py:74` 與 `rlsentry/whitebox/correlate.py:36-70`。確認：常數為 `True`；`keep_higher` 為 None 時於呼叫當下讀合約模組；只有嚴重度取較高者，規則名稱與 id 仍改為 SECURITY_DEFINER_RPC_DATA；`rlsentry/pipeline.py` 呼叫 correlate 時沒有傳 `keep_higher`（auditor 親手檢查項）。
- [ ] 【本機】閱讀 `rlsentry/probe/escalation.py:86-155`。確認：讀取原值（第 89 行）在任何 PUT 與 `try`（第 101 行）之前；讀不到或已是 admin 時 `continue`，不會進入 finally 的還原；還原傳入 `original`；note 中沒有原值（auditor 親手檢查項）。
- [ ] 【本機】閱讀 `lab/_shared/__main__.py:46-62`。確認：`serve` 只綁 `127.0.0.1`，目錄中沒有 `0.0.0.0`；這是測試基礎設施，不是產品程式。
- [ ] 【本機】閱讀 ADR-049、ADR-051（含補記）、ADR-053，並決定第 4 段標「需要你決定」的兩件事，寫進核准意見（或在 `/final-question` 回答）。
- [ ] 【本機】文件同步（ADR-021、ADR-028、ADR-031）。執行下面這條，預期沒有輸出（harness 之後若只追加 logs/，以本清單標頭的 sha 為準）：
  ```bash
  python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md
  ```

## 4. 與 SPEC 的偏差與假設
- **§5 M5 嚴重度表（ADR-049）**：表格把「anon 經 SECURITY DEFINER RPC 實際取得受保護資料」列為 Medium；依你的 MS6 核准意見第 1 點，改標時保留較高的嚴重度（anon High／含敏感欄位 Critical）。照你的指示以 MS7 ticket 處理，修改了 MS6 已核准的行為但沒有 reopen MS6。
- **需要你決定 1（ADR-053）**：3 個舊 holdout（MS2 ×2、MS6 ×1）被已核准的行為變更（ADR-039、ADR-040、ADR-051 #1）打破，`make acceptance` 因此無法通過。我以 `holdout.py add` 覆寫了這兩個檔案，只換掉衝突的輸入或斷言（舊版在 rlsentry-holdout 分支的歷史中）。holdout 原本應由 architect 在派工前寫、與實作獨立，這次是在知道實作之後改的。選項：A 接受（ADR-053 逐項說明）；B 要求 reopen MS2／MS6 重新核准這三個測試。我的建議是 A：每個修改都保留原測試要守的性質，並在 ADR 中逐項列出。
- **需要你決定 2（ADR-051 補記 #1）**：修補 SQL 的 DROP 會刪掉 `TO public` 或同時涵蓋 anon 與 authenticated 的 policy，但新建的 policy 只給該 finding 的角色；套用後另一個角色原本合法的存取可能消失。選項：A 維持為已知限制（修補 SQL 本來就要人工審閱）；B 交付後另開工作，在這種情況加註解行提醒。我的建議是 A。
- **traceability 的一列改寫**：MS0 段「§8 ground truth 與真實 Postgres 一致」的審查時狀態原為「MISSING P0」，已於 MS1 由 `tests/lab` 的 oracle 測試解決，但文字未更新，`make acceptance` 的 traceability 檢查因此失敗。我改寫為「審查時缺（P0）；已於 MS1 解決」並附證據（T-248；原文在 git 歷史）。
- **lab 命令列入口**（ADR-052）：新增 `lab/_shared/__main__.py`（測試基礎設施），讓 USAGE.md 的 doctest 可從 shell 操作 lab；SPEC 沒有要求。
- **沿用 MS6 的偏差**（MS6-v1 第 4 段）：audit 有 DB 連線時也跑 M4；設定檔增補 `supabase_url`、`anon_key_env`、`db_schemas`；S4；fail_on 只在 ci 生效、exit code 4、5；SARIF location 指向設定檔。

## 5. 已知限制
- **修補 SQL**（ADR-051）：一律使用 `db_schemas[0]`；函式 DDL 不含參數簽章（多載時以錯誤失敗，不會改錯函式）；DROP 範圍見第 4 段「需要你決定 2」；policy roles 為自訂角色時不會被 DROP。
- **嚴重度保證依賴合約常數**：`RELABEL_KEEPS_HIGHER_SEVERITY = True`，沒有執行期防護；由單元測試、lab e2e 與 holdout 把關。改標為 Critical 的路徑（anon＋敏感欄位）只有單元測試，沒有 lab 情境；e2e 只用預設 fail_on。
- **ADR-040 的副作用**（ADR-053 揭露）：anon 的合併讀取只要一個 401 就整格 inconclusive，並失去「公開表含敏感欄位」的提示。實際 PostgREST 不會對單列回 401，影響有限。
- **M4 部分失敗**：`read_policies` 失敗時 M4 從 modules 移除，但 correlate 的改標保留（不會降低嚴重度）。
- **L03 提權**：只試 `user_metadata.role = admin`；原本沒有 role 的帳號還原後是 `role: null`；還原失敗時報告 notes 要求人工清除。
- **lab 入口**：`serve --port` 未檢查範圍（被占用時以 traceback 結束）；`env` 會印出 lab 密碼；只影響本機 lab。
- **Benchmark**：只有 16 個情境、32 個漏洞案例，數字只描述這個 lab；runtime 由限速器決定（請求數不變時幾乎固定），表或角色增加時線性增加。L11（Storage）沒有探測。M1 不執行前端 JavaScript（D2）。
- **其他沿用 MS6**：報告 curl 含主鍵值；讀取植入只在使用者能 INSERT 的表成功；遠端寫入被拒時寫入 cell 為 inconclusive；「表擁有者 role」JWT 不在 Critical 集合；GitHub Action 對 audit 設定檔永遠不失敗；dev 的 M3 計時含植入與清理。
- **過程紀錄**：MS7 的 holdout 登錄時一併提交了 scratch 資料夾中的 `.ruff_cache/` 與 `__pycache__/`（不影響驗證）；MS7 參考實測沒有跑其他 milestone 的 holdout，所以 ADR-051 #1 對 MS6 holdout 的影響到 `make acceptance` 才發現（ADR-053 流程教訓）。
- **blocked ticket**：僅 T-071（MS1 遺留，已由 T-080 交付）。
