# MS4 驗證清單 v1（main @ 93e03445d）

## 1. 本模組做了什麼
- **M4 Whitebox（FR-11）**：以兩層唯讀連線執行 sha256 鎖定的 splinter 2026.09.1（交易內以參數化 `set_config('pgrst.db_schemas', …, true)` 設定，最後一律 rollback）；讀 `pg_policies`；把 SECURITY 類 lint 與 M3 finding 以物件名對照為 confirmed／probe_only／lint_only。SECURITY DEFINER 只有實測拿到資料才保留 confirmed，否則只給 SECURITY_DEFINER_EXECUTABLE（config_warning）。M4 不產生 confirmed。
- **Benchmark**：`python -m rlsentry.bench`（dev 計分＋audit 唯讀檢查、M4、5／20／50 表 runtime、JSON）。第一次完整結果：recall 29/32、precision 29/29、FPR 0/72、coverage 1.0、probe-only 2 類（L02、L04；L12 為與 L02 同類的第 6 個案例，ADR-035 補記）。原始 JSON：`docs/benchmark/MS4-bench.json`。見 `BENCHMARK_REPORT.md`。
- **MS3 核准意見第 1 點（L01／L05 寫入覆蓋）**：由 OpenAPI 的 `required`＋`format` 填必填欄位（ADR-034），L01、L05 的寫入案例現在都被確認；`test_scan_writes` 移除 MS3 的「無法植入」容忍。
- ticket：27 張全部 done（T-150–T-157、T-160–T-167、T-170–T-176）。嘗試次數 > 1：T-170（2，舊測試寫死 `measure`）。T-164 第 1 次派工用罄回合未提交、重派 1 次完成。blocked：僅 T-071（MS1 遺留，已由 T-080 交付）。
  - 核准意見處理：T-150（第 2 點→ADR-030、第 3 點→ADR-031、第 1 點延後項記入 `docs/PLAN.md` 的 MS6 表）。
  - 實測驅動的修訂：T-171／T-172（文字欄位依型別挑選，修 L05）、T-173／T-174（空 lint 也算量測、audit 也跑 M4）、T-157（測試 fixture）。
  - 稽核修正：T-175／T-176（P1-1：INSERT 的其他 uuid 欄位填攻擊者 id）。
- ADR：030（清單指令品質）、031（progress 同步）、032（M4 設計）、033＋補記（計分補充定義）、034＋補記 1、2（型別植入）、035＋補記（splinter_expected 實測、probe-only 2 類、展示情境 L04）。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS4 --no-vc`：**MS4: ALL PASSED**（tickets、provenance、ruff、mypy、tests、holdout 6、safety、checklist sync；mutation 需 MUTATION=1）。
- auditor（base 24b3473）：P0 無。第 2 次派工：P1-1 已由 T-175／T-176 修正；P1-2 經查不成立（所有 INSERT plan 都有 new_owner）。第 1 次派工的遲到報告（審到 aa7a8e6，並實跑全套 955 passed）另提出：probe-only「3 類」灌水（已更正為 2 類）、bench exit 1 與 L12 probe-only 沒有測試（T-175 已補）、`ScanReport.policies` 尚無人填入（延到 MS6，見第 4 段）、數字缺可核對的原始檔（已提交 `docs/benchmark/MS4-bench.json`）。P2 見第 5 段。詳見 `docs/verification/traceability.md` 的 MS4 段。
- holdout 在 acceptance 時發現自身 fixture 缺必填欄位（與 T-157 同一缺陷），只改 fixture、斷言不變後重加；新舊 hash 都記在 PRODUCTION_LOG。

## 3. 請你親手驗證（逐項打勾）
每一條指令都放在獨立的 code block 中（按右上角 Copy 即可貼上執行），都是單行，都在 lab 實跑過（ADR-030 與補記）。

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
最後一行預期印出 `http://127.0.0.1:54321`（第一次拉映像約數分鐘）。MS4 新增相依 `psycopg[binary]`，已包含在第一行。確認 Codespace 的 sha 等於本機驗證的 sha：
```bash
git rev-parse HEAD
```
不一致時（中間多了只改 logs/ 的紀錄 commit），把本機 sha 填入下面的 `LOCAL` 再執行，必須沒有輸出（這是唯一需要你填值的指令，因為本機 sha 只有你知道）：
```bash
LOCAL=請貼上本機sha; git diff --stat $LOCAL HEAD -- . ':!logs'
```
測完一律還原、不提交、不推送，再刪除 Codespace：
```bash
git restore .
```

