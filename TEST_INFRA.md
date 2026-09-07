# 北市大畢業通 — E2E 需求驅動測試架構規範 (TEST_INFRA.md)

## 1. 測試架構總覽 (Architecture Overview)

本測試架構依據 `ORIGINAL_REQUEST.md` 與 `PROJECT.md § Feature Inventory` 之規範，建立四層級（4-Tier）不透明箱（Opaque-Box）端對端回歸與驗收測試套件，檔案位於 `tests/test_e2e_requirement_suite.py`。

本測試套件專責檢驗四大核心需求之端對端行為：
- **R1. 全面消除未本地化英文與內部代碼 (Full Localization & Clean Presentation)**
- **R2. 提升成績單解析與校務系統抓取準確度 (Parser & Scraper Accuracy Improvement)**
- **R3. UI 簡約化與表格化重構 (Clean UI & Tabular Presentation)**
- **R4. 全面自動化測試與雙平台部署 (Verification & Deployment)**

```
+-----------------------------------------------------------------------------------+
|                        4-TIER E2E REQUIREMENT TEST SUITE                          |
+-----------------------------------------------------------------------------------+
|  Tier 1: Feature Coverage (特徵覆蓋層，7 大功能面向，每項 >= 5 案例)             |
|    ├─ R1 Localization (代碼與除錯前綴徹底轉譯繁體中文)                           |
|    ├─ R2 Normalization (羅馬數字、中文數字、半全形、空白正規化)                  |
|    ├─ R2 Major / Double Major (主修與雙主修身分表頭辨識與課程配置)               |
|    ├─ R2 GE Verification (通識四大領域 PublicCourseCatalog 驗證無警告)           |
|    ├─ R3 Dashboard Cards (6 大摘要指標卡片結構與數值正確性)                      |
|    ├─ R3 Tabular Expanders (7 欄結構化表格、成績欄位、排版整潔度)                |
|    └─ R3 PDF Export Clean Layout (PyMuPDF 排版對齊、100% 繁中零代碼)              |
+-----------------------------------------------------------------------------------+
|  Tier 2: Boundary & Corner Cases (邊界與極端異常處理層)                           |
|    ├─ 空輸入與空二進位流優雅容錯 (Fail-Closed)                                    |
|    ├─ 破損課程字串、純數字代碼與異常符號過濾                                     |
|    ├─ 特殊與高階羅馬數字 (I)~(VI)、全形數字與中文數字混合                         |
|    ├─ 半形/全形括號、冒號與空格交錯混合                                          |
|    ├─ 零學分門檻課程（體育、服務學習、大學生活學習與輔導）學分守恆                |
|    └─ 不及格 (F)、停修 (W)、修習中 (未/--) 之學分不灌水與狀態區隔                 |
+-----------------------------------------------------------------------------------+
|  Tier 3: Cross-Feature Interactions (跨模組端對端協同整合層)                      |
|    ├─ 課名正規化 ➔ 雙主修規則媒合 ➔ 審查配置 ➔ UI 渲染全鏈路無代碼洩漏           |
|    ├─ 修習中課程全鏈路追蹤 (標記 IN_PROGRESS ➔ 0 實得學分 ➔ 正向提示 ➔ PDF 乾淨)   |
|    ├─ 雙主修學分守恆性約束 (主修 + 雙主修 + 通識 + 自由選修 = 總修得學分)         |
|    ├─ 終端 Failsafe Scrubber 防禦測試 (注入合成代碼確保被強制清洗)               |
|    └─ 跨媒體一致性驗證 (HTML 表格、CSV 匯出、PDF 報表三者數值與狀態一致)          |
+-----------------------------------------------------------------------------------+
|  Tier 4: Real-World Application Scenarios (真實成績單驗收層)                      |
|    └─ 陳同學成績單 (`學生手冊/U1131002220260906175350.pdf`)                      |
|         ├─ 學號 U11310022、113 學年度地生系地球環境組 + 雙主修物化系化學組        |
|         ├─ `微積分(I)` 成功採計為雙主修必修 `微積分(一)` (3.0 學分)               |
|         ├─ `普通化學實驗(二)` 標記為修習中 (0.0 學分，完成後認列)                |
|         ├─ 通識 6 門 (12 學分) 100% 認列四大領域，無「身分尚不足以安全認列」警告  |
|         ├─ 儀表板 6 大卡片完整呈現                                                |
|         └─ 畫面與 PDF 報表 0 處內部代碼洩漏 (`REQUIREMENT_DEFICIT:` 等)           |
+-----------------------------------------------------------------------------------+
```

