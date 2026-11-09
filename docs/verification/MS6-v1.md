# MS6 驗證清單 v1（main @ b3c8c2bb2）

## 1. 本模組做了什麼
- **`pipeline.run_scan`**（SPEC §4、FR-16）：授權（不送任何請求）→ 建立唯一的 SafeClient → M1 → **S4 端點確認** → M2 → 登入、dev／ci 讀取植入、M3、dev／ci **L03 提權** → 清理（例外時也清理）→ M4（有 DB 連線時，含 `read_policies` 與設定檔的 `db_schemas`）→ M1 key finding 附在 correlate 之後 → M5。CLI（`rlsentry scan`／`init`）、Python API（`from rlsentry import run_scan`）、GitHub Action（`action/action.yml`）都只呼叫它；bench 也改經它（ADR-042）。
- **M5 報告**：JSON、自包含 HTML（沒有 script 與外部資源）、SARIF 2.1.0（以官方 schema 驗證）；依「證據等級 → 嚴重度」排序；每個 finding 附標題、遮罩後的 curl、修補 SQL（識別字一律加引號，工具不執行）、參考連結。exit code：只有 ci 有門檻，預設 Confirmed 且 ≥ high → 1；清理失敗 4；崩潰 5（ADR-044、047）。
- **核准意見**：MS5 第 4 點（supabase_admin、postgres 等高權限 JWT → Critical，ADR-038）、第 6 點（S4：Supabase URL 必須由設定檔或 `--supabase-url` 指名，bundle 指向的主機一個請求都收不到，ADR-043）、第 7 點（MS4 lab 測試只檢查 SECURITY 類 lint，ADR-045）；MS4 第 2 點（同一身分的已知主鍵合併為單一 GET，50 張表 50.8 s，ADR-040）、第 3 點（L04 報告附重現指令與修補 SQL，套用後重掃無漏洞）、第 5 點 (a)–(d)（ADR-039、bench `splinter_status` 依 `db_schemas`、`read_policies` 的 DB log 唯讀測試）；MS3 第 1 點（L03 提權、dev／ci 讀取植入、遠端 WriteRefused → inconclusive，ADR-041、042）。
- **Benchmark**（`docs/benchmark/MS6-bench.json`）：recall **32/32**、precision 32/32、FPR 0/72、coverage 1.0、probe-only 2 類；audit 16 個情境 DB 寫入皆 0；runtime 5／20／50 張 5.6／20.7／**50.8 s**（達標，rps 5 未調整）。
- ticket：24 張 done（T-200–T-235，T-210 取消併入 T-200）。嘗試次數 > 1：T-212（3 次；我把它排在 T-211 之前，且 T-201 漏改 `test_scan_writes.py`，由 T-203 修正，程式未改）、T-230（2 次；ADR 文字含被禁止的字詞）。blocked：僅 T-071（MS1 遺留，已由 T-080 交付）。
- ADR：038–045、047（另有 ADR-042 補記 ×2）。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS6 --no-vc`：**MS6: ALL PASSED**（tickets、provenance、ruff、mypy、tests、holdout 16、safety、checklist sync；mutation 需 MUTATION=1）。
- auditor：第 1 次派工在 30 回合內未交報告，改為兩部分重派（safety／正確性，只讀程式碼，未執行任何測試或 lab 指令）。P0 無；P1 共 4 類（例外時不清理 canary、提權還原可能不執行或靜默失敗、CLI 崩潰的 exit code 與 traceback、一個安全測試零請求也會通過）→ T-232–T-235 修正；P1「limit 削弱過濾檢查」不成立（理由見 ADR-047）。詳見 `docs/verification/traceability.md` 的 MS6 段。
- 派工前參考實測（草稿程式，未提交）：L03 提權實測、C04 植入 403、高權限 role 實測集合、合併讀取 50.6 s；草稿參考實作跑全部可見測試、holdout 與完整 benchmark，派工前抓到 L05 提權偽陽性（ADR-042 補記）與 7 個測試本身的問題。

## 3. 請你親手驗證（逐項打勾）
在容器內執行 `make verify-milestone MS=MS6`（下面第一項）。每一條指令都放在獨立的 code block 中，都是單行，都在 lab 以本清單標頭的 sha 實跑過（ADR-030 與補記）。審查流程沒有改變，`docs/verification_steps.html` 本次未更新（`/final-question`、`/approved` 的 SOP 等你確認後才會寫入，見第 4 段）。

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
python3 -c "from lab._shared import labctl; print(labctl.ensure_up().api_url)"
```
最後一行預期印出 `http://127.0.0.1:54321`。MS6 新增相依套件 typer、jinja2（執行期）與 jsonschema（測試），上面的 `pip install` 已涵蓋。確認 Codespace 的 sha：
```bash
git rev-parse HEAD
```
不一致時（中間多了只改 logs/ 或文件的紀錄 commit），把本機 sha 填入下面的 `LOCAL` 再執行，必須沒有輸出（唯一需要你填值的指令）：
```bash
LOCAL=請貼上本機sha; git diff --stat $LOCAL HEAD -- rlsentry tests lab action pyproject.toml
```
測完一律還原、不提交、不推送，再刪除 Codespace：
```bash
git restore .
```

