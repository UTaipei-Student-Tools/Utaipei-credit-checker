# 北市大畢業通 — 測試就緒報告 (TEST_READY.md)

**發布日期**：2026-09-06  
**發布代理人**：`teamwork_preview_test_writer_e2e` (Test Writer Subagent)  
**工作目錄**：`d:\學分計算\.agents\teamwork_preview_test_writer_e2e`  
**測試檔案**：`tests/test_e2e_requirement_suite.py`  
**架構規範**：`TEST_INFRA.md`  

---

## 1. 測試套件總覽 (Suite Overview)

依據 `ORIGINAL_REQUEST.md` 與 `PROJECT.md § Feature Inventory`，本 E2E 需求測試套件採**不透明箱（Opaque-Box）**與**需求驅動（Requirement-Driven）**設計，杜絕任何 Facade/Dummy 假測試，100% 針對真實業務邏輯、成績單資料流與輸出品質進行嚴密斷言。

### 四層級（4-Tier）測試規模統計：
- **Tier 1: Feature Coverage（功能覆蓋層）**：共 38 個測試案例（7 大功能面向，每項 5~6 個測試）
  - R1 本地化與代碼消除：6 案例
  - R2 課程名稱正規化：6 案例
  - R2 主修與雙主修身分識別：5 案例
  - R2 通識四大領域驗證：5 案例
  - R3 儀表板 6 大卡片：6 案例
  - R3 7 欄折疊展開結構化表格：5 案例
  - R3 PDF 結構化排版與零代碼：5 案例
- **Tier 2: Boundary & Corner Cases（邊界與極端異常層）**：共 6 個測試案例
- **Tier 3: Cross-Feature Interactions（跨模組協同整合層）**：共 5 個測試案例
- **Tier 4: Real-World Application Scenarios（真實成績單驗收層）**：共 5 個測試案例
- **總計測試案例數**：**54 個獨立測試案例**。

---

## 2. 測試執行指令 (Execution Instructions)

### 執行全量 E2E 需求測試套件：
```powershell
pytest tests/test_e2e_requirement_suite.py -v
```

### 依 Tier 分層執行：
```powershell
# 執行 Tier 1 功能面向測試
pytest tests/test_e2e_requirement_suite.py -k "Tier1" -v

# 執行 Tier 2 邊界與異常測試
pytest tests/test_e2e_requirement_suite.py -k "Tier2" -v

# 執行 Tier 3 跨功能協同測試
pytest tests/test_e2e_requirement_suite.py -k "Tier3" -v

# 執行 Tier 4 真實成績單 (陳同學) 驗收測試
pytest tests/test_e2e_requirement_suite.py -k "Tier4" -v
```

### 執行特定需求群組：
```powershell
# 檢驗 R1 本地化代碼消除
pytest tests/test_e2e_requirement_suite.py -k "R1" -v

# 檢驗 R2 正規化與身分辨識
pytest tests/test_e2e_requirement_suite.py -k "R2" -v

# 檢驗 R3 儀表板卡片與表格 UI
pytest tests/test_e2e_requirement_suite.py -k "R3" -v
```

---

## 3. 基準測試結果 (Baseline Execution Results)

在專案當前未完成 Milestone 1–3 實作重構之基線狀態下，全量測試套件呈現符合預期之「**紅燈（Red Baseline）**」狀態：

| 測試層級 | 測試數量 | 現行通過數 | 現行預期失敗數 | 失敗核心原因與定位 |
| :--- | :---: | :---: | :---: | :--- |
| **Tier 1: R1 本地化代碼消除** | 6 | 0 | 6 | `REQUIREMENT_DEFICIT:`、`APPLICATION:`、`SEARCH_IN` 等代碼未建立參數化轉譯與 Scrubber |
| **Tier 1: R2 課程名稱正規化** | 6 | 2 | 4 | `handbook_rules.py` 僅轉換國英文 `(I)`，遺漏微積分與物化等課程之 `(I)`~`(VI)` |
| **Tier 1: R2 主修與雙主修辨識** | 5 | 2 | 3 | `pdf_parser.py` 表頭正則缺少 `雙主修：` 擷取；`微積分(I)` 無法對應雙主修必修 |
| **Tier 1: R2 通識四大領域驗證** | 5 | 3 | 2 | `graduation_service.py` 在候選清單為空時將通識 `identity_status` 誤降為 `UNKNOWN` |
| **Tier 1: R3 儀表板 6 大卡片** | 6 | 3 | 3 | 目前儀表板僅實作 4 張指標卡，尚缺總學分、雙主修進度、非學分門檻之獨立簡約卡片 |
| **Tier 1: R3 7 欄折疊展開表格** | 5 | 3 | 2 | 表格缺少「成績」欄位；`notes` 欄位堆疊多行 `<p>` 段落破壞排版 |
| **Tier 1: R3 PDF 結構化排版** | 5 | 4 | 1 | PDF 報表排版存在內部代碼外洩與未對齊問題 |
| **Tier 2: 邊界與極端異常處理** | 6 | 4 | 2 | 罕見羅馬數字 `(VI)` 與全半形括號混用尚未正規化 |
| **Tier 3: 跨模組端對端協同** | 5 | 1 | 4 | 跨模組代碼流尚未通過 Failsafe Scrubber 清洗；修習中課程缺乏正面提示 |
| **Tier 4: 真實成績單全鏈路驗收** | 5 | 0 | 5 | 陳同學成績單表頭雙主修未解析、`微積分(I)` 未認列雙主修、通識報認列不足警告 |
| **總計** | **54** | **22** | **32** | **32 個測試精確定位系統需實作修復之缺陷** |