- [ ] 【本機】＋【Actions 涵蓋】依 ADR-022 三段信任鏈：(a) 本機 `host/review.sh` 第 1、2 步（同步＋防竄改，須看到 `✓ no changes to frozen files`）；(b) GitHub Actions `verify-milestone`，ref=`claude/busy-darwin-asvox3`，最後一行 `MS4: ALL PASSED`（Actions 只證明通過，不顯示細節）；(c) 兩個 sha 的差異排除 logs/ 後為空。容器內的指令：
  ```bash
  make verify-milestone MS=MS4
  ```
  (c) 的比對（把兩個 sha 填入後執行，預期沒有輸出）：
  ```bash
  LOCAL=請貼上本機sha; ACTIONS=請貼上Actions的sha; git diff --stat $LOCAL $ACTIONS -- . ':!logs'
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提，ADR-026）SECURITY DEFINER 只有拿到資料才算漏洞**。把 `rlsentry/whitebox/correlate.py:20` 的「已證實」條件改成永遠成立，再跑測試：
  ```bash
  sed -i '20s/f.evidence is Evidence.CONFIRMED and RULES\[f.rule\].vulnerability/True/' rlsentry/whitebox/correlate.py && python3 -m pytest -q tests/whitebox/test_correlate.py
  ```
  預期：`2 failed, 8 passed`，失敗的是 `test_security_definer_without_data_is_only_a_configuration_warning` 與 `test_unproven_findings_never_count_as_probe_evidence`。意義：若把 INCONCLUSIVE_CELL 之類未證實的 finding 也當成「實測拿到資料」，L07 `ping_definer` 會被標成 confirmed、警告消失＝把設定警告說成漏洞（MS4 焦點）。還原：
  ```bash
  git restore rlsentry/whitebox/correlate.py
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提）計分必須比對 rule**。把 `rlsentry/bench/score.py:56` 的比對拿掉 rule：
  ```bash
  sed -i '56s/(f.target, f.op, f.role, f.rule) == (c.target, c.op, c.role, c.rule)/(f.target, f.op, f.role) == (c.target, c.op, c.role)/' rlsentry/bench/score.py && python3 -m pytest -q tests/bench/test_score.py
  ```
  預期：`1 failed, 11 passed`，失敗的是 `test_match_requires_rule_role_op_and_confirmed`（訊息含 `assert ('tp' == 'fn'`）。意義：規則錯的 finding 會被算成 TP，recall 被灌水（ADR-011 刻意的嚴格）。還原：
  ```bash
  git restore rlsentry/bench/score.py
  ```
- [ ] 【Codespaces 必做變異】（需 Docker）**M4 連線唯讀**。同時拿掉兩層唯讀：
  ```bash
  sed -i -e 's/default_transaction_read_only=on/default_transaction_read_only=off/' -e '/conn.read_only = True/d' rlsentry/whitebox/db.py && python3 -m pytest -q tests/lab/test_whitebox_lab.py::test_connection_is_read_only
  ```
  預期：`1 failed`，訊息含 `'off' == 'on'`。（architect 實測：只拿掉其中一層時測試仍通過，證明兩層是各自獨立的防線。）還原：
  ```bash
  git restore rlsentry/whitebox/db.py
  ```
- [ ] 【Codespaces 必做】不需 Docker 的 MS4 單元測試：
  ```bash
  python3 -m pytest -q tests/whitebox tests/bench tests/probe/test_fill.py tests/probe/test_seed_fill.py tests/probe/test_text_column.py tests/probe/test_insert_fill_actor.py tests/discovery/test_openapi_types.py
  ```
  預期：`54 passed`。
- [ ] 【Codespaces 必做】（需 Docker）M4 在真實 lab：
  ```bash
  python3 -m pytest -q tests/lab/test_whitebox_lab.py tests/lab/test_policies_lab.py tests/lab/test_whitebox_run_lab.py
  ```
  預期：`10 passed`。涵蓋：splinter 實跑、`db_schemas` 生效、連線拒絕寫入且 DB log 無寫入、L05 policy 條件式含 `with_check == "true"`、L07 定義者函式有資料→confirmed／無資料→只有警告、L02／L04／L12 為 probe_only。