---

## 2. 權威預期來源 (Authoritative Expected Output Derivation)

每個測試案例之預期值均嚴格源自以下權威資料：
1. **成績單基準依據**：`學生手冊/U1131002220260906175350.pdf`（陳同學真實成績單視覺排版與原始字元）。
2. **課程手冊規範**：
   - `rules_config.json` 及 `curriculum_registry.py`：
     - 113 學年度地球環境暨生物資源學系手冊（主修 128 學分、通識 28 學分、專業必選修規定）。
     - 115 學年度應用物理暨化學系應用化學組雙主修手冊（必修 `微積分(一)` 3 學分、`普通化學實驗(二)` 1 學分等共 40 學分門檻）。
3. **全校公開課程目錄**：`public_course_catalog.py`（通識四大領域課程歸屬與 `VERIFIED` 標籤）。
4. **禁止代碼黑名單**：
   `REQUIREMENT_DEFICIT:`, `REQUIREMENT_EVIDENCE_`, `APPLICATION:`, `SEARCH_IN`, `SEARCH_EXHAUSTED`, `handbook:\d+`, `primary:\d+`, `target:\d+`, `WAIVER_DECISION_REQUIRED`, `RULE_CONTEXT:`, `28030`。

---

## 3. 測試層次與案例清單 (Test Inventory)

