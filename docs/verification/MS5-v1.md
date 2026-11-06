# MS5 驗證清單 v1（main @ 5a41a7327）

## 1. 本模組做了什麼
- **M1 Recon（FR-01–03、NFR-03）**：`rlsentry/recon/`（fetch、links、sourcemap、extract、classify、run）。從目標網址只送同源 GET（不帶任何 header）：HTML 的 `<script src>`／`modulepreload` → JS 內的 chunk 路徑（Vite `import()`、Next.js `_buildManifest`）→ `sourceMappingURL` 指向的 map → webpack chunk map（CRA）與 `.e(id)`（Next.js）。擷取 JWT（不驗簽，只留 role／ref／exp）、`sb_publishable_`／`sb_secret_`、key 語境中的高 entropy 字串。**service_role／sb_secret → SECRET_KEY_IN_BUNDLE（Critical）；anon／publishable 不產生 finding**；其他 → UNVERIFIED_KEY（Configuration warning）。報告只有前 6 後 4 遮罩值，報告中所有 URL 經 `report_url`（省略 query string、移除 userinfo、再遮罩）。
- **真實框架 fixture**（SPEC §9 測試層級）：Next.js 15.5、Vite 8、CRA 5 以 supabase-js 2.119 實際建置，`tests/recon/fixtures/`（建置方式與預期結果見該目錄 README）。
- **Benchmark**：bench 每個情境先以 recon 掃描 `labctl.serve_frontend` 在 127.0.0.1 提供的前端；M2 改用 recon 實際抓到的 bundle；key finding 不經 M4 correlate。recall **30/32**（L08-V1 轉為 TP；MS4 為 29/32）、precision 30/30、FPR 0/72、probe-only 仍 2 類；audit 16 個情境 DB 寫入皆 0。原始 JSON：`docs/benchmark/MS5-bench.json`。
- **MS4 核准意見**：第 1、2、3、5 點記入 `docs/PLAN.md`（MS6 表：稽核 P2 (a)–(d) 各自註明要以測試證明、L04 重現指令與修補 SQL、主鍵合併為單一請求並重量 5／20／50 張表且不調高 rps；MS7：重跑完整 benchmark 並更新原始數量）。第 4、6、7 點無需動作。
- ticket：14 張全部 done（T-180–T-193）。嘗試次數 > 1：T-188（3 次；第 1、2 次失敗都與 T-188 無關：容器重啟留下未完成的試合併、重啟後 lab 統計被重設，見第 5 段與 PRODUCTION_LOG）。blocked：僅 T-071（MS1 遺留，已由 T-080 交付）。
  - 稽核修正：T-192／T-193（P1 S1：報告 URL 遮罩；S2、S3、S6）。T-191 只改測試 docstring 的 ticket 編號。
- ADR：036（M1 設計：同源、範圍上限、擷取與分類、標籤、M1 finding 不經 correlate）＋補記（report_url、userinfo、KeyFinding 一致性）、**037（D2：不支援無頭瀏覽器）**。

## 2. 自動驗收結果（僅供參考，你仍須親自執行第 3 段第一項）
- `python3 harness/acceptance.py --milestone MS5 --no-vc`：**MS5: ALL PASSED**（tickets、provenance、ruff、mypy、tests、holdout 8、safety、checklist sync；mutation 需 MUTATION=1）。
- auditor（base 93e03445d）：P0 無；**P1 ×1（S1：同源回 200 的 URL 原樣進入 `chunks_scanned`／`source_file`）已由 T-192／T-193 修正**；P2 S2、S3、S6 一併修正；S4 排進 MS6（PLAN）；其餘 P2 見第 5 段。auditor 違反派工指示跑了完整測試（含 lab，1051 passed），恰與 architect 的第一次 benchmark 同時執行，該次 benchmark 已作廢並在最終程式碼上重跑。詳見 `docs/verification/traceability.md` 的 MS5 段。
- 派工前參考實測（草稿程式，未提交）：可見測試與 holdout 在派工前就全部可通過；抓到 2 個問題（測試的 SPA 頁缺 doctype、合約的 key 語境漏了 `supabaseKey`）。

## 3. 請你親手驗證（逐項打勾）
每一條指令都放在獨立的 code block 中（按右上角 Copy 即可貼上執行），都是單行，都在 lab 實跑過（ADR-030 與補記）。審查流程沒有改變，`docs/verification_steps.html` 本次未更新。

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
最後一行預期印出 `http://127.0.0.1:54321`（第一次拉映像約數分鐘）。MS5 沒有新增相依套件。確認 Codespace 的 sha 等於本機驗證的 sha：
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

