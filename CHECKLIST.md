# RLSentry 生產檢核清單

自動產生，請勿手改 · 完成 16/18 · 進行中 0 · blocked 0

## [x] STAGE0 護欄測試（玩具 ticket）（已核准）
- [x] T-000 Stage 0 toy ticket — add() plus harness canaries（recon-dev，done，1 次）
- [x] T-001 Stage 0 canary 重跑（人類授權）（recon-dev，done，1 次）
- 驗證清單：docs/verification/STAGE0-v2.md（v2）

## [ ] MS0 基礎：合約、expected policy 格式、ground truth（進行中）
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
- [ ] T-024 Ground truth 與預期 policy 一致性測試（architect，todo，0 次） ← 依賴 T-015✓ T-016✓ T-017✓ T-018✓ T-019✓ T-020✓ T-021✓ T-022✓
- [ ] T-025 MS1–MS7 ticket 計畫（architect，todo，0 次） ← 依賴 T-013✓

## [ ] MS1 Lab benchmark + Safety（鎖定）

## [ ] MS2 M2 Discovery + M3 讀取（鎖定）

## [ ] MS3 M3 寫入（鎖定）

## [ ] MS4 M4 Whitebox（鎖定）

## [ ] MS5 M1 Recon（鎖定）

## [ ] MS6 M5 Report + 介面 + profiles（鎖定）

## [ ] MS7 整合與交付（鎖定）
