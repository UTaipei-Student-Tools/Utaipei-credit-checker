---
title: 北市大畢業通
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.57.0
app_file: app.py
pinned: false
license: mit
---

# 北市大畢業學分自我審查系統

這是一套以 Streamlit 製作的學分自我檢查工具，依據臺北市立大學 111–115 學年度理學院學生手冊，解析歷年成績單 PDF，將課程分類至校共同、通識、地生系主修、自由選修，以及支援的雙主修規劃模組。111、115 與非地生逐課資料不足的情況只顯示已核對門檻，結果保守標示 `UNKNOWN`，不猜測課程身份。

> 本工具提供個人規劃與初步核對，不取代教務處、系所或學分審查會議的正式認定。規則更新後，應先由熟悉校規的人員核對 `rules_config.json`。

## 功能

- 上傳歷年成績單 PDF，不必提供校務系統帳密。
- 在左側選擇入學 cohort 111–115；cohort 決定主要手冊，且不會被課表學年度或雙主修申請年度取代。
- 選擇地生（生命科學／地球環境）、物化（電子物理／應用化學）、資科或數學（115 標示為數據科學與數學），以及單主修／雙主修身分。
- 追蹤校共同必修、四類通識、體育、系共同必修、領域必選修及自由選修。
- 雙主修依校級「大二起至正常修業最後一年第一學期、至少40學分、共同課程最多6學分且須系所核准」規則顯示四狀態資格；各系更嚴格規定與申請證據仍須人工確認。
- 可登入校務系統抓取成績單與指定學期課表；此功能可能受校方維護、頁面改版或網路區域限制影響。
- 合併規劃中課程、模擬排課，並匯出 CSV。
- 報告以固定的 10 區塊下拉導覽切換明細，避免較窄畫面把後段分頁裁掉。
- 以 Lieflat F5 二十格圖呈現各門檻完成率；手機版保留可左右滑動的圖表與文字表格替代內容。
- 支援深色模式、手機／平板響應式排版，以及以定稿 UT 圖示加入 iOS／Android 主畫面（PWA metadata，不快取個人成績）。
- 畢業門檻由 `rules_config.json` 統一驅動；每個手冊年度都有獨立課名、學分、必選修與雙主修／輔系規則。
- 課程採「手冊年度＋學系範圍＋完整正規化課名＋正式學分」嚴格配對。例如 `微積分`、`微積分(I)`、`微積分(II)`、`微積分(一)`、`微積分(二)` 都是不同課程。
- 普物、普化、微積分等跨系課只會成為認定候選；必須逐筆綁定來源修課紀錄、目標必修、核准單位與證據，才可在最多 6 學分範圍內共同計入。舊版只填合計學分的資料不會增加畢業進度。

## 本機執行

需求：Python 3.10 以上。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

啟動後開啟終端顯示的本機網址，通常是 `http://localhost:8501`。

## 測試

```powershell
python -m unittest discover -s tests -v
```

測試涵蓋三個手冊年度隔離、課名與學分嚴格配對、科系別名範圍、含實驗課程、年度增刪、替代必修、成績狀態、非 PDF 防護、課表解析，以及分類前後總學分守恆。

## 隱私與安全

- 建議使用「上傳 PDF」模式。上傳內容只保存在目前 Streamlit 工作階段記憶體中。
- 即時抓取只在處理期間使用唯一暫存檔，讀回記憶體後立即刪除；不會留下學生 PDF 或寫入固定的 `student_transcript.pdf`。
- 校務帳密不會寫入專案檔案、規則檔或匯出檔。
- 請勿將真實成績單、匯出 CSV、`.env` 或 `.streamlit/secrets.toml` 提交到 Git；`.gitignore` 已包含這些規則。
- 管理員功能不再內建密碼。若要啟用，請設定環境變數或 Streamlit secret：`UTAIPEI_ADMIN_PASSWORD`。

## 更新畢業規則

主要門檻與課程清單位於 `rules_config.json`：

- `_meta`：結構版本、預設手冊年度與配對政策。
- `shared`：三個年度共用的校共同、明示安全別名、自由選修與體育設定。
- `handbooks.112`、`handbooks.113`、`handbooks.114`：已建置逐課規則；111、115 的門檻規劃與 PDF 頁碼引用由 `policy_audit.py` 提供，逐課結果保持人工複核。

