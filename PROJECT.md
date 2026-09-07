# Project: 臺北市立大學學分計算與成績審核系統優化

## Architecture
- **Parser & Adapter Layer**:
  - `pdf_parser.py`: PyMuPDF 視覺排版與關鍵字解析，擷取學號、姓名、入學年月、系所、雙主修／輔系修讀身分、歷年修課表格。
  - `handbook_rules.py`: 跨系所通用正規化函式 `normalize_course_name`，正規化羅馬數字 `(I)`~`(VI)`、中文數字 `(一)`~`(六)`、半全形字元與空白。
  - `course_input_adapter.py`: 成績單資料適配器，標記 `COMPLETED` 與 `IN_PROGRESS`（成績為「未」者標記為修習中）。
- **Curriculum & Knowledge Base**:
  - `rules_config.json`: 全校與各學系歷年學生手冊之課程規則結構庫。
  - `curriculum_registry.py`: 形式化手冊規範目錄（地生系、物化系應化組、資科系、數學系等）。
  - `public_course_catalog.py`: 全校公開開課清單與通識四大領域目錄。
- **Audit & Resolution Engine**:
  - `allocation_engine.py`: 學分配置演算法與形式約束驗證，維持內部不可變狀態代碼。
  - `graduation_service.py`: 畢業資格審查協調器，整合手冊規則與公開課目錄（修正通識 `VERIFIED` 身分繼承）。
- **Presentation & Export Boundary**:
  - `snapshot_renderer.py`: Streamlit 網頁渲染器，負責 6 大指標摘要卡片、7 欄折疊表格排版、參數化中文轉譯與 Failsafe Scrubber。
  - `snapshot_exports.py`: PDF 報表與 CSV 匯出引擎，結構化文字表格排版與 100% 繁中字詞防溢出。
  - `sidebar.py`: 側邊欄控制項，自動帶入辨識之主修與雙主修組別。
- **Testing & Deployment Track**:
  - `tests/`: 包含單元測試、整合測試與新增驗收測試（`test_e2e_requirement_suite.py`, `test_m1_challenger.py`）。
  - Git Dual-Platform Remotes: Hugging Face (`origin`) 與 GitHub (`github: jimmymochi/utaipei-credit-audit`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | 羅馬與中文數字正規化 | `微積分(I)` ↔ `微積分(一)`、`普通化學實驗(二)`、`儀器分析 (一)` 空白消除 | M1 | R2 |
| 2 | 修讀身分精準辨識 | `pdf_parser.py` 解析表頭 `雙主修：` 與 `輔系：`，側邊欄自動預選雙主修系組 | M1 | R2 |
| 3 | 通識課程身分驗證修復 | `graduation_service.py` 繼承 `PublicCourseCatalog` 通識 `VERIFIED` 標記，消滅「身分尚不足以安全認列」 | M1 | R2 |
| 4 | 已修畢與修習中明確區分 | 成績「未」標記修習中，學分守恆，提示「修習中，完成後認列」 | M1 | R2 |
| 5 | 內部代碼與除錯前綴消除 | 杜絕 `REQUIREMENT_DEFICIT:`、`REQUIREMENT_EVIDENCE_`、`APPLICATION:`、`SEARCH_` | M2 | R1 |
| 6 | 冒號命名空間轉譯繁中 | `handbook:113:...` 轉譯為中文書目引用（如「113學年度地生系手冊 第45頁」） | M2 | R1 |
| 7 | 審查狀態與待辦繁中轉譯 | 參數化轉譯「地生系專業選修：尚缺 6 學分，請依系所規定選修」及防禦性過濾器 | M2 | R1 |
| 8 | 儀表板 6 大摘要卡片 | 總學分、已修得、尚缺、主修進度、雙主修進度、非學分門檻 | M3 | R3 |
| 9 | 7 欄折疊展開結構化表格 | 課名、學期、成績、修得學分、此類採計學分、採計類別、狀態／備註 | M3 | R3 |
| 10 | PDF 結構化報表排版 | PyMuPDF 對齊文字表格，杜絕文字溢出與代碼洩漏，100% 正體中文 | M3 | R3 |
| 11 | 全面自動化測試與回歸驗證 | pytest 單元與整合測試全數通過，新增陳同學成績單整合驗收測試 | M4 | R4 |
| 12 | GitHub 與 Hugging Face 雙平台部署 | Git commit 詳實，push 至 GitHub 及 Hugging Face Space | M4 | R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | 解析與正規化提升 (R2) | `handbook_rules.py`, `pdf_parser.py`, `graduation_service.py`, `tests/test_core.py` | none | DONE |
| M2 | 全面本地化與代碼消除 (R1) | `snapshot_renderer.py`, `snapshot_exports.py`, `equivalency_ui.py`, `sidebar.py` | M1 | DONE |
| M3 | UI 簡約卡片與表格化重構 (R3) | `snapshot_renderer.py`, `snapshot_exports.py`, UI CSS 與排版 | M2 | DONE |
| M4 | 測試驗收與雙平台部署 (R4) | `tests/`, git remotes (`github`, `origin`), 部署執行與驗證 | M3 | DONE |

## Interface Contracts
### `handbook_rules.normalize_course_name` ↔ `pdf_parser` & `graduation_service`
- Input: `name: Any`
- Output: `str`
- Behavior: 保留課程專有名稱與實驗／實習後綴；正規化括號內羅馬數字 `(I)`~`(VI)`、`(1)`~`(6)` 為中文數字 `(一)`~`(六)`；清除字串內部不合理空白。

### `pdf_parser.parse_transcript_pdf` ↔ `sidebar.py` & `app.py`
- Input: `source: str | bytes | BinaryIO`
- Output: `tuple[dict[str, Any], list[dict[str, Any]]]`
- Behavior: `student_info` 增加 `double_major` 與 `minor` 結構化欄位。

### `graduation_service._compile_attempts` ↔ `snapshot_renderer.py`
- Input: `courses`, `catalog`, `handbook_rules`
- Output: `DecisionSnapshot` 中的 `attempts`
- Behavior: 若手冊目錄未列出某課程但 `public_course_catalog` 判定 `public_identity_state == "VERIFIED"`，`identity_status` 設為 `VERIFIED`，不得降為 `UNKNOWN`。

### `snapshot_renderer` & `snapshot_exports` ↔ User UI & PDF Output
- Input: `DecisionSnapshot`
- Output: HTML string / PDF bytes
- Behavior: 通過參數化轉譯器與 Failsafe Scrubber，保證無任何 `REQUIREMENT_`、`APPLICATION:`、`SEARCH_` 或冒號代碼字串輸出。

## Code Layout
- `handbook_rules.py`: 規則正規化
- `pdf_parser.py`: PDF 成績單解析器
- `graduation_service.py`: 畢業審查核心服務
- `snapshot_renderer.py`: Streamlit HTML 呈現邊界
- `snapshot_exports.py`: PDF / CSV 匯出模組
- `sidebar.py`: 側邊欄設定
- `tests/`: 測試案例目錄
