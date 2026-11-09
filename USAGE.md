# RLSentry 使用說明

RLSentry 從攻擊者的角度驗證 Supabase 專案的授權（RLS）：用 anon key 與兩個測試帳號，透過正常的 Supabase API 實際讀寫，證明「不該看到的資料看得到」，並附重現指令與修補 SQL。

> **只掃描你擁有或已取得書面授權的目標。** 未經授權的掃描可能觸犯刑法第 358–362 條（SPEC §7）。RLSentry 在送出任何請求前要求授權確認（設定檔 `authorized: true` 或 `--i-own-this-target`），且 Supabase API 位址必須由你明列（S4）。

本文件的每個 `<!-- doctest -->` 區塊都在本機 Supabase lab 實際執行過，`make acceptance` 會再執行一次。

## 1. 安裝

需求：Python 3.12 以上。在 repo 根目錄：

```bash
pip install -e ".[dev]"
rlsentry --help
```

只要使用掃描器（不跑測試與 lab）時，`pip install .` 即可。

### 本機 lab（執行下面的範例需要）

範例都對本機 lab 執行（`127.0.0.1`），不會連到任何外部網站。需要 Docker 與 Supabase CLI：

```bash
docker info >/dev/null 2>&1 || (sudo dockerd >/tmp/dockerd.log 2>&1 &); sleep 5; docker info >/dev/null && echo DOCKER_OK
python -m lab._shared up
```

`up` 印出 `http://127.0.0.1:54321` 表示 lab 已啟動。lab 的命令列入口（ADR-052）：

| 指令 | 作用 |
| --- | --- |
| `python -m lab._shared up` | 啟動 lab（已啟動則沿用），印出 API URL |
| `python -m lab._shared apply L04` | 載入情境（每次都從乾淨狀態重建） |
| `eval "$(python -m lab._shared env)"` | 設定 `RLSENTRY_ANON_KEY`、`RLSENTRY_DB_URL`、`RLS_A_PW`、`RLS_B_PW`（只有 lab 的值） |
| `python -m lab._shared serve L04 --port 8740` | 在 127.0.0.1 提供該情境的前端（給 M1 抓 bundle） |
| `python -m lab._shared sql` | 從 stdin 讀 SQL，以 postgres 在一個 transaction 中執行（展示修補用） |

## 2. 設定檔 `rlsentry.yaml`

範例：`docs/examples/rlsentry.dev.yaml`、`rlsentry.ci.yaml`、`rlsentry.audit.yaml`。密碼、key、DB URL **只寫環境變數的名稱**，值不進設定檔。

| 欄位 | 預設 | 說明 |
| --- | --- | --- |
| `target` | （必填） | 前端網址（`http://` 或 `https://`）。M1 只對與它同源的 URL 發 GET。 |
| `authorized` | `false` | 你確認擁有或已獲授權測試此目標。也可改用 CLI 的 `--i-own-this-target`。兩者都沒有 → exit 3，一個請求都不送。 |
| `profile` | `audit` | `dev`、`ci`、`audit`（見第 3 節）。CLI `--profile` 與設定檔不同時，**取較嚴者**（audit > ci > dev）。 |
| `supabase_url` | 無 | Supabase API 的 base URL（`scheme://host[:port]`，不可有 path、query、userinfo）。見下方 S4。 |
| `anon_key_env` | 無 | 存放 anon key 的環境變數名稱。ci 不跑 M1，必須提供；dev／audit 沒提供時用 bundle 中找到的 anon key。 |
| `db_url_env` | 無 | 存放 Postgres 連線字串的環境變數名稱；有值才執行 M4（splinter 交叉比對，**唯讀**）。 |
| `db_schemas` | `[public]` | PostgREST 曝露的 schema，傳給 M4（splinter、policy 讀取、交叉比對）；修補 SQL 使用第一個。 |
| `test_users` | `[]` | `user_a`、`user_b` 兩個測試帳號：`name`、`email`、`password_env`（密碼的環境變數名稱）。沒有測試帳號時只能測 anon。 |
| `rate_limit_rps` | `5` | 每秒請求數上限（並行數 4）。對正式環境請維持預設（NFR-04）。 |
| `fail_on` | `{evidence: confirmed, severity: high}` | **只在 ci 生效**：達到門檻的 finding 讓 exit code 為 1。 |
| `write_hosts` | `[]` | ci 可寫入的**遠端** preview DB 主機（完全比對，例如 `abcd.supabase.co`，不可有 scheme、path、萬用字元、預設 port）。localhost 不需列出。dev 只寫 localhost；audit 永遠不寫。 |
| `tables` | `{}` | 預期權限（expected policy）：每張表、view、RPC 一項，見下表。 |
| `defaults` | `{anon: deny, user: own_rows_only}` | 沒列在 `tables` 的表與操作的預設範圍。 |