- [ ] 【本機】＋【Actions 涵蓋】在容器內執行 `make verify-milestone MS=MS5`。依 ADR-022 三段信任鏈：(a) 本機 `host/review.sh` 第 1、2 步（同步＋防竄改，須看到 `✓ no changes to frozen files`）；(b) GitHub Actions `verify-milestone`，ref=`claude/busy-darwin-asvox3`，最後一行 `MS5: ALL PASSED`（Actions 只證明通過，不顯示細節）；(c) 兩個 sha 的差異排除 logs/ 後為空。容器內的指令：
  ```bash
  make verify-milestone MS=MS5
  ```
  (c) 的比對（把兩個 sha 填入後執行，預期沒有輸出）：
  ```bash
  LOCAL=請貼上本機sha; ACTIONS=請貼上Actions的sha; git diff --stat $LOCAL $ACTIONS -- . ':!logs'
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提，ADR-026）service_role 一定要被報告**。把 `rlsentry/recon/classify.py:80` 的「略過 publishable」改成「略過 secret」：
  ```bash
  sed -i '80s/k.kind == "publishable" or /k.kind == "secret" or /' rlsentry/recon/classify.py && python3 -m pytest -q tests/recon/test_classify.py tests/recon/test_recon_fixtures.py
  ```
  預期：`5 failed, 26 passed`，失敗的是 `test_findings_service_role_is_critical_anon_is_silent`、`test_findings_only_publishable_gives_nothing` 與三個框架的 `test_framework_keys_url_and_findings[nextjs|vite|cra]`。意義：bundle 裡的 service_role key 被靜默略過＝把 Critical 說成安全（MS5 焦點）。還原：
  ```bash
  git restore rlsentry/recon/classify.py
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提）anon key 不得被報告為漏洞**。拿掉同一行的「略過 publishable」：
  ```bash
  sed -i '80s/k.kind == "publishable" or //' rlsentry/recon/classify.py && python3 -m pytest -q tests/recon/test_classify.py tests/recon/test_lab_frontends.py
  ```
  預期：`18 failed, 19 passed`（兩個 classify 測試，加上 16 個 lab 前端全部失敗：每個前端的 anon key 都變成 finding）。不需 Docker：前端由 127.0.0.1 上的靜態伺服器提供。還原：
  ```bash
  git restore rlsentry/recon/classify.py
  ```
- [ ] 【Codespaces 必做變異】**（簽章前提）報告中的 URL 必須遮罩**（稽核 P1 S1 的修正）。讓 `rlsentry/recon/links.py:66` 的 `report_url` 原樣回傳：
  ```bash
  sed -i '66s/return mask_text(base + hash_sep + fragment)/return url/' rlsentry/recon/links.py && python3 -m pytest -q tests/recon/test_report_urls.py tests/recon/test_recon_masking.py
  ```
  預期：`3 failed, 5 passed`，失敗的是 `test_report_url_forms`、`test_scanned_urls_and_sources_are_masked`、`test_skipped_url_with_token_is_masked`。意義：query string 或 source map 名稱中的 key 會原樣出現在報告（NFR-03）。還原：
  ```bash
  git restore rlsentry/recon/links.py
  ```
- [ ] 【Codespaces 必做變異】**只抓同源**。拿掉 `rlsentry/recon/fetch.py:76` 的同源檢查：
  ```bash
  sed -i '76s/if not same_origin(url, target_url):/if False:/' rlsentry/recon/fetch.py && python3 -m pytest -q tests/recon/test_fetch.py
  ```
  預期：`1 failed, 9 passed`，失敗的是 `test_crawl_order_and_scope`（CDN 與其他主機被請求）。意義：recon 會連到授權範圍外的主機（CLAUDE.md、SPEC §7）。還原：
  ```bash
  git restore rlsentry/recon/fetch.py
  ```
- [ ] 【Codespaces 必做變異】（需 Docker）**key finding 不得經過 M4 correlate**。讓 `rlsentry/bench/run.py:73` 把 recon 的 finding 也交給 correlate：
  ```bash
  sed -i '73s/probe_findings = correlate(probe_findings, lints)/probe_findings = correlate(probe_findings + rec_findings, lints); rec_findings = []/' rlsentry/bench/run.py && python3 -m pytest -q tests/lab/test_bench_recon.py::test_l08_key_is_scored
  ```
  預期：`1 failed`，訊息含 `['L08-V1'] == []`。意義：L08 會被算成第 3 類 probe-only（灌水；key 不在 splinter 的範圍內，ADR-036 #7）。還原：
  ```bash
  git restore rlsentry/bench/run.py
  ```
- [ ] 【Codespaces 必做】不需 Docker 的 MS5 測試（含三個真實框架 fixture 與 16 個 lab 前端）：
  ```bash
  python3 -m pytest -q tests/recon tests/labctl/test_serve_frontend.py
  ```
  預期：`92 passed`。