### Tier 1: 功能面向覆蓋測試 (Feature Coverage)
| 測試案例名稱 | 涵蓋需求 | 測試內容與斷言標的 |
| :--- | :--- | :--- |
| `test_r1_no_requirement_deficit_raw_prefix` | R1 | 驗證 HTML 與 PDF 中無 `REQUIREMENT_DEFICIT:`，轉為中文缺額說明 |
| `test_r1_no_application_blocker_raw_prefix` | R1 | 驗證無 `APPLICATION:` 前綴，轉為「雙主修資格審核：尚未取得教務處核准紀錄」等繁中 |
| `test_r1_no_search_raw_codes_in_presentation` | R1 | 驗證無 `SEARCH_INCOMPLETE` / `SEARCH_EXHAUSTED` 等求解器標籤 |
| `test_r1_handbook_colon_namespaces_translated` | R1 | 驗證 `handbook:113:earth:...` 轉譯為自然中文手冊書目引用 |
| `test_r1_parametric_deficit_contains_meaningful_chinese` | R1 | 驗證缺額說明具體呈現要求名稱與缺額數值 |
| `test_r1_known_course_codes_translated_to_titles` | R1 | 驗證課號 `28030` 轉為「大學生活學習與輔導」 |
| `test_r2_normalize_roman_numerals_i_to_vi` | R2 | 驗證 `微積分(I)`~`(VI)` 轉為 `微積分(一)`~`(六)` |
| `test_r2_normalize_arabic_numerals_in_parentheses` | R2 | 驗證 `微積分(1)` 轉為 `微積分(一)` |
| `test_r2_normalize_whitespace_and_punctuation` | R2 | 驗證 `儀器分析 (一)` 空白消除為 `儀器分析(一)` |
| `test_r2_normalize_preserves_course_semantics_and_subtitles` | R2 | 驗證保留 `DNA分子生物學`、`英文(三):職場商旅` 等語意 |
| `test_r2_normalize_case_insensitivity_and_fullwidth` | R2 | 驗證全半形括號 `（I）` 與大小寫 `(i)` 均轉為 `(一)` |
| `test_r2_detect_primary_department_and_track` | R2 | 驗證 `detect_department_track` 正確識別地生系地球環境組 |
| `test_r2_parse_transcript_header_double_major` | R2 | 驗證解析表頭雙主修欄位「應用物理暨化學系應用化學組-修習中」 |
| `test_r2_parse_transcript_header_minor` | R2 | 驗證解析表頭輔系欄位 |
| `test_r2_double_major_target_plan_resolution` | R2 | 驗證正確加載 115 物化系化學組雙主修 40 學分規則表 |
| `test_r2_calculus_allocates_to_double_major_requirement` | R2 | 驗證 `微積分(I)` 成功配置至雙主修必修 `微積分(一)` |
| `test_r2_ge_courses_verified_via_public_catalog` | R2 | 驗證 6 門通識於 `PublicCourseCatalog` 中為 `VERIFIED` |
| `test_r2_ge_identity_status_not_downgraded_to_unknown` | R2 | 驗證通識課程不被降級為 `UNKNOWN` 身分 |
| `test_r2_ge_no_insufficient_identity_warning` | R2 | 驗證無「課程身分或要求來源尚不足以安全認列」警告 |
| `test_r2_ge_domains_correctly_classified` | R2 | 驗證通識歸入人文、公民、自然、藝術四大領域 |
| `test_r2_ge_completed_credits_recognized` | R2 | 驗證通識已修得 12 學分正確入帳 |
| `test_r3_dashboard_metric_total_credits` | R3 | 驗證 6 大卡片之「總學分」顯示應修總額 (128 學分) |
| `test_r3_dashboard_metric_earned_credits` | R3 | 驗證 6 大卡片之「已修得」顯示實得與有效採計 |
| `test_r3_dashboard_metric_missing_credits` | R3 | 驗證 6 大卡片之「尚缺」顯示尚缺學分數 |
| `test_r3_dashboard_metric_primary_progress` | R3 | 驗證 6 大卡片之「主修進度」顯示必修完成度 |
| `test_r3_dashboard_metric_double_major_progress` | R3 | 驗證 6 大卡片之「雙主修進度」自適應顯示修習組別與進度 |
| `test_r3_dashboard_metric_non_credit_gates` | R3 | 驗證 6 大卡片之「非學分門檻」顯示體育/服務學習進度 |
| `test_r3_expander_contains_html_table_structure` | R3 | 驗證要求展開元件內含標準語意 `<table>` |
| `test_r3_table_header_seven_columns` | R3 | 驗證表格標題具備 7 欄位（課名、學期、成績、修得學分、此類採計學分、採計類別、狀態／備註） |
| `test_r3_table_grade_column_rendered` | R3 | 驗證表格呈現成績（如 85、通過、修習中） |
| `test_r3_unallocated_courses_tabular_expander` | R3 | 驗證尚未採計課程點開後亦為結構化對齊表格 |
| `test_r3_table_notes_column_clean_structure` | R3 | 驗證狀態／備註欄無混亂多行 `<p>` 段落堆疊 |
| `test_r3_pdf_valid_binary_and_structure` | R3 | 驗證 `build_student_pdf` 產生合規 `%PDF-` 二進位 |
| `test_r3_pdf_contains_student_header_metadata` | R3 | 驗證 PDF 包含學號、姓名、系所、入學年月等基本資料 |
| `test_r3_pdf_contains_summary_metrics` | R3 | 驗證 PDF 摘要包含總學分、已修得、有效學分、尚缺學分 |
| `test_r3_pdf_zero_debug_code_leakage` | R3 | 驗證 PDF 文字 0 處洩漏內部代碼與除錯前綴 |
| `test_r3_pdf_page_boundary_and_wrapping` | R3 | 驗證 PDF 在多頁下換行對齊不溢出頁面邊界 |

### Tier 2: 邊界與極端異常測試 (Boundary & Corner Cases)
| 測試案例名稱 | 測試焦點 |
| :--- | :--- |
| `test_tier2_empty_transcript_input` | 空成績列或空檔案輸入，安全停機回報清楚診斷 |
| `test_tier2_corrupt_course_names_and_strings` | 破損字串 `%%%`、特殊標記 `[◇]`、純數字 `12345` 之容錯排除 |
| `test_tier2_unusual_roman_numerals` | 罕見與小寫羅馬數字 `(VI)`、`(iv)`、全形 `（Ⅲ）` 之正確轉換 |
| `test_tier2_half_full_width_mixes` | 全半形括號混雜 `微積分（1）`、`普通物理學(２)` 之容錯正規化 |
| `test_tier2_zero_credit_courses` | 0 學分門檻課程（體育、輔導、服務學習）不虛增學分總額 |
| `test_tier2_failed_and_withdrawn_courses` | 不及格 (F) 與停修 (W) 實得學分為 0，不計入已修得學分 |