---

## 4. 發現之實作缺陷與升級清單 (Defects Escalated to Implementers)

本測試套件在基線分析中確認並升級以下 **5 大核心實作缺陷** 給後續實作代理人（Milestone Implementers）：

1. **缺陷 1 (M1 - R2)：課程名稱正規化範圍過於狹隘**
   - **檔案**：`d:\學分計算\handbook_rules.py:962-984`
   - **現象**：僅硬編碼替換「英文」與「國文」的 `(I)`/`(II)`/`(III)`，導致 `微積分(I)`、`普通物理學(III)`、`進階化學(IV)` 無法對應為 `(一)`~`(四)`。
   - **修復方向**：使用通用序列正規化正則 `\((I{1,3}|IV|V|VI|[1-6]|[一二三四五六])\)` 統一把括號內數字轉為 `(一)`~`(六)`，並消除多餘空格。

2. **缺陷 2 (M1 - R2)：成績單表頭解析遺失雙主修與輔系欄位**
   - **檔案**：`d:\學分計算\pdf_parser.py:380-412`
   - **現象**：表頭文字區塊僅提取單一系所，未擷取 `雙主修：` 與 `輔系：` 欄位，導致陳同學 `應用物理暨化學系應用化學組-修習中` 身分遺失。
   - **修復方向**：增加正則 `re.search(r"雙主修[：:]\s*([^\s\n]+)", text)`，將組別與狀態寫入 `student_info["double_major"]`。

3. **缺陷 3 (M1 - R2)：通識課程身分被強降為 UNKNOWN**
   - **檔案**：`d:\學分計算\graduation_service.py:3573-3581`
   - **現象**：學系專業手冊不含全校通識，當 `len(matching_candidates) == 0` 時，忽略了 `public_evidence.public_identity_state == "VERIFIED"`，強制設 `identity = UNKNOWN`，觸發「課程身分或要求來源尚不足以安全認列」警告。
   - **修復方向**：在手冊候選清單為空但公共課綱已驗證時，提升身分為 `VERIFIED`，並繼承通識所屬領域標籤。

4. **缺陷 4 (M2 - R1)：底層英文代碼與除錯前綴直接外洩**
   - **檔案**：`d:\學分計算\snapshot_renderer.py:100-140` 與 `snapshot_exports.py`
   - **現象**：`_PUBLIC_CODE_REASONS` 缺少 `REQUIREMENT_DEFICIT:`、`APPLICATION:*`、`SEARCH_*` 對照，且含有連字號與冒號時 ASCII 兜底過濾器失效。
   - **修復方向**：建立參數化要求阻擋翻譯器、官方手冊引用解析器，並於輸出端部署全域防禦性純淨化過濾器（Failsafe Scrubber）。

5. **缺陷 5 (M3 - R3)：儀表板卡片與課程明細表格排版未達標**
   - **檔案**：`d:\學分計算\snapshot_renderer.py:2284-2289`、`_course_markup`
   - **現象**：儀表板僅有 4 張卡片，缺少總學分、雙主修進度、非學分門檻；課程表格缺少「成績」欄位，且備註欄多段 `<p>` 堆疊過長。
   - **修復方向**：重構為 6 大摘要卡片；表格擴充為 7 欄位（課名、學期、成績、修得學分、此類採計學分、採計類別、狀態／備註）。

---

## 5. 測試套件交付與驗收準則判定 (Handoff Verdict)

- [x] **四層級（4-Tier）測試套件已完全實作**：`tests/test_e2e_requirement_suite.py`（54 個測試案例，0 處 facade 假代碼）。
- [x] **測試架構說明文件已發布**：`d:\學分計算\TEST_INFRA.md`。
- [x] **測試就緒狀態與基準分析已發布**：`d:\學分計算\TEST_READY.md`。
- [x] **備份符合自訂規則之中文文件**：`C:\Users\jimmy\OneDrive - 臺北市立大學\桌面\CIL資料夾\學分計算測試\`。
- [x] **就緒狀態**：**TEST READY**（測試套件完備，可供後續 Milestone 代理人作為實作與驗收之客觀依據）。