`tables.<名稱>` 的欄位：`owner_column`（擁有者欄位）、`public_column`（公開旗標欄位）、`primary_key`（OpenAPI 不可用或 RPC 時指定識別欄位）、`select`／`insert`／`update`／`delete`（各自 `{anon: <範圍>, user: <範圍>}`）。範圍：`deny`、`all`、`own_rows_only`、`public_rows_only`、`public_or_own_rows`。

**`rlsentry init`** 讀目標的 OpenAPI（只發 GET），依欄位名稱（`user_id`、`owner_id`、`author_id`、`created_by`；`is_public`、`is_published`）產生 `tables:` 草稿；不會覆寫既有檔案，草稿需要你審閱：

<!-- doctest -->
```bash
python -m lab._shared apply L05
eval "$(python -m lab._shared env)"
rm -f /tmp/rlsentry.draft.yaml
rlsentry init --config docs/examples/rlsentry.ci.yaml --out /tmp/rlsentry.draft.yaml
grep -A2 '"projects":' /tmp/rlsentry.draft.yaml | grep -q 'owner_column: "owner_id"' && cat /tmp/rlsentry.draft.yaml
```

預期：`wrote /tmp/rlsentry.draft.yaml`，接著印出草稿：`"projects"` 的 `primary_key: ["id"]`、`owner_column: "owner_id"`，四種操作皆為 `{anon: deny, user: own_rows_only}`（`init` 只能依欄位名稱猜測，預期權限仍要由你確認）。

### S4：Supabase API 位址必須由你確認

前端 bundle 中的 Supabase URL 來自目標（不可信）。RLSentry **只**把請求送到設定檔的 `supabase_url` 或 CLI 的 `--supabase-url`（兩者都有但不同 → 拒絕）。兩者都沒有時以 exit 3 拒絕，訊息會列出 bundle 中找到的 URL，請確認後以 `--supabase-url <URL>` 重跑或寫進設定檔（ADR-043）。第 3.3 節的 audit 範例示範這個流程。

## 3. 三種 profile

| | dev | ci | audit |
| --- | --- | --- | --- |
| 用途 | 開發者對本機 lab | PR 時對 preview DB | 對已上線環境的唯讀稽核 |
| 模組 | M1–M5 | M2–M5（不掃前端） | M1–M3、M5；有 `db_url_env` 時加 M4（唯讀） |
| 寫入 | 只對 localhost：植入 canary、寫入探測、L03 提權（全部清理／還原） | 只對 localhost 與 `write_hosts` | **永遠不寫**（SafeClient 閘門拒絕；只送 GET／HEAD 與登入的 POST） |
| 失敗門檻 | 無（exit 0） | `fail_on`（預設 Confirmed 且 ≥ high → exit 1） | 無（exit 0） |
| 預設報告格式 | html | json、sarif | html、json |

### 3.1 dev（情境 L04：跨租戶讀取）

<!-- doctest -->
```bash
python -m lab._shared apply L04
eval "$(python -m lab._shared env)"
python -m lab._shared serve L04 --port 8740 > /dev/null &
sleep 1
rm -rf /tmp/rlsentry-dev
rlsentry scan --config docs/examples/rlsentry.dev.yaml --out /tmp/rlsentry-dev --format html,json; rc=$?
kill $!
test "$rc" -eq 0 && python3 -c "import json; r=json.load(open('/tmp/rlsentry-dev/rlsentry-report.json')); c=sorted((f['rule'], f['role'], f['severity'], f['correlation']) for f in r['findings'] if f['evidence'] == 'confirmed'); assert r['modules'] == ['M1', 'M2', 'M3', 'M4', 'M5'] and c == [('CROSS_TENANT_READ', 'user_a', 'medium', 'probe_only'), ('CROSS_TENANT_READ', 'user_b', 'medium', 'probe_only')], c; print('dev OK', c)"
```

