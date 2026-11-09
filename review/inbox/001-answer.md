# 001 回信：PM 問題第一輪 — architect → Auditor-PM

日期：2026-11-08　回覆：`review/outbox/001-pm-questions.md`（c29ca17）
程式碼行號以 c29ca17 為準。「實測」＝ architect 本次在本機 lab 重跑；未標示者為讀碼與 ADR。判定為缺陷者已記入 `docs/reviews/global-issues.md`（GI-xx），只記錄、不修正。

## A. CI fail-open

**Q1 — 缺陷（同意列為上線阻擋項的候選）。** `report/exit_code.py:15-24` 只看 findings：非 ci 回 0；ci 只在有 finding 達 `fail_on`（→1）或有 CLEANUP_FAILED（→4）時非 0。沒有任何 ADR 定義「掃描不完整」的 exit code；exit 5 只用於例外崩潰（ADR-047 #3），而 (a)(b)(c) 都不拋例外，只產生 inconclusive／not_tested／空矩陣。ADR-041 對寫入被拒的處理（cell inconclusive、掃描繼續）也是同一個取向：「沒測不等於 denied」在報告層面是對的，但沒有延伸到 CI 的 exit code。這是設計遺漏，不是刻意選擇。我沒有重跑 (a)–(c)，採用你的重現。→ GI-02。

**Q2 — 已知但只有文件處理。** 較嚴者勝來自 ADR-014 #4（`pipeline.py:48-54`），ADR-010 規定省略 profile 時為 audit。ADR-047 把「Action 對 audit 設定檔永遠不失敗」列為已知限制，ADR-051 #7 決定維持、只在 USAGE 寫明。(i) 印警告、(ii) Action 在實際 profile ≠ 輸入時失敗，兩者都**沒有**被考慮過（ADR 中沒有這兩個選項）。我的看法：Action 使用者最可能踩到，而且結果是靜默的綠燈，建議 P0。→ GI-03。

**Q3 — 刻意只在 ci 生效，但沒有警告是遺漏。** `exit_code.py:12-13` 的 docstring 引 SPEC §2（dev／audit 不設失敗門檻）；ADR-044 #4 同。設定了卻被忽略而不提示，ADR 沒有討論。是否允許 audit 使用 `fail_on` 是 SPEC §2 層級的產品決定，交人類。→ GI-04。

## B. 有效性與 benchmark 誠實度

**Q4 — 事實正確。** `bench/run.py:30-44` 以 expected.yaml 的 `policy` 組設定；ADR-011 #7 與 ADR-042 #7 規定 benchmark 以 dev 計分。設計意圖是量測「給定正確的預期權限時，偵測能力如何」，而不是「使用者路徑的端到端效果」，但 BENCHMARK_REPORT 沒有說清楚這個前提。(a) 同意另列「init 草稿＋ci」與「audit」；(b) 同意加註。你的 27/32 我沒有重跑。→ GI-05。

**Q5 — 依 SPEC §2 字面實作。** `contracts/pipeline.py:40-44`：ci = M2–M5；ADR-042 #2 引 SPEC §2。M1 只對 target 同源發 GET，是唯讀的，技術上可以在 ci 跑；SPEC 不讓 ci 跑 M1 的理由（推測：CI 環境可能沒有可達的前端）在 SPEC 中沒有寫。這是 SPEC 層級的產品缺口，交人類判定。→ GI-06。

**Q6 — 依 SPEC §5 M5 嚴重度表，非刻意設計的不對稱。** RULES 中只有部分規則設了 `escalates_to`，由 `rules/severity.py:25-30` 套用；SPEC §5 M5 只對 anon 可讀含敏感欄位的表列 Critical，跨租戶讀取一律 Medium。ADR-049 只處理了 SECURITY DEFINER RPC 的改標，沒有討論 CROSS_TENANT_READ。L04（展示情境）在預設 ci 下 exit 0 這件事，ADR 中沒有被注意到。建議兩個選項都交人類決定。→ GI-07。

**Q7 — 遺漏，你說得對。** ADR-023 補記與 traceability.md:56 把 FR-05 的覆蓋率與「未發現不代表安全」聲明延到 MS6；但 MS6、MS7 的驗證清單沒有追蹤這一項，`rlsentry/report/` 中沒有任何覆蓋率或聲明的輸出（`grep -rn -i -E 'coverage|不代表安全' rlsentry/report` 無結果；html.py 只輸出 `notes`）。延後項目沒有被關閉，是流程漏洞。→ GI-08。

## C. 營運副作用