### Tier 3: 跨模組端對端協同測試 (Cross-Feature Interactions)
| 測試案例名稱 | 測試焦點 |
| :--- | :--- |
| `test_tier3_end_to_end_normalization_to_double_major_allocation` | 課名正規化 ➔ 雙主修規則比對 ➔ 配置 ➔ 網頁與 PDF 同步呈現 |
| `test_tier3_in_progress_course_flow_through_ui_and_pdf` | 修習中課程（成績「未」）全流程標記，顯示「修習中，完成後認列」 |
| `test_tier3_dual_program_credit_conservation` | 主修 + 雙主修跨系審查之嚴格學分守恆（無重複採計、無漏算） |
| `test_tier3_presentation_failsafe_scrubber_on_synthetic_leakage` | 防禦性過濾器對手動注入之未翻譯代碼實施強制清洗保證 |
| `test_tier3_cross_media_data_consistency` | 驗證 HTML 表格、CSV 匯出、PDF 報表三者在學分與狀態上完全一致 |

### Tier 4: 真實成績單驗收測試 (Real-World Application Scenarios)
| 測試案例名稱 | 測試焦點 |
| :--- | :--- |
| `test_tier4_chen_transcript_pdf_parsing_metadata` | 解析陳同學成績單 PDF 表頭學號、姓名、系所、入學年月、雙主修身分 |
| `test_tier4_chen_transcript_course_normalization` | 陳同學成績單課程正規化 (`微積分(I)`、`普通化學實驗(二)`、`儀器分析 (一)`) |
| `test_tier4_chen_transcript_ge_verification_no_warnings` | 陳同學 6 門通識課程 (12 學分) 歸入四大領域且無認列不足警告 |
| `test_tier4_chen_transcript_double_major_allocation` | `微積分(I)` 成功採計至物化系化學組雙主修必修 `微積分(一)` (3.0 學分) |
| `test_tier4_chen_transcript_clean_presentation_and_pdf` | 陳同學決策快照之網頁 HTML 與匯出 PDF 達成 0 處內部代碼洩漏 |

---

## 4. 測試執行與環境相容性說明 (Execution Instructions)

### 執行單一測試檔案
```powershell
pytest tests/test_e2e_requirement_suite.py -v
```

### 執行特定 Tier
```powershell
# 執行 Tier 1 功能測試
pytest tests/test_e2e_requirement_suite.py -k "tier1 or r1 or r2 or r3" -v

# 執行 Tier 2 邊界測試
pytest tests/test_e2e_requirement_suite.py -k "tier2" -v

# 執行 Tier 3 跨功能測試
pytest tests/test_e2e_requirement_suite.py -k "tier3" -v

# 執行 Tier 4 真實成績單測試
pytest tests/test_e2e_requirement_suite.py -k "tier4" -v
```

### 執行全專案回歸測試
```powershell
pytest tests/ -v
```

---

## 5. 漸進可測試性與基準狀態 (Progressive Testability & Baseline)

- 本測試套件為**純粹需求導向（Requirement-Driven）與不透明箱（Opaque-Box）設計**。
- 在實作完成前（Milestone 1–3 進行中），針對既有已知缺陷之測試案例（如 `微積分(I)` ↔ `微積分(一)`、通識 `identity_status` 誤降 `UNKNOWN`、6 大卡片尚未實作、PDF 未結構化表格排版等）將於基準執行時檢出預期失敗（Expected Failures / Regressions），作為後續實作代理人推動改進之客觀北極星。
- 在實作代理人完成 M1（解析與正規化提升）、M2（全面本地化與代碼消除）、M3（UI 簡約卡片與表格化重構）後，所有 4 Tier 測試將達到 100% 通過（Exit Code 0）。