預期輸出（節錄）：`Confirmed: 2 (2 medium)`、`MEDIUM CROSS_TENANT_READ notes user_a select`、`MEDIUM CROSS_TENANT_READ notes user_b select`，最後一行 `dev OK …`。dev 沒有失敗門檻，所以有漏洞時 exit code 仍是 0；用瀏覽器開 `/tmp/rlsentry-dev/rlsentry-report.html` 看完整報告。

### 3.2 ci（情境 L05：跨租戶寫入）

<!-- doctest -->
```bash
python -m lab._shared apply L05
eval "$(python -m lab._shared env)"
rm -rf /tmp/rlsentry-ci
rlsentry scan --config docs/examples/rlsentry.ci.yaml --out /tmp/rlsentry-ci; rc=$?
echo "exit=$rc"
test "$rc" -eq 1 && test -s /tmp/rlsentry-ci/rlsentry-report.sarif && python3 -c "import json; r=json.load(open('/tmp/rlsentry-ci/rlsentry-report.json')); c=sorted((f['rule'], f['role'], f['severity']) for f in r['findings'] if f['evidence'] == 'confirmed'); assert c == [('CROSS_TENANT_WRITE', 'user_a', 'high'), ('CROSS_TENANT_WRITE', 'user_b', 'high')], c; print('ci OK', c)"
```

預期：`Confirmed: 2 (2 high)`、`exit=1`（達到預設 `fail_on`），寫出 `rlsentry-report.json` 與 `rlsentry-report.sarif`，最後一行 `ci OK …`。寫入探測只動自己植入的 canary 列，結束前全部清理（ADR-029）。

### 3.3 audit（情境 L08：service_role key 在前端；含 S4 確認）

`rlsentry.audit.yaml` 沒有寫 `authorized` 與 `supabase_url`。第一次執行只給 `--i-own-this-target`，會因 S4 被拒（exit 3）；第二次加上 `--supabase-url` 確認：

<!-- doctest -->
```bash
python -m lab._shared apply L08
eval "$(python -m lab._shared env)"
python -m lab._shared serve L08 --port 8740 > /dev/null &
sleep 1
rm -rf /tmp/rlsentry-audit
rlsentry scan --config docs/examples/rlsentry.audit.yaml --out /tmp/rlsentry-audit --i-own-this-target; first=$?
rlsentry scan --config docs/examples/rlsentry.audit.yaml --out /tmp/rlsentry-audit --i-own-this-target --supabase-url http://127.0.0.1:54321; second=$?
kill $!
echo "first=$first second=$second"
test "$first" -eq 3 && test "$second" -eq 0 && python3 -c "import json; r=json.load(open('/tmp/rlsentry-audit/rlsentry-report.json')); c=[(f['rule'], f['target'], f['severity']) for f in r['findings'] if f['evidence'] == 'confirmed']; assert r['profile'] == 'audit' and c == [('SECRET_KEY_IN_BUNDLE', 'jwt:service_role', 'critical')], c; assert r['authorization']['supabase_url_method'] == 'cli_flag'; print('audit OK', c)"
```

預期：第一次印出拒絕訊息（含 bundle 中找到的 URL 與確認方式）；第二次 `Confirmed: 1 (1 critical)`、`CRITICAL SECRET_KEY_IN_BUNDLE jwt:service_role - -`；`first=3 second=0`。報告中的 key 一律遮罩（前 6 後 4）。audit 不植入、不寫入、不提權；它只能用目標既有的資料判定，所以很多格子會是 inconclusive（不代表安全）。

## 4. 展示情境：splinter 沒報，RLSentry 證實跨租戶讀取（L04）

L04 的 `notes` 表 SELECT policy 只檢查「已登入」（`auth.uid() IS NOT NULL`），沒檢查擁有者。splinter（Supabase 官方 linter）不會報這種問題，因為它不知道這張表「應該只屬於擁有者」（ADR-035）。完整流程：