- [ ] 【本機】＋【Actions 涵蓋】在容器內執行 `make verify-milestone MS=MS6`。依 ADR-022 三段信任鏈：(a) 本機 `host/review.sh` 第 1、2 步（同步＋防竄改，須看到 `✓ no changes to frozen files`）；(b) GitHub Actions `verify-milestone`，ref=`claude/busy-darwin-asvox3`，最後一行 `MS6: ALL PASSED`（Actions 只證明通過，不顯示細節）；(c) 兩個 sha 的差異排除 logs/ 後為空。容器內的指令：
  ```bash
  make verify-milestone MS=MS6
  ```
  (c) 的比對（把兩個 sha 填入後執行，預期沒有輸出）：
  ```bash
  LOCAL=請貼上本機sha; ACTIONS=請貼上Actions的sha; git diff --stat $LOCAL $ACTIONS -- . ':!logs'
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提，ADR-026）audit 無法寫入**。同時拿掉兩道防線：pipeline 的「audit 不植入、不提權」（`rlsentry/pipeline.py:144`）與 SafeClient 閘門的 audit 拒絕（`rlsentry/safety/mode.py:74`）：
  ```bash
  sed -i 's/writes = profile is not Profile.AUDIT/writes = True/' rlsentry/pipeline.py && sed -i 's/    if profile == Profile.AUDIT:/    if profile == Profile.AUDIT and False:/' rlsentry/safety/mode.py && python3 -m pytest -q tests/pipeline/test_run_scan_safety.py
  ```
  預期：`FAILED tests/pipeline/test_run_scan_safety.py::test_audit_sends_only_reads_and_the_login_post`，訊息含 `'/rest/v1/notes' != '/auth/v1/token'`（audit 送出了植入的 POST）。意義：兩道防線都失效時，測試會抓到 audit 寫入（NFR-01，MS6 焦點）。只拿掉第一道時，閘門仍擋下所有寫入，只有 `test_run_scan.py` 的「audit 未植入」註記測試會失敗（我已實測）。還原：
  ```bash
  git restore rlsentry/pipeline.py rlsentry/safety/mode.py
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提）CI 只在 Confirmed 時失敗**。拿掉 `rlsentry/report/exit_code.py:20` 的證據等級條件：
  ```bash
  sed -i 's/if EVIDENCE_RANK\[f.evidence\] >= need_ev and /if /' rlsentry/report/exit_code.py && python3 -m pytest -q tests/report/test_exit_code.py
  ```
  預期：`3 failed, 8 passed`，失敗的是 `test_ci_default_fails_only_on_confirmed_high_or_worse[suspected-critical-0]`、`[config_warning-critical-0]` 與 `test_custom_threshold_ranks_evidence_and_severity`。意義：只有 Suspected／Configuration warning 的 Critical 也會讓 CI 失敗（MS6 焦點、FR-13）。還原：
  ```bash
  git restore rlsentry/report/exit_code.py
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提）S4：bundle 指向未確認的主機時一個請求都不送**。讓 pipeline 把 bundle 中的 URL 當成使用者確認的 URL（`rlsentry/pipeline.py:124`）：
  ```bash
  sed -i 's/resolve_endpoint(config, cli_supabase_url, rec.result.supabase_url)/resolve_endpoint(config, cli_supabase_url or rec.result.supabase_url, rec.result.supabase_url)/' rlsentry/pipeline.py && python3 -m pytest -q tests/pipeline/test_run_scan_safety.py
  ```
  預期：`2 failed, 7 passed`，失敗的是 `test_bundle_pointing_at_an_unconfirmed_host_gets_zero_requests` 與 `test_even_the_real_api_url_is_not_used_until_the_user_names_it`。意義：惡意前端可讓測試帳號的密碼與所有探測送往使用者沒有授權的主機（MS5 核准意見第 6 點）。還原：
  ```bash
  git restore rlsentry/pipeline.py
  ```
- [ ] 【Codespaces 必做】還原後確認 safety 測試回到全綠：
  ```bash
  python3 -m pytest -q tests/pipeline/test_run_scan_safety.py
  ```
  預期：`9 passed`。
- [ ] 【Codespaces 必做】三種 profile 的端到端測試（SPEC §9；需 Docker）：dev 跑完 M1–M5 並確認 L05 轉移；ci 只在 L05（Confirmed、high）回 1，L04、L07（Medium）與 C01 回 0；audit 以 DB log 證明 0 寫入；CLI 端到端；L04 展示（套用修補 SQL 後重掃無漏洞）；lab 上的 S4；L03 提權與還原；C04 在 dev 仍為 inconclusive：
  ```bash
  python3 -m pytest -q -m e2e_profiles tests
  ```
  預期：`14 passed, 1238 deselected`（約 40 秒，不含第一次拉映像）。
- [ ] 【Codespaces 必做】親眼看 L04 展示情境的重現指令與修補 SQL（ci profile、有 DB 連線；MS4 核准意見第 3 點）：
  ```bash
  python3 -c "from lab._shared import labctl;from tests.e2e.conftest import lab_config,lab_env;from tests.e2e.helpers import gt,scan;from rlsentry.contracts.models import Profile;i=labctl.ensure_up();labctl.apply('L04');r=scan(lab_config('http://127.0.0.1:1',i,gt('L04').policy,Profile.CI),lab_env(i));f=[x for x in r.findings if x.rule=='CROSS_TENANT_READ'][0];print(f.severity.value,f.role.value,f.correlation);print(f.repro);print(f.fix_sql)"
  ```
  預期（主鍵中 2 個 canary uuid 每次不同）：第一行 `medium user_a probe_only`；curl 以 `curl -sS -X GET 'http://127.0.0.1:54321/rest/v1/notes?select=id&id=in.%28...` 開頭、結尾為 `-H 'apikey: eyJhbG****n_I0' -H 'Authorization: Bearer eyJhbG****QYvw'`（key 只剩前 6 後 4）；修補 SQL 為：
  `ALTER TABLE "public"."notes" ENABLE ROW LEVEL SECURITY;`、`DROP POLICY "notes_select" ON "public"."notes";`、`CREATE POLICY "rlsentry_notes_select_user" ON "public"."notes" FOR SELECT TO authenticated USING (auth.uid() = "owner_id");`