- [ ] 【Codespaces 必做】（需 Docker）**splinter_expected 是實測值**：
  ```bash
  python3 -m pytest -q tests/lab/test_splinter_expected.py
  ```
  預期：`17 passed`（16 個情境逐一重跑 splinter，結果等於 expected.yaml，再加 1 個「沒有任何情境仍是 measure」）。這是 ground truth 沒有憑空填寫的唯一實證。
- [ ] 【Codespaces 必做】（需 Docker）L07 的 audit 結果。先執行：
  ```bash
  python3 -m rlsentry.bench --scenario L07 --json /tmp/l07.json
  ```
  預期結尾 `tp 3  fn 0  fp 0  tn 3  fp_safe 0`。再執行：
  ```bash
  python3 -c "import json; r=json.load(open('/tmp/l07.json')); a=[s for s in r['scenarios'] if s['profile']=='audit'][0]; print(a['db_writes'], a['splinter'], {c['case_id']: c['verdict'] for c in a['cases']})"
  ```
  預期：`0 reported {'L07-V1': 'tp', 'L07-V2': 'tp', 'L07-V3': 'tp', 'L07-S1': 'tn', 'L07-S2': 'tn', 'L07-S3': 'tn', 'L07-I1': 'inconclusive_ok', 'L07-W1': 'warning_seen'}`。意義：audit 0 次寫入；`ping_definer` 只出現警告（W1）且 cell 是 inconclusive，不是漏洞。
- [ ] 【Codespaces 必做】（需 Docker）probe-only 案例。先執行：
  ```bash
  python3 -m rlsentry.bench --scenario L02 --scenario L04 --scenario L12 --json /tmp/po.json | grep -E 'probe-only|precision|fpr'
  ```
  預期：`precision 6/6 = 1.000`、`fpr 0/16 = 0.000`、`probe-only L02: L02-V1, L02-V2, L02-V3`、`probe-only L04: L04-V1, L04-V2`、`probe-only L12: L12-V1`。再執行：
  ```bash
  python3 -c "import json; r=json.load(open('/tmp/po.json')); print([(s['scenario'], s['splinter'], s['splinter_lints']) for s in r['scenarios'] if s['profile']=='dev'])"
  ```
  預期：`[('L02', 'not_reported', []), ('L04', 'not_reported', []), ('L12', 'not_reported', ['rls_enabled_no_policy:audit_log'])]`（L12 唯一的 lint 落在另一張表）。
- [ ] 【Actions 涵蓋】holdout 與派工前紀錄一致：
  ```bash
  git fetch -q origin rlsentry-holdout && git show origin/rlsentry-holdout:MS4/test_holdout_whitebox.py | sha256sum
  ```
  預期 `cc747c1be74d8f2e0a7253bd0ba2af1f2cbc54d3172927c28fb26df985da6db5  -`（PRODUCTION_LOG 記錄的重加後 hash；舊 hash 與重加原因也在那裡）。
- [ ] 【本機】splinter 固定版本與上游一致。兩條指令的輸出都應為 `d8d558baad3e03832e521c527907fa50a9a172fabd899dd0f5c2504a5a0e9349`（等於 `rlsentry/contracts/whitebox.py` 的 `SPLINTER_SHA256`）：
  ```bash
  sha256sum rlsentry/whitebox/splinter.sql
  ```
  ```bash
  curl -sL https://raw.githubusercontent.com/supabase/splinter/2026.09.1/splinter.sql | sha256sum
  ```
- [ ] 【本機】閱讀 `rlsentry/whitebox/correlate.py:19-72` 與 `rlsentry/whitebox/db.py:1-19`。確認：只有 confirmed＋vulnerability 的 finding 算「實測證實」；新加的 finding 一律 lint_only、evidence 取自 RULES（不可能是 confirmed）；連線兩層唯讀、呼叫端 finally 中 rollback。再讀 `rlsentry/probe/write.py:131-145`：INSERT 的 owner 欄位是受害者、其他 uuid 欄位是攻擊者自己（ADR-034 補記 2）。
- [ ] 【本機】打開 `docs/reviews/MS4-high-risk.md`，依逐張（T-160、T-161、T-162、T-163、T-167、T-172、T-176）與抽查清單，以各 accept commit 看 diff；第 5 類抽查 L02、L07、L12 的 `splinter_expected`。
- [ ] 【本機】文件同步（ADR-021、ADR-028、ADR-031）。執行下面這條，預期沒有輸出：
  ```bash
  python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md
  ```
  再打開 `docs/system_overview.html`，確認架構圖 M4 方塊為完成、第 7 節 MS4 為「等待你審查」、第 8 節有 MS4 段落；打開 `docs/verification_steps.html`，確認步驟 4.5 的 Supabase CLI 安裝已改為單行、步驟 5 有 ADR-030／031 的說明。
