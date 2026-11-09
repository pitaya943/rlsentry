# RLSentry SPEC 修改建議清單（A5）

詳細內容（現行文字、證據、建議文字、替代方案、影響）見 `review/spec-review.html`。位置以 `docs/SPEC.md` 行號為準。

| 編號 | 優先 | 位置 | 一句話建議 |
|---|---|---|---|
| S-01 | P0 | docs/SPEC.md:86；:131（FR-13）；:173；:279 | ci 的失敗條件要涵蓋「掃描不完整」，不只「有 finding」 |
| S-02 | P0 | docs/SPEC.md:81-89 | 明定「有效 profile」的決定規則與可見性；CLI 不得被靜默覆蓋 |
| S-03 | P0 | docs/SPEC.md:123（FR-05）；:217（§5 M2） | 把「覆蓋率與未發現不代表安全」從 FR-05 的附帶語句拆成獨立、可驗證的需求 |
| S-04 | P0 | docs/SPEC.md:145（NFR-06）；:472-487（§9 評估指標） | 有效性指標必須註明量測條件，並新增「使用者路徑」指標 |
| S-05 | P1 | docs/SPEC.md:85-87（profile 表的模組欄）；:150-170（架構圖與流程） | 同步 profile 模組表：ci 加唯讀 M1、audit 有 DB 時可跑 M4 |
| S-06 | P1 | docs/SPEC.md:271-279（§5 M5 嚴重度表與 fail_on 預設） | 嚴重度表：跨租戶讀取遇敏感欄位要升級；吸收 ADR-049 的改標規則 |
| S-07 | P1 | docs/SPEC.md:231-232（寫入探測）；:243（清理） | 寫入探測與清理的可驗證要求：每一列都帶標記、殘留可定位、lab 代清要嘛做要嘛刪 |
| S-08 | P1 | docs/SPEC.md:317；:328 | Finding.id 在單份報告內必須唯一，並定義去重規則 |
| S-09 | P1 | docs/SPEC.md:133（FR-15）；:364 | `rlsentry init` 的產出必須是「填完密碼就能掃」的完整設定 |
| S-10 | P1 | 新增 §3.1「發佈與相容性」（建議放在 NFR 之後） | 新增對外發佈需求：版本、授權、相容性承諾、報告格式穩定性 |
| S-11 | P1 | docs/SPEC.md:140（NFR-01）；:190（Safety 模式檢查）；:441（§8）；:555（MS1） | NFR-01「唯讀」的精確定義與驗證方式改為實際做法 |
| S-12 | P1 | docs/SPEC.md:89；新增 §5 M5「exit code」小節 | 把 exit code 與 fail_on 適用範圍寫成公開介面 |
| S-13 | P2 | docs/SPEC.md:229（§5 M3 讀取探測）；:142（NFR-03） | 讀取探測的方式改為實作的「只取主鍵的單一 GET」 |
| S-14 | P2 | docs/SPEC.md:281-328（§6 資料模型） | §6 改為「以 contracts 與發佈的 JSON Schema 為準」，SPEC 只保留語意 |
| S-15 | P2 | docs/SPEC.md:330-362（設定檔） | 設定檔範例補齊實際欄位與預設值 |
| S-16 | P2 | docs/SPEC.md:287（Op）；:300；:397（L07） | RPC 的表示方式：寫明「RPC 以 select 表示、只用 GET」，矩陣不產生寫入格 |
| S-17 | P2 | docs/SPEC.md:408-430（expected.yaml 格式） | Ground truth 格式同步 ADR：safe case 可為 allowed、鍵名 target、L04 範例更正 |
| S-18 | P2 | docs/SPEC.md:443-446（§8 執行方式） | benchmark 執行方式改為實際架構，並註明需要 repo |
| S-19 | P2 | docs/SPEC.md:195-207（§5 M1）；:187-193（Safety） | M1 與 Safety 吸收已實作的安全邊界：只抓同源、source map 只依引用、端點確認（S4） |
| S-20 | P2 | docs/SPEC.md:209-217（§5 M2） | M2 寫明 OpenAPI 與 bundle 取聯集、受限 OpenAPI 時的行為與 ci 的限制 |
| S-21 | P2 | docs/SPEC.md:141（NFR-02）；§7 | 授權紀錄必須記錄有意義的確認者 |
| S-22 | P2 | docs/SPEC.md:146-147（NFR-07、NFR-08）；:144（NFR-05） | 讓 NFR-05、07、08 的驗收可以客觀重跑 |
| S-23 | P2 | docs/SPEC.md:103-109（核心使用者故事） | 使用者故事改成與實作一致、可驗證的說法 |
| S-25 | P2 | docs/SPEC.md:493-618（§10 專案結構、§11 開發流程）；:630-642（§13 風險中與代理相關的列） | 把開發流程從產品規格中分離 |
| S-24 | P3 | docs/SPEC.md:620-628（§12 決策）；:60-69（非目標）；:402（L11） | 更新決策狀態，並把 Storage 明確定位 |
| S-26 | P3 | docs/SPEC.md:366-382（§7 安全、倫理與法律） | §7 補上使用者端的資料處理與 production 稽核注意事項 |

需人類決策：S-01（門檻預設值）、S-05（是）、S-06（是）、S-09（TODO 是否擋掃描）、S-10（授權條款）、S-12（audit 是否適用 fail_on）、S-21（audit 是否拒絕 unknown）、S-25（harness 引用（凍結））