- [ ] 【本機】閱讀 `rlsentry/pipeline.py:90-190`。確認：`authorize` 在任何請求與 `_new_client` 之前；`resolve_endpoint` 在 M1 之後、M2 之前；`writes = profile is not Profile.AUDIT` 控制植入、提權與清理；植入之後的 probe 與提權包在 try/finally，finally 一定呼叫 `cleanup_reads`；M4 失敗只記例外類別名稱；M1 finding 在 correlate 之後才附上。
- [ ] 【本機】閱讀 `rlsentry/safety/endpoint.py:46-66`。確認：`resolve_endpoint` 只回傳設定檔或 CLI 的 URL；`recon_url` 只出現在拒絕訊息，且經過 `report_url`。
- [ ] 【本機】閱讀 `rlsentry/probe/escalation.py`（整檔）。確認：只對「矩陣為 denied、且提權前重測仍看不到」的列提權；提權 PUT 發生網路錯誤時仍還原；還原失敗會加 note（auditor 親手檢查 3、4）。
- [ ] 【本機】閱讀 `action/action.yml`。確認：`run:` 區塊中沒有 `${{ inputs.* }}`（輸入只經 `env:`）、沒有 `--i-own-this-target`、上傳 SARIF 的步驟有 `if: always()`。
- [ ] 【本機】文件同步（ADR-021、ADR-028、ADR-031）。執行下面這條，預期沒有輸出（harness 之後若只追加 logs/，以本清單標頭的 sha 為準）：
  ```bash
  python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md
  ```