- [ ] 【Codespaces 必做】auditor 的親手檢查 1（S1 修正）：同源、回 200、query 帶 sb_secret 的 script：
  ```bash
  python3 -c "from tests.fakes import Recorder, run; from tests.recon.helpers import ORIGIN, SB_SECRET, StaticSite; from rlsentry.recon.run import recon; u=ORIGIN+'/a.js?k='+SB_SECRET; s=StaticSite(None, extra={ORIGIN+'/':(200,'<script src=\"/a.js?k='+SB_SECRET+'\"></script>',{}), u:(200,'x()',{})}); o=run(lambda c: recon(c, ORIGIN+'/'), Recorder(s)); print(SB_SECRET in o.result.model_dump_json(), o.result.chunks_scanned)"
  ```
  預期：`False ['http://fixture.test/', 'http://fixture.test/a.js?…']`（稽核時為 `True`）。
- [ ] 【Codespaces 必做】（需 Docker）L08 在 dev 與 audit。先執行：
  ```bash
  python3 -m rlsentry.bench --scenario L08 --json /tmp/l08.json
  ```
  預期結尾 `tp 1  fn 0  fp 0  tn 3  fp_safe 0`。再執行：
  ```bash
  python3 -c "import json; r=json.load(open('/tmp/l08.json')); print([(s['profile'], s['db_writes'], {c['case_id']: c['verdict'] for c in s['cases']}, s['probe_only']) for s in r['scenarios']])"
  ```
  預期：`[('dev', 27, {'L08-V1': 'tp', 'L08-S1': 'tn', 'L08-S2': 'tn', 'L08-S3': 'tn'}, []), ('audit', 0, {'L08-V1': 'tp', 'L08-S1': 'tn', 'L08-S2': 'tn', 'L08-S3': 'tn'}, [])]`。意義：service_role 為 TP、anon key 為 TN（S1）、audit 0 次寫入、L08 不在 probe-only。（dev 的 27 是 M3 寫入探測植入／清理 canary 的寫入，只在 dev。）
- [ ] 【Codespaces 必做】（需 Docker）bench 接線與 L12（M2 改用 recon 抓到的 bundle 後仍找得到只在 bundle 中出現的表）：
  ```bash
  python3 -m pytest -q tests/lab/test_bench_recon.py
  ```
  預期：`2 passed`。
- [ ] 【Actions 涵蓋】holdout 與派工前紀錄一致：
  ```bash
  git fetch -q origin rlsentry-holdout && git show origin/rlsentry-holdout:MS5/test_holdout_recon.py | sha256sum
  ```
  預期 `6babb1ec8849f28cfa9ed27c82b09e6ef4c4274a62c6c1a8f1b75207f1a1ebd5  -`（PRODUCTION_LOG 記錄的 hash）。
- [ ] 【本機】閱讀 `rlsentry/recon/classify.py:46-87`（分類與 finding）、`rlsentry/recon/fetch.py:31-112`（只 GET、無 header、同源先於上限與請求）、`rlsentry/recon/links.py:40-66`（同源、userinfo、report_url）、`rlsentry/bench/run.py:41-75`（auditor 親手檢查 2：`start = time.monotonic()` 在 `serve_frontend` 區塊之後；correlate 只收 probe findings，`rec_findings` 在 `score_scenario` 才加入）。
- [ ] 【本機】打開 `docs/reviews/MS5-high-risk.md`，依逐張（T-186、T-182、T-183、T-187、T-193、T-189）與抽查清單，以各 accept commit 看 diff；再抽看 `tests/recon/fixtures/README.md` 與 `_sources/` 確認 fixture 是真實建置。
- [ ] 【本機】文件同步（ADR-021、ADR-028、ADR-031）。執行下面這條，預期沒有輸出：
  ```bash
  python3 docs/tools/progress.py && git diff --stat docs/progress.html docs/branch-log.md
  ```
  再打開 `docs/system_overview.html`，確認架構圖 M1 方塊為完成、第 7 節 MS4 為「已核准」、MS5 為「等待你審查」、第 8 節有 MS5 段落、第 9 節第 6 列是 S4 風險。
- [ ] 【本機】**做出決定**：閱讀 ADR-036、ADR-037 與 `BENCHMARK_REPORT.md` 第 1、2、2b 節。接受或要求修改：(a) **D2：不支援無頭瀏覽器**（ADR-037）；(b) **不盲猜 `<url>.map`**，只依註解或 header 抓 map（ADR-036 #2；auditor 親手檢查 3：與 SPEC §5 M1「存在 .map 時一併解析」的字面不同）；(c) 只抓同源、報告 URL 省略 query string；(d) `authenticated`／`supabase_admin` 等其他 role 的 JWT 只列 unverified（Low）；(e) recall 30/32，2 個 FN 是 L03（MS6）；(f) 第 5 段的 P2 與環境發現。

