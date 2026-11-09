# RLSentry 上線前優化清單（v2：已併入 architect 回覆 001／002；GI = docs/reviews/global-issues.md）

| # | 優先 | 項目 | 影響 | 成本 | 證據 | 驗收 |
|---|---|---|---|---|---|---|
| I-01 | P0 | ci fail-open：Supabase 不通／登入全失敗／0 target 皆 exit 0 | CI 永遠綠燈、授權回歸無人察覺 | S | blind.html 2.4；exit_code.py:15-25 | 三種情況各一個 e2e，exit ≠ 0（新 code 5） |
| I-02 | P0 | `--profile ci` 被設定檔預設 audit 靜默覆蓋 | Action 使用者最常見配置 exit 0 | S | pipeline.py:48-54；policy.py:110 | CLI/設定不一致時印警告；Action 驗證實際 profile |
| I-03 | P0 | FR-05 覆蓋率與「未發現不代表安全」聲明未實作 | SPEC P1 需求缺漏、誤導「0 finding = 安全」 | S | traceability.md:56；L11 報告 grep=0 | 報告含 coverage 區塊；L11 顯示 Storage 未涵蓋 |
| I-04 | P1 | Benchmark 只量 dev＋ground-truth policy；真實路徑 recall 27/32 | 對外指標過度樂觀 | S（文件）/M（量測） | bench/run.py:30-44；本審核重跑 | BENCHMARK_REPORT 增「init 草稿＋ci」「audit」兩欄 |
| I-05 | P1 | ci 不跑 M1 → service_role 外洩 CI 抓不到 | 最嚴重規則在 CI 缺席 | S | L08 ci 無 finding | ci 有可達 target 時跑唯讀 M1；L08 ci exit 1 |
| I-06a | P1 | INSERT 探測不帶 canary（write.py:62-64 不傳 text_column）→ 3 列無法辨識 | 殘留無法追蹤 | S | L09 3 列 body IS NULL（GI-09） | L09 殘留列 100% 帶 canary |
| I-06b | P1 | SPEC §5 M3 lab DB 代清未實作；CLEANUP_FAILED 無殘留主鍵；exit 4 被 exit 1 遮蓋 | preview DB 累積垃圾資料 | M | L09 每次 +13 列；cleanup.py 無 DB 路徑（GI-10） | 有 db_url 時列數回到 2；報告列 pk 與 DELETE 範本 |
| I-07 | P1 | L09 同 id CLEANUP_FAILED ×2（讀取植入清理＋寫入探測清理各一）；L07 SECURITY_DEFINER role=None/anon 為語意重複（id 不同） | SARIF 指紋、計數錯誤 | S | L09/L07 JSON（GI-11） | id 唯一性斷言 |
| I-08 | P1 | init 可用性：錯誤訊息提 TARGET、需 anon_key_env、草稿缺必要欄位、RPC 無 primary_key | 新使用者首次設定 ~50 次試誤 | M | blind.html 2.1 | init 產出可直接 scan 的完整檔 |
| I-09 | P1 | CROSS_TENANT_READ 對敏感欄位不升級；L04 展示情境在 ci exit 0 | 主打賣點在 CI 不擋 | S | rules/severity.py:25-30 | 決策 ADR＋測試 |
| I-10 | P1 | 發佈要件：LICENSE、README、版本號、--version、PyPI、產品 CI、Action SHA pin | 外部使用者無法合法/可靠採用 | M | pyproject.toml；.github/workflows | 發佈 checklist 全綠 |
| I-11 | P2 | fail_on 在 audit/dev 靜默無效 | 排程稽核無法警示 | S | exit_code.py:15 | 警告或支援 |
| I-12 | P2 | confirmed_by 在 CI 為 unknown | 授權紀錄薄弱 | S | pipeline.py:62-67 | Action 帶 GITHUB_ACTOR |
| I-13 | P2 | 登入失敗、env 缺失只在 matrix reason，無終端提示 | 誤讀結果 | S | blind 2.4 | 摘要列 not_tested 原因 |
| I-14 | P2 | audit 登入會寫 auth.*；對外說法需精確 | 法律/信任 | S | traceability.md:12 | USAGE 明示 |
| I-15 | P2 | RPC 產生無意義 insert/update/delete 格 | 報告噪音 | S | L07 audit matrix | RPC 只有 select 格 |
| I-16 | P3 | lab env 不給 email、sql 不印結果 | 盲測摩擦 | S | blind 2.1 #9 | env 印 email |
| I-18 | P2 | SPEC §8／NFR-01 `log_statement = mod` 說法與 ADR-019 實測不符 | 規格正確性 | S | GI-01 | SPEC 改寫 |
| I-17 | P3 | 報告中英混雜、curl 遮罩不可直接執行未說明 | 可讀性 | S | HTML 報告 | 一致語言、說明 |

## 更正
- 盲測 F14（「stdout 關閉時報告不寫出」）不成立：dev 預設只輸出 HTML（cli.py:117、DEFAULT_FORMATS），已撤回。

## 已驗證為良好、無需處理
- 授權閘門、S4 Supabase URL 確認、audit 寫入閘門（safety/mode.py）；985 個單元測試通過；6 個人工變異全部被抓到。
- 設定檔嚴格驗證、錯誤訊息精準（含行列號與欄位路徑）。
- C01–C04 對照組在 ci＋init 草稿下 0 個 confirmed 誤報。

## I ↔ GI 對應
I-01→GI-02、I-02→GI-03、I-03→GI-08、I-04→GI-05、I-05→GI-06、I-06a→GI-09、I-06b→GI-10、I-07→GI-11、I-08→GI-13、I-09→GI-07、I-10→GI-12、I-11→GI-04、I-12→GI-14、I-14→GI-15、I-18→GI-01。I-13、I-15、I-16、I-17 只在本清單。

## 待人類決策
I-01（exit code 與門檻）、I-05（ci 跑 M1）、I-09（跨租戶讀取嚴重度／fail_on 預設）、I-11（audit fail_on）、I-10（授權條款）、I-12（confirmed_by unknown 可否接受）。