雙主修校級規則來源：[臺北市立大學雙主修規定 PDF](https://reg.utaipei.edu.tw/var/file/31/1031/img/926/316980591.pdf)；資科系專題／認證門檻來源：[資科系規則 PDF](https://cs.utaipei.edu.tw/var/file/81/1081/img/1416/276427143.pdf)。

修改流程：

1. 取得校方最新正式規章並逐項核對。
2. 先備份 `rules_config.json`。
3. 在對應 `handbooks.<學年度>` 節點修改來源、門檻與正式課程清單；不要用全域模糊別名合併不同科系的同名或近似課程。
4. 若成績單只有可靠的格式差異，才在指定學系範圍加入明示別名，並保留 I／II、一／二、上／下、實驗與含實驗等課程身分資訊。
5. 執行完整測試。
6. 使用一份去識別化測試成績單人工核對分類結果。
7. 重新啟動 Streamlit；規則在程式載入時讀取。

## 專案結構

- `app.py`：應用程式入口與整體流程。
- `sidebar.py`：上傳、登入、身分與領域設定。
- `pdf_parser.py`：成績單 PDF 解析及課程狀態建立。
- `scraper.py`：校務系統登入、成績單與課表抓取。
- `schedule_parser.py`：課表 HTML 解析。
- `credit_engine.py`：課程分類與畢業門檻判定。
- `handbook_rules.py`：規則載入、課名標準化與門檻介面。
- `policy_audit.py`：cohort／系所門檻、雙主修資格、人工證據與來源引用。
- `audit_export.py`：含公式注入防護的 CSV／JSON 稽核匯出。
- `report_renderer.py`：審查結果、明細與匯出畫面。
- `ui_components.py`：共用視覺元件與響應式樣式。
- `schedule_planner.py`：模擬排課。
- `rules_config.json`：可維護的規則資料。
- `tests/`：不依賴真實個資的自動測試。

## 已知限制

- PDF 解析依賴北市大目前的成績單欄位位置；校方版面更新後可能需要調整欄位座標。
- 成績單目前沒有穩定提供開課系所與課號；完全同名、同學分但分屬不同系所，或抵免／採認個案，仍須由系所人工確認。
- 系統不使用子字串、編輯距離或關鍵字來猜測系所課程；沒有可靠學分的課表列也不會自動假設為 2 學分。
- 物化、資科、數學目前以已核對門檻規劃為主；成績單缺少課號／開課系所、人工核准或資科專題／認證證據時，系統不應宣稱已完成正式審查。

## 部署

Hugging Face Spaces 會依本檔案最上方的 YAML 使用免費的 Streamlit SDK 啟動，版本固定為 `streamlit==1.57.0`。安裝需求最後一行的本機 `streamlit_bootstrap` 套件會透過 Python `sitecustomize` 在 Streamlit 啟動前直接修補初始 HTML，寫入 `北市大畢業通`、iOS 主畫面名稱、manifest v2、UT 圖示與手機版 metadata；因此 iPhone Safari 的「加入主畫面」不需要等待 JavaScript 執行。升級 Streamlit 時必須同步重新檢查 patch，不可只放寬版本範圍。

PWA 圖示由 `static/icons/ut-graduation-v2-source.png` 產出的不透明 32／180／192／512 PNG 組成。系統不註冊 service worker，也不快取成績單或個人審查結果。若 iPhone 已加入舊捷徑，請先刪除舊捷徑，再用 Safari 開啟 Space 網址並選擇「分享 → 加入主畫面」；新捷徑名稱會預填為 `北市大畢業通`。

正式部署只需將本專案內容推送至原本的 Streamlit Space；repo slug 與公開網址不需變更。部署前請確認：

- 未包含真實學生 PDF、CSV 或帳密。
- `rules_config.json` 已經人工核對。
- `python -m unittest discover -s tests -v` 全數通過。
- 即時抓取功能在部署地區可連線至校務系統；若不可用，使用者仍可上傳 PDF。