- [ ] 【本機】決定第 4 段標「需要你決定」的兩件事，寫進核准意見。

## 4. 與 SPEC 的偏差與假設
- **§2 profile 表**：audit 在提供 DB 連線時也執行 M4（唯讀，ADR-032 #2）；表格字面寫 audit 沒有 M4（ADR-042 #2）。ci 不跑 M1（照表格），所以 ci 必須用 `anon_key_env` 提供 anon key。
- **§6 設定檔增補**：`supabase_url`、`anon_key_env`、`db_schemas`；**資料模型增補**：`AuthorizationRecord.supabase_url／supabase_url_method`、`ScanReport.modules／notes／timings`、`Finding.title／repro／references`（ADR-042、043、044）。
- **S4（ADR-043）**：bundle 中的 URL 即使與 target 同源也不會被單獨使用；第一次掃描未設定 URL 的使用者會被拒絕一次。
- **fail_on 只在 ci 生效**（SPEC §2 表：dev、audit「不設」）；新增 exit code 4（清理失敗）、5（崩潰）。
- **SARIF 的 location 指向設定檔**：漏洞在資料庫，不在原始碼行。
- **PLAN 的「C04 在 dev 可判定」不成立**：C04 沒有 INSERT policy，植入回 403；ground truth 不變（ADR-042 #5）。
- **M4 失敗的處理範圍**：合約寫「任何例外 → note」，實作只攔 psycopg／OS／Value／Runtime 錯誤（lint 規則禁止攔截所有例外），其他例外會中止掃描（偏向 fail-closed，ADR-042 補記 2）。
- **需要你決定 1（ADR-047）**：M4 把 anon 的 RPC 越權讀取改標為 SECURITY_DEFINER_RPC_DATA 時，嚴重度依 SPEC §5 M5 表由 High（含敏感欄位時 Critical）降為 Medium，所以提供 DB 連線反而可能讓 `fail_on: high` 的 CI 通過。選項：A 照 SPEC（現狀）；B 改標時保留兩者中較高的嚴重度（偏離 SPEC 表）。
- **需要你決定 2**：progress.html 的更新時機與 `/final-question`、`/approved MS<N>` SOP（我在對話中提的方案）。確認後我會寫 ADR、`docs/sop/` 的 skill 草稿，並在同一個 commit 更新 `verification_steps.html` 步驟 8；skill 檔要放在凍結的 `.claude/` 下，需要由你安裝。

## 5. 已知限制
- 稽核 P2（ADR-047）：修補 SQL 一律使用 `db_schemas[0]`；函式 DDL 不含參數簽章（多載函式會失敗）；DROP POLICY 不看 policy 的 roles；policy 名稱超過 63 bytes 會被截斷；提權的還原把 role 設為 null 而非原值；「表擁有者 role」（如 supabase_storage_admin）的 JWT 不在 Critical 集合；GitHub Action 對 `profile: audit` 的設定檔永遠不會失敗（較嚴者勝）；dev 的 M3 計時含植入、提權與清理（runtime 目標以 audit 量測）。
- 提權只嘗試 `user_metadata.role = admin` 一種寫法；依其他 metadata 欄位授權的 policy 不會被測到。提權中斷且還原失敗時，測試帳號會殘留 role=admin（報告會有 note，需人工清除）。
- 報告的 curl 含主鍵值（重現需要）；以 email 等個資當主鍵的表會在報告中出現該值（system_overview 風險 4）。
- 讀取植入只在使用者能 INSERT 的表成功；其餘表維持 MS2 的「既有列」判定。
- 遠端 dev／ci 寫入被閘門拒絕時，寫入 cell 為 inconclusive（不是 denied），報告 notes 會說明。
- L11（P2）沒有 storage 探測。
- 過程紀錄：worker 重啟一次（驗收鏈中斷、Docker 停止，重建乾淨 lab 後續跑）；T-212 的兩次失敗是 architect 的排序與測試遺漏。詳見 PRODUCTION_LOG。
- blocked ticket：僅 T-071（MS1 遺留，已由 T-080 交付）。