## 4. 與 SPEC 的偏差與假設
- **§5 M1 第 2 步「存在 .map 時一併解析」**：只解析 `sourceMappingURL` 註解或 `SourceMap`／`X-SourceMap` header 指向的 map，不對每個 chunk 盲猜 `<url>.map`（ADR-036 #2）。
- **§12 D2**：不支援無頭瀏覽器（ADR-037）。只在執行期組出的 chunk URL、由 API 下發的 key 不會被掃到；報告以 `chunks_scanned`／`chunks_skipped` 揭露範圍。
- **抓取範圍**：SPEC 沒有規定，決定只抓與 target 同源的 URL，且不帶任何 header（ADR-036 #1）。
- **§6 資料模型的增補**（ADR-036）：`KeyFinding.label`（＋kind／label 一致與遮罩 validator）、`ReconResult.chunks_skipped`；`Recon` 介面改為 `recon(client, target_url) -> ReconOutput`（ADR-023 的 SafeClient 慣例）。
- **FR-03 分類**：只有 `role=anon` 為 publishable、`role=service_role` 為 secret；其他 role 一律 unverified（含 `supabase_admin` 這種高權限 role，人工確認時應視為嚴重）。
- **報告中的 URL 省略 query string**（ADR-036 補記）：query string 是 token 最常出現的位置，不論格式都不寫出。
- **整合改動 MS4 的 `bench/run.py`**：加入 M1（recon 不計時、key finding 不經 correlate）。這是接上 M1 的必要步驟，不是 MS4 的缺陷；MS4 的計分與 correlate 對 MS4 輸入的行為不變（已由 MS4 的回歸測試確認）。
- **§9 Recall 目標仍未達**：30/32（L03 ×2 延後 MS6）。**Runtime 目標未達**：與 MS4 相同（MS5 未改 M2／M3；改善排在 MS6／MS7，PLAN）。

## 5. 已知限制
- 稽核 P2：S4 `supabase_url`／`anon_key` 來自目標 bundle，MS6 pipeline 送請求前必須經設定檔或使用者確認（已記入 PLAN 的 MS6 表）；S5 大檔先完整下載才檢查大小（最壞 200 × 10 MB），重疊檢查為 O(literals × spans)；generic key 偵測依 key 語境名稱，壓縮成無意義名稱時會漏；`supabase_url = None`（URL 在執行期組出）沒有測試覆蓋；sb_secret 的端到端只有單元測試；fetch 的 cookie 檢查為空轉（假網站不送 Set-Cookie，但 SafeClient 本身拒收 cookie 已在 MS1 測過）；serve_frontend 的「只允許 GET／HEAD」與 bench 的「runtime_s 只計 M2＋M3」沒有專屬測試（程式正確，見第 3 段閱讀項）。
- M1 只有 L08 一個計分漏洞案例，統計意義低；主要證據是三個真實框架 fixture 與 holdout。ENTROPY_MIN 4.0 依 fixture 量測。16 個 lab 前端形狀相同（`index.html`＋`assets/app.js`）。
- **環境發現（MS4 測試）**：容器被強制終止後，Postgres 的 crash recovery 會重設統計，`_realtime.extensions` 的索引 idx_scan 變 0，splinter 的 PERFORMANCE lint `unused_index` 出現在非 public schema，使 `tests/lab/test_whitebox_lab.py::test_l01_rls_disabled_is_reported`（斷言所有 lint 都在 public）失敗。乾淨啟動的 lab（Codespaces、Actions）不受影響；`supabase stop --no-backup`（在 `lab/_shared`）後重啟即恢復。未修改已核准的 MS4 測試；若你認為應放寬為只檢查 SECURITY 類 lint，請在核准意見中指示（會以 reopen 方式處理）。
- 過程紀錄：容器重啟留下未完成的試合併（以 harness 的 accept 路徑清除）；architect 一次 `commit -a` 誤把 harness 的紀錄檔帶進 `arch/T-191`（該分支未合併，改以只含測試檔的 `arch/T-191b` 驗收；`logs/events.jsonl` 少了 5 行 start 事件，原文保留在 `arch/T-191` 的 commit 中）。詳見 PRODUCTION_LOG。
- MS6 待辦（PLAN）：L03 提權與 dev／ci 讀取植入串進 `run_scan`；遠端 `WriteRefused` → inconclusive；稽核 P2 (a)–(d)；L04 報告重現指令與修補 SQL；主鍵合併為單一請求並重量 runtime；S4 URL 確認。
- L11（P2）沒有 storage 探測。
- blocked ticket：僅 T-071（MS1 遺留，已由 T-080 交付）。
