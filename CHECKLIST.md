# RLSentry 生產檢核清單

自動產生，請勿手改 · 完成 33/53 · 進行中 0 · blocked 0

## [x] STAGE0 護欄測試（玩具 ticket）（已核准）
- [x] T-000 Stage 0 toy ticket — add() plus harness canaries（recon-dev，done，1 次）
- [x] T-001 Stage 0 canary 重跑（人類授權）（recon-dev，done，1 次）
- 驗證清單：docs/verification/STAGE0-v2.md（v2）

## [x] MS0 基礎：合約、expected policy 格式、ground truth（已核准）
- [x] T-010 合約：§6 資料模型與 rule catalog（architect，done，1 次）
- [x] T-011 合約：expected policy 與 rlsentry.yaml（architect，done，1 次）
- [x] T-012 合約：ground truth 格式與 benchmark 輸出（architect，done，1 次）
- [x] T-013 合約：模組介面與相依套件（architect，done，1 次）
- [x] T-014 可見測試：policy 解析三函式（architect，done，1 次）
- [x] T-015 Ground truth：L01–L03（architect，done，1 次）
- [x] T-016 Ground truth：L04–L06（architect，done，1 次）
- [x] T-017 Ground truth：L07–L09（architect，done，1 次）
- [x] T-018 Ground truth：L10–L12（architect，done，1 次）
- [x] T-019 Ground truth：C01–C02（architect，done，1 次）
- [x] T-020 Ground truth：C03–C04（architect，done，1 次）
- [x] T-021 policy/resolve.py：resolve_expected（probe-dev，done，1 次）
- [x] T-022 policy/visibility.py：row_permitted（probe-dev，done，1 次）
- [x] T-023 policy/load.py：load_config（probe-dev，done，1 次）
- [x] T-024 Ground truth 與預期 policy 一致性測試（architect，done，1 次）
- [x] T-025 MS1–MS7 ticket 計畫（architect，done，1 次）
- [x] T-026 稽核修正：ProbeResult 已知列語意、Finding.rule 檢查（architect，done，2 次）
- [x] T-027 稽核修正：TablePolicy.primary_key、寫入閘門與 profile 規則（architect，done，1 次）
- [x] T-028 稽核修正：計分定義、lab 慣例、ground truth 隔離（architect，done，1 次）
- [x] T-029 稽核修正：ground truth L05、L07、L09（architect，done，1 次）
- [x] T-030 稽核修正：ground truth L01、L11、L12（architect，done，1 次）
- [x] T-031 可見測試：設定檔 YAML 錯誤不得回顯內容（architect，done，1 次）
- [x] T-032 policy/load.py：YAML 錯誤只回報位置與種類（probe-dev，done，1 次）
- 驗證清單：docs/verification/MS0-v1.md（v1）

## [ ] MS1 Lab benchmark + Safety（進行中）
- [x] T-040 pyproject：限定 package discovery，讓 pip install -e .[dev] 在乾淨環境可用（architect，done，1 次）
- [x] T-041 合約：safety 層、ci write_hosts、lab 工具；ADR-016–018（architect，done，1 次）
- [x] T-042 可見測試：safety gate、mode、mask（architect，done，1 次）
- [x] T-043 可見測試：ratelimit、http client（architect，done，1 次）
- [ ] T-044 Lab 驗證測試基礎：conftest、oracle、共用 lab 測試（architect，todo，0 次） ← 依賴 T-041✓
- [ ] T-045 Lab 驗證測試：16 個情境的測試檔（architect，todo，0 次） ← 依賴 T-044…
- [x] T-050 safety/gate.py：authorize 授權閘門（recon-dev，done，1 次）
- [x] T-051 safety/mode.py：require_write_allowed 寫入閘門（recon-dev，done，1 次）
- [x] T-052 safety/mask.py：mask、mask_text（recon-dev，done，1 次）
- [x] T-053 safety/ratelimit.py：RateLimiter（recon-dev，done，1 次）
- [ ] T-054 safety/http.py：SafeClient（唯一的 HTTP client）（recon-dev，todo，0 次） ← 依賴 T-043✓ T-051✓ T-053✓
- [ ] T-060 Lab 共用：Supabase 專案設定與 labctl（lab-dev，todo，0 次） ← 依賴 T-044…
- [ ] T-061 Lab L01：RLS 未啟用（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-062 Lab L02：Policy 恆真（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-063 Lab L03：依 user_metadata 授權（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-064 Lab L04：跨租戶讀取（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-065 Lab L05：跨租戶修改（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-066 Lab L06：SECURITY DEFINER view（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-067 Lab L07：SECURITY DEFINER RPC（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-068 Lab L08：service_role 進 bundle（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-069 Lab L09：INSERT 寬鬆（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-070 Lab L10：敏感欄位外洩（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-071 Lab L11：公開 Storage bucket（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-072 Lab L12：OpenAPI 被限制（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-073 Lab C01：對照組：owner-scoped（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-074 Lab C02：對照組：公開表（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-075 Lab C03：對照組：空表（lab-dev，todo，0 次） ← 依賴 T-045… T-060…
- [ ] T-076 Lab C04：對照組：無資料的使用者（lab-dev，todo，0 次） ← 依賴 T-045… T-060…

## [ ] MS2 M2 Discovery + M3 讀取（鎖定）

## [ ] MS3 M3 寫入（鎖定）

## [ ] MS4 M4 Whitebox（鎖定）

## [ ] MS5 M1 Recon（鎖定）

## [ ] MS6 M5 Report + 介面 + profiles（鎖定）

## [ ] MS7 整合與交付（鎖定）
