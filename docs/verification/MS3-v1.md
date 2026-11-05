# MS3 驗證清單 v1（main @ 24b347327）

## 1. 本模組做了什麼
- M3 寫入探測（FR-09）：dev／ci 才寫入，audit 一律唯讀（NFR-01）。流程：seed work row → plan_writes → send_write → read_back → write_cell → cleanup_seeded。
- ticket：21 張全部 done（T-120–T-140，T-131–T-140 多為過程中自我發現的修訂／稽核修正）。
  - 核准意見處理：T-120（第 1、2、4、6 點寫成 ADR-025–028，並更新 verification_steps.html）、T-121／T-122（第 5 點：fcntl 延遲 import、分類測試移出 tests/lab/→tests/labctl/）。
  - 寫入：T-123 合約（ADR-029）、T-124 可見測試、T-125 lab 整合＋變異＋holdout、T-126 seed、T-127 write、T-128 verdict/diff/cleanup/rules、T-129 metadata、T-130 run.py 串接。
  - 過程修訂（實測／稽核驅動）：T-131（test_import 子行程，修 flock 死鎖）、T-132（每探測各自 work row）、T-133（plan_writes 傳欄位名）、T-134（快速 fake 測試 test_run_writes）、T-135＋T-137（write_cell 依 HTTP 狀態分類）、T-136／T-138（誠實化 lab 斷言、清理去重）、T-139（寫入只對 table；變異改 disable RLS）、T-140（稽核 P1：NFR-01 流量證據）。
  - 攻擊次數＞1：T-121（2）、T-135（2，第一次誤改 regression 測試）。其餘皆 1 次。blocked：僅 T-071（MS1 遺留，已由 T-080 交付）。