<!-- doctest -->
```bash
python -m lab._shared apply L04
eval "$(python -m lab._shared env)"
python -m lab._shared serve L04 --port 8740 > /dev/null &
sleep 1
rm -rf /tmp/rlsentry-demo /tmp/rlsentry-demo-fixed
rlsentry scan --config docs/examples/rlsentry.dev.yaml --out /tmp/rlsentry-demo --format json
python3 -c "import json; f=[x for x in json.load(open('/tmp/rlsentry-demo/rlsentry-report.json'))['findings'] if x['rule'] == 'CROSS_TENANT_READ' and x['role'] == 'user_b'][0]; print('correlation:', f['correlation']); print(f['probes'][0]['reason']); print(f['repro']); print(f['fix_sql'])"
python3 -c "import json; c=sorted((x['rule'], x['role'], x['correlation']) for x in json.load(open('/tmp/rlsentry-demo/rlsentry-report.json'))['findings'] if x['evidence'] == 'confirmed'); assert c == [('CROSS_TENANT_READ', 'user_a', 'probe_only'), ('CROSS_TENANT_READ', 'user_b', 'probe_only')], c; print('before fix:', c)"; before=$?
python3 -c "import json; print(next(x['fix_sql'] for x in json.load(open('/tmp/rlsentry-demo/rlsentry-report.json'))['findings'] if x['rule'] == 'CROSS_TENANT_READ'))" | python -m lab._shared sql; fixed=$?
rlsentry scan --config docs/examples/rlsentry.dev.yaml --out /tmp/rlsentry-demo-fixed --format json
kill $!
test "$before" -eq 0 && test "$fixed" -eq 0 && python3 -c "import json; r=json.load(open('/tmp/rlsentry-demo-fixed/rlsentry-report.json')); c=[(f['rule'], f['target'], f['role']) for f in r['findings'] if f['evidence'] == 'confirmed']; assert c == [], c; print('demo OK: no confirmed finding after the fix')"
```

逐步說明：
1. **splinter 沒報**：dev 範例有 `db_url_env`，所以 M4 跑了 splinter；finding 的 `correlation: probe_only` 表示 splinter 對 `notes` 沒有任何 SECURITY 類 lint（`before fix:` 那一行斷言兩個 Confirmed 都是 probe_only）。
2. **Confirmed**：`reason` 寫出 user_b 以自己的登入看到了 user_a 的已知列（以主鍵計數，不下載資料內容）。
3. **重現指令**：`repro` 是可直接執行的 curl，`apikey` 與 `Authorization` 已遮罩（`eyJhbG****…`）；重現時換成你自己的 anon key 與 user_b 的 access token。
4. **修補 SQL**：DROP 過寬的 `notes_select`，建立 `auth.uid() = "owner_id"` 的 policy。RLSentry **絕不執行 SQL**；這裡由你（`lab._shared sql`）在 lab 中執行。
5. **修補後重掃**：沒有任何 Confirmed finding，最後一行 `demo OK: no confirmed finding after the fix`。

## 5. 報告與 exit code

`rlsentry scan --out <目錄> --format json,html,sarif` 寫出 `<目錄>/rlsentry-report.{json,html,sarif}`；不指定 `--format` 時依 profile 的預設（第 3 節表格）。終端機只印摘要（依證據等級計數，與每個 Confirmed finding 一行）。

- **證據等級**（與嚴重度獨立）：Confirmed（實際讀到不該讀的列、寫入後讀回證實、或 secret key 在前端）、Suspected（inconclusive 格子、只從 bundle 推測的目標）、Configuration warning（lint-only、SECURITY DEFINER 可執行但沒取得資料、無法辨識的 key）。報告依「證據等級 → 嚴重度」排序。
- **嚴重度**：Critical、High、Medium、Low、Review（SPEC §5 M5）。例外：M4 把 anon 經 SECURITY DEFINER RPC 的讀取改標為 `SECURITY_DEFINER_RPC_DATA` 時保留較高的嚴重度（anon 為 High，含敏感欄位為 Critical；使用者為 Medium），所以提供 DB 連線不會讓 ci 的結果改變（ADR-049）。
- 每個 finding 附：標題、證據等級、嚴重度、目標、身分、操作、證據（列數、狀態碼、遮罩後的 key）、`curl` 重現指令、修補 SQL、參考連結。報告中所有 key、JWT 與 URL 的 query string 都經遮罩；不含任何資料列的內容（只有計數與主鍵）。
- **HTML** 自包含（沒有 script、沒有外部資源，開啟不會連網；D3／ADR-050：沒有 Web 介面）。**SARIF 2.1.0** 的 location 指向設定檔（漏洞在資料庫，不在原始碼行）。