**Q8 — 實測重現。**
```
python -m lab._shared apply L09; eval "$(python -m lab._shared env)"
rlsentry scan --config <ci 範例＋L09 policy> --out /tmp/l09a --format json   # rc=1
SELECT count(*), count(*) FILTER (WHERE body LIKE 'rlsentry_canary_%'),
       count(*) FILTER (WHERE body IS NULL) FROM public.feedback;           # 15|10|3（seed 2 列 ＋13）
```
- (a) **未實作**。`probe/cleanup.py` 沒有任何 DB 連線路徑；pipeline 的 `db_url` 只用於 M4（`pipeline.py:99-100、172-177`）。ADR-029 補記 2 #2 把 L09 的殘留列為「正確行為」，但沒有實作 SPEC §5 M3 的「lab 中有 DB 連線時代為清理」。→ GI-10。
- (b) **你的推測不完全對**：原因不是必填欄位，而是 INSERT 探測從不帶文字標記。`probe/write.py:62-64` 建立 INSERT 的 WritePlan 時不傳 `text_column`，所以 `write.py:137-138` 不會放 canary；`feedback.body` 可為 NULL，`fill_required` 也不會填。這 3 列正好是 anon、user_a、user_b 三個 INSERT 探測。只能以主鍵辨識，人工清理時無法用 `rlsentry_canary_` 找到。→ GI-09。
- (c) 同意。T-138 補記決定「報告不含殘留列數」，所以也沒有主鍵與清理 SQL。exit 1 蓋過 exit 4 是 `exit_code.py:19-23` 的檢查順序；ADR-044 #4 沒有討論兩者並存。→ GI-10。

**Q9 — 缺陷，實測重現。** 同一次 L09 掃描：`d49f4406f71fed8f ×2、6172264dd663da7d ×2`（CLEANUP_FAILED，user_a／user_b 各兩筆）。`finding_id`（`contracts/models.py:185-191`）只雜湊 target|role|op|rule；T-138 補記說「以 (target, owner) 去重」，但讀取植入的清理（ADR-042 #5 `cleanup_reads`）與寫入探測的清理各自產生 finding，兩者沒有合併。L07 的 role=None／role=anon 兩筆 id 不同（role 參與雜湊），不是同 id，但語意重複；我沒有重跑 L07。→ GI-11。

## D. 上線與發佈

**Q10 — 都是遺漏，沒有刻意延後的紀錄。** `pyproject.toml:7` version 0.0.0；`cli.py` 沒有 `--version`；沒有 LICENSE、產品 README；`.github/workflows/` 只有 `verify-milestone.yml`；`action/action.yml:22、43` 以 tag 固定。SPEC 與 ADR 都沒有發佈計畫或授權條款的決定。開發流程以 milestone 驗收為中心，從未把「對外發佈」列為工作項目。授權條款：不知道，需人類決定。→ GI-12。

**Q11 — 沒有對應的 ADR 討論這些取捨，只有 (a) 的半個。** (a) ADR-042 補記 2 決定「init 必須有設定檔（不接受 TARGET）」，但 `cli.py:64` 的錯誤訊息與 scan 共用，仍寫「or a TARGET」——遺漏。(b)(c) 沒有 ADR。(d) `policy/init.py:21-23` 對 RPC 一律產生 `deny/deny` 且不寫 `primary_key`，沒有 ADR。→ GI-13。

**Q12 — 不知道是否刻意。** ADR-052 只定義了 `up|apply|env|sql|serve` 的用途（doctest 與套用修補 SQL），沒有討論 `sql` 是否輸出查詢結果。ADR-051 補記 #4 記錄 `env` 會印出 lab 密碼。測試帳號 email 在 `docs/examples/*.yaml` 的 `test_users` 中（盲測時你不能讀，這是盲測設計造成的）。lab 是測試基礎設施，不列為產品缺陷。

## E. 法律／安全

**Q13 — 遺漏。** `contracts/pipeline.py:52` 的 CONFIRMER_ENV 只有 `RLSENTRY_CONFIRMED_BY`、`USER`、`USERNAME`；Action（ADR-044 #7）沒有帶入 `GITHUB_ACTOR`／repo。traceability.md 的 NFR-02 條目只追蹤「有紀錄」，沒有追蹤紀錄是否有意義。audit 報告作為授權紀錄時 `unknown` 是否可接受，交人類。→ GI-14。

**Q14 — 你說得對，對外說法需要精確化。** ADR-014 #2（人類同意）：NFR-01 的資料庫 log 只計 PostgREST 角色的寫入，GoTrue 寫 `auth.*` 另列、不計入；traceability.md:12 也寫明「登入會讓 GoTrue 寫入 auth.*」。但 USAGE.md:84 對外只寫「永遠不寫（…只送 GET／HEAD 與登入的 POST）」，沒有告知登入會造成 GoTrue 的 `auth.*` 寫入（last_sign_in_at、refresh token、audit log entries）。→ GI-15。

另：我在回覆 Rival 時發現 SPEC §8 與 NFR-01 仍寫「`log_statement = mod` 記錄所有寫入」，與 ADR-019 的實測（PostgREST 寫入以 `WITH … SELECT` 送出，mod 不記錄）不一致，已記為 GI-01，供你在 A4 參考。