- ADR：025（清單標籤＋Codespaces 準備）、026（必做／選做變異分級，簽章前提）、027（worktree：origin/main 必須是 HEAD 祖先）、028（verification_steps.html 維護）、029（寫入探測設計）＋補記（work row、text_column、狀態分類、清理全涵蓋、讀取植入／L03 延後、只對 table、去重）。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS3 --no-vc`：**ALL PASSED**（tests、holdout 5、safety、provenance、ruff、mypy 皆過；mutation 需 MUTATION=1 才跑）。
- lab：test_scan_writes 15 情境、test_write_mutations 2、test_scan_reads 15 全綠。
- auditor（base bd79ce0）：無 P0；P1 ×1（NFR-01 DB log 流量證據缺失）已由 T-140 補上；P2 見第 5 段。詳見 docs/verification/traceability.md 的 MS3 段。

## 3. 請你親手驗證（逐項打勾）
**Codespaces 準備（ADR-025；完整指令見 `docs/verification_steps.html` 步驟 4.5）**：在 `claude/busy-darwin-asvox3` 開 Codespace，依序執行：
```
pip install -e ".[dev]"
curl -fsSL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.tar.gz | sudo tar -xz -C /usr/local/bin supabase
docker info >/dev/null 2>&1 || (sudo dockerd >/tmp/dockerd.log 2>&1 &); sleep 5; docker info >/dev/null 2>&1 && echo DOCKER_OK
python3 -c "from lab._shared import labctl; print(labctl.ensure_up().api_url)"   # 第一次拉映像約數分鐘，預期印出 http://127.0.0.1:54321
```
確認 `git rev-parse HEAD` 等於本機 sha（不一致時 `git diff --stat <本機 sha> HEAD -- . ':!logs'` 須為空）。測完一律 `git restore .`、不提交、不推送，刪除 Codespace。

- [ ] 【本機】＋【Actions 涵蓋】在容器內執行 `make verify-milestone MS=MS3`，依 ADR-022 三段信任鏈：(a) 本機 `host/review.sh` 第 1、2 步（同步＋防竄改，須 `✓ no changes to frozen files`）；(b) Actions `verify-milestone` ref=claude/busy-darwin-asvox3（最後一行 `MS3: ALL PASSED`，Actions 只證明通過不顯示細節）；(c) `git diff --stat <本機 sha> <Actions sha> -- . ':!logs'` 無輸出。
- [ ] 【Codespaces 必做變異】**（簽章前提，ADR-026）** 把 `rlsentry/probe/verdict.py:103` 的 `Outcome.INCONCLUSIVE` 改成 `Outcome.DENIED`，執行 `python3 -m pytest -q tests/probe/test_write_status.py`。預期 `test_non_auth_failure_is_inconclusive_never_denied` 失敗。意義：INSERT 因非授權原因（如 400 NOT NULL）失敗時，若被判 denied 等於把「其實可能不安全」說成安全；此變異證明該防線有效。完成後 `git restore rlsentry/probe/verdict.py`。
- [ ] 【Codespaces 必做】`python3 -m pytest -q tests/probe/test_write_verdict.py tests/probe/test_write_status.py`。預期全綠：401／403→denied、2xx→依讀回（2xx 無效果→denied）、其餘狀態／無回應→inconclusive。
- [ ] 【Codespaces 必做】（需 Docker）`python3 -m pytest -q tests/lab/test_scan_writes.py`。預期 `15 passed`。這驗證真實 lab 上：脆弱寫入被 confirmed、安全 cell 無誤報、清理完整、且 NFR-01 流量證據（`traffic_problems`：seed.sql 既有列未變、PostgREST 寫入只有 INSERT／UPDATE／DELETE）。
- [ ] 【Codespaces 必做變異】（需 Docker，共模變異）`python3 -m pytest -q tests/lab/test_write_mutations.py`。預期 `2 passed`：C01 todos 在 `disable row level security` 後，掃描器把原本 denied 的 cell 翻成 confirmed CROSS_TENANT_WRITE／ANON_WRITE（讀回驗證）。先看它綠，再想：若掃描器寫入判定被弱化，這兩個會變紅。
- [ ] 【Codespaces 必做】`python3 -m pytest -q tests/probe/test_run_writes.py`（stateful fake，免 Docker）。預期全綠：seed→write→read_back→verdict→cleanup 編排；含「INSERT 回 400→inconclusive 非 denied」與「無法刪除→每位擁有者一筆 CLEANUP_FAILED」。
- [ ] 【Codespaces 必做】確認無 canary 殘留。清理由 `tests/lab/test_scan_writes.py` 的 `cleanup_problems`／`traffic_problems` 斷言（每個殘留 canary 必對應一筆 CLEANUP_FAILED、seed.sql 既有列未被更動）——先讀這兩個函式確認邏輯。要親手查，在 repo 根目錄貼下面這**一行**（用 repo 既有、唯讀的 `labctl.query`，掃所有 public 文字欄位找 `rlsentry_canary_` 前綴；勿用多行 heredoc，貼進去會卡在續行）：
      `python3 -c "from lab._shared import labctl; cols=labctl.query(\"select table_name,column_name from information_schema.columns where table_schema='public' and data_type in ('text','character varying')\"); print('residue:', [(t,c,n) for t,c in cols for (n,) in [labctl.query(f\"select count(*) from public.{t} where {c} like 'rlsentry_canary_%'\")[0]] if n!='0'] or 'none')"`
      預期印出 `residue: none`。注意 `test_scan_writes` 在每個情境後會 `labctl.apply` 還原，所以 `pytest` 跑完後資料庫是乾淨狀態（本查詢回 none）；清理行為本身由上述斷言把關。（自我驗證：先 `docker exec -i supabase_db_rlsentry-lab psql -U postgres -c "insert into public.todos(id,owner_id,title) values (gen_random_uuid(),'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','rlsentry_canary_demo')"`，再跑上面那行會印出 `residue: [('todos', 'title', '1')]`，然後 `delete` 還原。）
- [ ] 【本機】閱讀 `rlsentry/probe/verdict.py:95-111`（write_cell）。確認：plan None→not_tested；401／403→denied；非 2xx 其他→inconclusive；2xx 依 read_back（無效果→denied）。沒有任何路徑把送不出的寫入當成安全。
- [ ] 【本機】閱讀 `rlsentry/probe/run.py` 的寫入段。確認：只對 `kind=="table"` 跑寫入；audit 整段跳過（AUDIT_WRITE_REASON）；每個 work row 與 2xx INSERT canary 都收集後交 `cleanup_seeded`。
- [ ] 【本機】閱讀 `tests/lab/test_scan_writes.py` 的 `judge`／`cleanup_problems`／`traffic_problems`。確認：不可植入的脆弱寫入（L01／L05）記為限制而非漏抓；殘留 canary 必對應 CLEANUP_FAILED；真實列未變。
- [ ] 【Actions 涵蓋】holdout：`git show origin/rlsentry-holdout:MS3/test_holdout_writes.py | sha256sum`。預期 `94680aedc763b81d32b3c3c9683a2207aa1fdcbd9178fccc7d627c68d9a9c824`（與 PRODUCTION_LOG 派工前紀錄相同；Actions 已跑過它）。
- [ ] 【本機】打開 `docs/reviews/MS3-high-risk.md`，依逐張（T-126–T-130、T-137）與抽查（合約）清單，以各 accept commit 看 diff。
- [ ] 【本機】打開 `docs/system_overview.html`：確認「MS3」一節與架構圖 M3 方塊狀態（讀取＋寫入皆完成）與實際一致（ADR-021）。
- [ ] 【本機】打開 `docs/verification_steps.html`：確認 Codespaces 準備、四種標籤與必做變異簽章前提（ADR-025／026／028）與本清單一致。
- [ ] 【本機】**做出決定**：接受第 5 段的延後項（L03 提權與 dev／ci 讀取植入延到 MS6；L01／L05 不可植入；遠端 dev／ci 寫入會 fail-loud）與 P2，或在核准意見中要求改。

## 4. 與 SPEC 的偏差與假設
- **§5 M3「dev／ci 探測前植入已知資料」（讀取）**：MS3 的 `probe()` 不呼叫 `seed_known_rows`，讀取沿用 MS2 的 collect_known_rows（既有列）；dev 的 C04 仍為 inconclusive。seed_known_rows 已實作並單元測試，延到 MS6 pipeline 串接（ADR-029 補記 2）。
- **L03 `USER_METADATA_ESCALATION`**：提權後需以密碼重新登入取得新 JWT，`probe()` 只收到 token（不含密碼，NFR-03）。metadata.py 已實作並單元測試，延到 MS6 串接。本 milestone 不產生此 finding。
- **寫入只對 kind=="table"**：RPC／view 的寫入 cell 一律 NOT_TESTED（ADR-029 補記 T-139）。
- **讀回判定以 HTTP 狀態分類**：401／403 才算 denied；400／409／5xx／無回應一律 inconclusive（ADR-029 補記 2），避免把「掃描器自己送不出有效寫入」誤判為安全。
- **NFR-01 證據**：audit 0 寫入由 test_scan_reads（DB log）驗證；dev 的「真實列未變、寫入只及 canary」由 test_scan_writes 直接讀 DB 驗證（DbWrite 只留 role＋command，不留值，故 auth 登入寫入以角色無法與資料寫入區分，canary-only 的保證靠 seed 列快照＋cleanup）。

## 5. 已知限制
- **L01／L05 寫入不可植入**：`customers.email`（text NOT NULL）、`projects.created_by`（uuid NOT NULL）等欄位掃描器無法在不知型別下填值 → 該寫入 cell 為 not_tested／inconclusive（保守、不誤報）。完整覆蓋需由 OpenAPI 取得欄位型別，列為未來工作（ADR-029 補記 2）。
- **lab 真實脆弱寫入的正向路徑**：因 L01／L05 不可植入，真實 lab 上「確實寫入成功→confirmed」主要由 test_write_mutations（C01 disable RLS）與可自然植入的脆弱 dev case 覆蓋；offline 由 test_run_writes 完整覆蓋（auditor P2）。
- **遠端 dev／ci 目標**：對非 localhost 送寫入時 `WriteRefused` 會直接中止 `probe()`（fail-loud，不會寫入），尚未轉成 inconclusive cell；MS3 範圍為本機 lab（auditor P2）。
- **CLEANUP_FAILED 去重**：以 (target, owner) 去重，報告不含殘留列數；實際殘留列在 dev／ci 可丟棄 DB（ADR-029 補記 T-138）。L09 feedback（無 owner DELETE policy）掃描後會留下 canary 並回報 CLEANUP_FAILED，屬正確行為。
- **permissive `to anon` policy**：本 lab 中以新增 permissive policy 讓 anon 寫入不生效（anon DELETE 仍影響 0 列，role 對應細節），故變異測試改用 `disable row level security`（ADR-029 補記 T-139）。
- **blocked ticket**：僅 T-071（MS1 遺留，已由 T-080 交付）。