| exit code | 意義 |
| --- | --- |
| 0 | 完成（dev、audit 一律 0；ci 沒有達到 `fail_on`） |
| 1 | ci：有 finding 達到 `fail_on` |
| 2 | 設定錯誤或用法錯誤（設定檔格式、缺少環境變數、未知的 `--format`） |
| 3 | 拒絕執行：未授權、S4 端點未確認、寫入被安全閘門拒絕 |
| 4 | ci：寫入探測植入的 canary 無法清除（CLEANUP_FAILED），需要人工清理 |
| 5 | 掃描崩潰（網路、OS、執行期錯誤）；只印例外類別，不印內容 |

## 6. GitHub Action

`action/action.yml` 是 composite action：安裝 RLSentry、執行 `rlsentry scan --format json,sarif`、上傳 SARIF 到 code scanning。授權必須寫在設定檔（`authorized: true`），Action 不會代入 `--i-own-this-target`。

```yaml
jobs:
  rlsentry:
    runs-on: ubuntu-latest
    permissions: {contents: read, security-events: write}
    steps:
      - uses: actions/checkout@v4
      - uses: <owner>/rlsentry/action@<tag>
        with:
          config: rlsentry.yaml       # profile: ci；write_hosts 只列 preview DB
          profile: ci
        env:
          RLSENTRY_ANON_KEY: ${{ secrets.PREVIEW_ANON_KEY }}
          RLS_A_PW: ${{ secrets.RLS_A_PW }}
          RLS_B_PW: ${{ secrets.RLS_B_PW }}
```

請使用 `profile: ci` 的設定檔：較嚴者勝，`profile: audit` 的設定檔在 Action 中永遠不會失敗（ADR-051 #7）。輸入只經 `env:` 進入 shell，避免 script injection。

## 7. Python API

`from rlsentry import run_scan` 與 CLI、Action 是同一個入口（FR-16）：

<!-- doctest -->
```bash
python -m lab._shared apply L05
eval "$(python -m lab._shared env)"
python3 -c "import asyncio; from rlsentry import run_scan; from rlsentry.policy.load import load_config; cfg = load_config(open('docs/examples/rlsentry.ci.yaml').read()); rep = asyncio.run(run_scan(cfg, confirmed_by='usage-doctest')); got = (rep.profile.value, rep.modules, sorted({f.rule for f in rep.findings if f.evidence.value == 'confirmed'})); assert got == ('ci', ['M2', 'M3', 'M4', 'M5'], ['CROSS_TENANT_WRITE']), got; print(*got)"
```

預期（有斷言）：`ci ['M2', 'M3', 'M4', 'M5'] ['CROSS_TENANT_WRITE']`。`run_scan` 回傳 `ScanReport`（Pydantic），可用 `rlsentry.report.json.render_json` 等函式輸出。

## 8. 已知限制

- **結果只描述被測的範圍**：只測設定檔與 OpenAPI 列出的表、view、RPC；`inconclusive` 不代表安全。audit 沒有植入資料，只能用目標既有的列判定。
- **預期權限決定判定**：L04 型問題（只檢查已登入）只有在你寫明「這張表只屬於擁有者」時才會被判為漏洞。
- **M1**：不執行前端 JavaScript（D2，ADR-037）；只在執行期組出的 chunk、API 下發的 key 不會被找到。
- **修補 SQL 需要人工審閱**：一律使用 `db_schemas` 的第一個 schema；函式 DDL 不含參數簽章（多載函式會以錯誤失敗，不會改錯函式）；DROP POLICY 只刪可能授予該角色存取的 permissive policy（ADR-051）。
- **L03 提權**：只嘗試 `user_metadata.role = admin`；還原為原值，但原本沒有 role 的帳號還原後是 `role: null`。還原失敗時報告 notes 會要求人工清除。
- **報告的 curl 含主鍵值**（重現需要）；以 email 等個資當主鍵的表會在報告中出現該值。
- **Storage**：沒有 bucket 探測（L11，P2）。
- **Firebase**：不支援（D4，ADR-013）。
- **Benchmark**：指標只描述本 repo 的 16 個 lab 情境，不推論到所有 Supabase 專案（見 `BENCHMARK_REPORT.md`）。
