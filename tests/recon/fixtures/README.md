# 真實框架 bundle fixture（SPEC §9 測試層級；ADR-036、ADR-037）

由 architect 於 2026-11-06 在本機以官方工具建置，產出原封不動提交（只刪除圖片、CSS 與 CRA 的
`main.*.js.map`、`*.LICENSE.txt`）。原始碼與建置設定在 `_sources/<框架>/`（`env.production`
即建置時的 `.env.production`）。所有 key 都是假的：JWT 以 HS256、密鑰 `rlsentry-fixture-not-a-real-secret`
簽出，project ref 為虛構（`fxtr…`）；`AIzaSyFxtr…` 不是真的 Google key。

| 目錄 | 工具與版本 | 建置指令 | 植入內容 |
| --- | --- | --- | --- |
| `nextjs/` | Next.js 15.5.29（pages router、`output: "export"`）、supabase-js 2.119.0 | `create-next-app@15 --no-app`，`next build` | `pages/index`：anon JWT；`pages/admin`（只在 `_buildManifest.js` 出現）：service_role JWT；`components/Debug`（`next/dynamic`，只以 `l.e(43)` 與 webpack `u()` 出現）：role=authenticated 的 JWT |
| `vite/` | Vite 8.3.6（react-ts 範本，`build.sourcemap: true`）、supabase-js 2.119.0 | `npm create vite@latest -- --template react-ts`，`vite build` | 入口：`sb_publishable_…`；lazy route `Admin`（只以 `import(\`./Admin-….js\`)` 出現）：service_role JWT；兩個 `.map` |
| `cra/` | react-scripts 5.0.1、supabase-js 2.119.0 | `create-react-app@5`，`react-scripts build` | `main`：自訂網域 `https://api.fixture-cra.example` 與 anon JWT；lazy chunk `203`（只在 webpack chunk map 出現）：`{apiKey:"AIzaSy…"}`（unverified）；`main` 的 map 刻意刪除（測 404 的 map） |

預期結果（`tests/recon/test_recon_fixtures.py` 斷言）：

| fixture | supabase_url | key（label → kind） | finding |
| --- | --- | --- | --- |
| nextjs | `https://fxtrnextjsfixture0001.supabase.co` | jwt:anon → publishable、jwt:service_role → secret、jwt:authenticated → unverified | SECRET_KEY_IN_BUNDLE（jwt:service_role）、UNVERIFIED_KEY（jwt:authenticated） |
| vite | `https://fxtrvitefixture000001.supabase.co` | sb_publishable → publishable、jwt:service_role → secret | SECRET_KEY_IN_BUNDLE（jwt:service_role） |
| cra | `https://api.fixture-cra.example` | jwt:anon → publishable、unverified → unverified | UNVERIFIED_KEY（unverified） |

實測發現（寫進合約的理由）：壓縮後的 `createClient` 呼叫看不到函式名（`(0,t(8033).UU)("url","key")`）；
Vite 8 用反引號字串；source map 內嵌 supabase-js 文件範例（`https://xyzcompany.supabase.co`、
`your-publishable-key`）；phoenix 的 `"base64url.bearer.phx."` entropy 3.52。