- [ ] 【本機】**做出決定**：閱讀 `BENCHMARK_REPORT.md` 第 1、2、5 節。接受或要求修改：(a) recall 29/32 未達 95%，3 個 FN 是已核准延後項（L03→MS6、L08→MS5）；(b) runtime 50 表 70.7 s 未達 60 s（ADR-033 決定不調高預設 rps）；(c) 展示情境選 L04（ADR-035）；(d) probe-only 以漏洞類型計為 2 類（L12 不另計，ADR-035 補記）；(e) 第 5 段的 P2。

## 4. 與 SPEC 的偏差與假設
- **§9 Runtime 目標未達**：audit、預設 rps 5 下 50 張表 70.7 s（> 60 s）。依 ADR-033 不為達標而提高預設 rps；改善方向（合併主鍵查詢）列為未來工作。
- **§9 Recall 目標未達**：29/32。L03 提權（需重新登入，延到 MS6）與 L08 key（M1，MS5）尚未串接，誠實記為 FN、不從分母剔除（ADR-033 #8）。
- **splinter_expected 的定義**（ADR-033 #4）：只在 SECURITY 類 lint 落在該情境某個漏洞案例的目標上時算 `reported`；SPEC 未定義粒度。
- **probe-only 的「類」＝漏洞類型**（ADR-035 補記修訂 ADR-033 #5 的「類＝情境」）：MS4 為 2 類。
- **SPEC §5 M4 第 2 點「把 policy 條件式放進報告」**：`read_policies` 已完成並有 lab 測試，但 `ScanReport.policies` 要到 MS6 pipeline 才會填入（ADR-032 #8，已記入 PLAN 的 MS6 表）。
- **比對粒度＝物件名**（ADR-032 #5）：同一物件上 lint 與漏洞類型不同時也標 confirmed，報告會附 lint 名稱。
- **runtime 只計 M2＋M3**；M4 與 lab 設定不計時（ADR-033 #6）。

## 5. 已知限制
- 稽核 P2：correlate 以裸物件名比對，若 `db_schemas` 有多個 schema 且有同名物件會合併；finally 中的 rollback 在連線已斷時可能蓋掉原始錯誤；lab 以 superuser 執行 splinter（唯讀由兩層設定保證），真實專案應使用低權限角色（MS6 USAGE 說明）。
- 稽核 P2（第 1 次報告）：同一物件只要有任一角色被證實拿到資料，就會抑制其他角色的 SECURITY DEFINER 警告；`SECURITY_DEFINER_RPC_DATA` 套用在所有 RPC 讀取越權上，不論該函式是否為 SECURITY DEFINER（漏洞本身仍成立，只是規則名稱可能不精確）；`splinter_status` 寫死 public schema，而 `DEFAULT_DB_SCHEMAS` 尚未由設定檔傳入（MS6 接上時處理）；`read_policies` 沒有 DB log 層級的唯讀測試（與 run_splinter 共用 `open_readonly`）。
- `tests/lab/test_splinter_expected.py` 中不需 Docker 的部分是固定值釘選；真正的實測證據是需要 Docker 的參數化部分（第 3 段第 7 項）。
- INSERT 探測每個 plan 只嘗試一種填法；需要特定外鍵組合才能通過的政策仍可能是 inconclusive 或 denied（ADR-034 補記 2）。沒有 OpenAPI 的目標（L12、bundle 推測）沒有型別資訊，行為同 MS3。
- M4 是選配：未提供 DB 連線時不會有 SECURITY_DEFINER_EXECUTABLE 等警告。
- MS6 待辦（MS3 核准意見第 1 點，已記入 `docs/PLAN.md`）：L03 提權與 dev／ci 讀取植入串進 `run_scan`；遠端 dev／ci 的 `WriteRefused` 轉為 inconclusive 寫入 cell。
- L11（P2）沒有 storage 探測。
- blocked ticket：僅 T-071（MS1 遺留，已由 T-080 交付）。
