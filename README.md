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

# 北市大畢業通

「北市大畢業通」是臺北市立大學學生使用的畢業學分規劃與規則核對工具；加入手機主畫面後的短名稱為「畢業通」。它提供個人規劃與可稽核的初步判定，不取代教務處、系所或學分審查會議的正式認定。

## 固定網址

[Streamlit 固定網址](https://utaipei-credit-checker.streamlit.app/)

## 核心流程

所有畫面、圖表與匯出都使用同一份不可變 `DecisionSnapshot`，不在不同模組重跑規則或重新配置學分：

```text
PDF／校務系統／手動資料
        ↓
逐列確認 CourseConfirmation（未確認前不能正式分析）
        ↓
graduation_service.evaluate(...)
        ↓
DecisionSnapshot
        ├─ 響應式報告與科目展開明細
        ├─ 配置分布、畢業門檻與總學分統計表
        └─ PDF／CSV／規則與判定摘要匯出
```

全域配置器會依整體缺額，在手冊允許的用途間配置實得學分。它遵守學分總額守恆、必修要求、重修有效成績、共享上限，以及抵認與免修不憑空產生學分等限制。多種合法分法可以同時成立；一份完整、已驗證的配置可證明課程要求能滿足，是否已找到最省學分的方案則另外判斷。搜尋未完成、規則尚未建置、官方資料不足與需要學生補資料，會分別說明原因。

報告以簡潔總覽搭配可展開的表格。每門課列出最後配置的要求、實際使用學分、配置理由、其他候選配置、雙主修共享情況，以及待確認原因。每個要求（例如「已完成 6／9 學分」）都可以展開查看課名、學期、實得與採計學分、修課狀態、缺額、規則來源與判定理由；手機可在表格區域橫向捲動。

## 規則與手冊範圍

介面可依入學年度選擇 111–115 學年度適用手冊，並分別保存：

- 入學年度與主修適用手冊。
- 輔系／雙主修申請學期與申請年度。
- 輔系／雙主修目標課表版本；介面先選年度，再列出該年度的系所／組別。
- 申請狀態、校方核准狀態、是否正式取得資格，以及是否達到正式授予輔系／雙主修的畢業條件。

目前可選的主修、輔系與雙主修目標包括：

- 地球環境暨生物資源學系。
- 應用物理暨化學系－物理組。
- 應用物理暨化學系－化學組。
- 資訊科學系。
- 數學系（115 學年度為數據科學與數學系）。

`rules_config.json`、`curriculum_registry.py` 與 `research/` 保存規則來源、適用年度、原始條文或表格位置、核對狀態與人工確認原因。手冊修訂、程式規則及個人核准證據分開處理；無法確認的項目會說明原因，不直接當成學生未修課。

數學系目前依非師資生規則規劃。113–114 年須選數學與科學計算、數據科學或數學教育其中一個主修領域；115 年提供前兩個領域。111–112 年系選修64已包含甲類至少15與外系專門科目上限，不再另加自由選修15。資科系的系選修54則展開為甲類指定課程32及乙類22，並檢查當年度乙類領域門數。

公開開課資料另保存在 `data/public_course_catalog.json`，取自校方公開課程查詢，不含學生、教師、教室或帳號資料。查詢以修課學期、精確課名與學分，或官方課號比對；同名課的通識分類、開課系所與資訊門檻資格分別核對，不能用使用者自行填寫的分類取代官方資料。資料集涵蓋 111-1 至 115-1 的九個一般學期；暑修等未收錄學期不借用其他學期的分類。

資訊應用與設計的全校核定課程清單目前收錄 112-1 與 115-1。其他學期若無適用的系所核定免修依據，會提示補充認定資料。資訊門檻不另增加學分，原課程仍依其合法類別採計；生活輔導、服務學習與體育也各自檢查完成條件。

特別規則不以課名猜測：

- 普通物理、普通化學跨系抵認須有正式等同／替代依據。校務歷年成績單若未提供課號，仍可依指定手冊內唯一、精確的課名與學分核對同系課程；有同名歧義或講授／實驗差異時，會列為待核對。
- 化學組雙主修的微積分要求依目標課表年度判斷，不能把某一年度套用到所有 cohort。
- 同名課、改名課、跨系合開課、替代科目與等同科目都要有可追溯正式依據；講授課與實驗課不因名稱相似自動互抵。
- 免修、抵免或採認若沒有正式實得學分，不會增加配置學分。

輔系或雙主修的「已申請」只是使用者提供的狀態，不等於校方核准、正式資格或正式授予。雙主修共享學分必須先有來源端的有效配置，且符合正式規則與上限；沒有來源配置或無法核對時一律待確認。

目前採用的主要正式來源包括[學生手冊索引](https://curr.utaipei.edu.tw/p/412-1032-5.php?Lang=zh-tw)、[臺北市立大學雙主修規定](https://reg.utaipei.edu.tw/var/file/31/1031/img/926/316980591.pdf)與[資訊科學系規則](https://cs.utaipei.edu.tw/var/file/81/1081/img/1416/276427143.pdf)。來源未涵蓋的個案不會被推定為通過。

## 成績資料與隱私

- 可上傳歷年成績單 PDF；解析結果須逐列檢視並按「確認目前成績列」後，才可成為正式分析輸入。也可以手動修正辨識結果。
- 可選擇校務系統登入即時抓取成績單。正式套用前，會確認 PDF 學號與登入學號一致、解析完整且歷年學分對帳成功；不符時保留原資料。密碼不持久保存；登入憑證、Session Cookie、完整成績單與原始例外內容不寫入日誌。
- 解析會分別核對全歷年的修習學分與實得學分，區分修習中、已結束與通過課程；單學期合計不能代替全歷年總額。總額衝突、漏列、多列或抵免實得數字不明時，會顯示具體核對原因。
- 抓取失敗會顯示可理解的原因與復原方式，使用者仍可改用 PDF，或在確認表手動新增修習中課程。任何未確認或來源變更的資料都會阻擋正式評估。
- 公開畫面、錯誤訊息與匯出預設遮罩學號與姓名。自動測試使用合成成績單；另經帳號本人授權的校務實測，只回報核對狀態，不保存真實成績單或課程資料。

## UI、統計與匯出

介面使用 Noto Sans TC 與系統字型，提供真正獨立的淺色／深色主題。使用者明確選擇的主題優先於作業系統設定；版面處理 iPhone Safe Area、單一主要捲動區、44×44 px 以上操作控制與 375–1440 px 寬度，手機不需要開啟側欄即可完成入學年度、主修、輔系／雙主修及申請資訊設定。

配置分布、畢業門檻與總學分進度以預設展開的精確數字表呈現，課程列數與要求項目數分開顯示。無法核對來源守恆、官方門檻或配置數字時，會說明具體原因。表格、明細與匯出都由相同 `DecisionSnapshot` 產生，並帶有同一 `snapshot_id` 與統計 digest；獨立 HTML 報告也保留 SVG 進度圖。

## 部署架構

目前版本是 Python／Streamlit 伺服器應用，不能把同一份程式原封不動放到 GitHub Pages；Pages 只提供靜態檔案託管。若未來把 PDF 解析、規則配置、圖表與匯出完整移到瀏覽器端，靜態前端可減少伺服器重跑並提升多人讀取容量，但校務系統登入仍需要受控後端或本機輔助程式，不能把帳密與 Session Cookie 放在公開前端，也會受到跨網域限制。現階段仍以既有 Hugging Face Space 發布，效能以實際冷啟動與多工作階段 smoke test 驗收。

可下載：

- 適合列印的 PDF 報告。
- 課程配置明細 CSV。
- 可稽核的規則與判定摘要 JSON。

學生使用的 PDF 與 CSV 採用中文欄位、修課狀態與核對原因；規則與判定摘要 JSON 保留可供程式稽核的欄位。匯出保留配置理由、規則來源與待處理項目，套用公式注入與個資遮罩防護；匯出的數字與畫面使用同一份快照。

## PWA 與更新

`static/manifest-v2.webmanifest` 設定正式名稱「北市大畢業通」、短名稱「畢業通」、`display: standalone`、`start_url`、主題色與背景色。指定 UT 深藍學士帽／勾選圖示提供 favicon、Apple touch icon 180×180、PWA 192×192／512×512 與 maskable icon。

Service Worker 只處理必要的靜態外殼（manifest 與圖示等），不快取成績單、分析結果或其他個人資料。右上角三個點選單中的「更新至最新版」會檢查網站版本或新版 Service Worker、清理必要的前端快取並重新載入；只要本次工作階段仍有上傳檔、解析／手動列、活動或已確認輸入，或尚未匯出的分析快照，就會先提示，不直接丟失目前結果。使用者取消時不會更新 Service Worker、清除快取或重新載入。

## 本機執行

需求：Python 3.10 以上。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py --server.fileWatcherType none --server.port 8505
```

若要在本機修改 PWA bootstrap，可在安裝固定依賴後以 checkout 版本覆蓋套件：

```powershell
python -m pip install -e .\streamlit_bootstrap --no-deps
```

## 測試與瀏覽器驗收

單元與整合測試：

```powershell
python -m pytest -q
python -m unittest discover -s tests -v
ruff check .
```

`tests/browser_acceptance.py` 不是 pytest 自動收集的測試，必須在 Streamlit 啟動後明確執行。它使用合成成績單驗證主題矩陣、PWA metadata／manifest／Service Worker、確認閘門、UNKNOWN 判定、要求展開、三種匯出、更新防遺失提示，以及 375、390、414、橫向手機、768、1024、1440 px 響應式版面：

```powershell
python -m playwright install chromium webkit
python tests/browser_acceptance.py --url http://127.0.0.1:8505/ --browser chromium
python tests/browser_acceptance.py --url http://127.0.0.1:8505/ --browser webkit
```

部署到公開 Space 後，將 `--url` 換成正式網址並重新執行兩個瀏覽器 smoke test。WebKit 模擬可作為 Safari 行為檢查；它不等同於實體 iPhone 驗收。

## 專案結構

- `app.py`：入口、來源確認閘門與單一快照流程。
- `sidebar.py`：入學年度、主修、雙主修與資料來源設定。
- `pdf_parser.py`、`scraper.py`：PDF 與校務系統成績單資料擷取。
- `input_confirmation.py`、`course_input_adapter.py`：逐列確認、遮罩與來源狀態。
- `graduation_service.py`、`allocation_engine.py`：規則評估與全域學分配置。
- `decision_snapshot.py`、`snapshot_renderer.py`：不可變決策快照與報告明細。
- `lieflat_progress_chart.py`：F5／F7／F11 Lieflat Charts。
- `snapshot_exports.py`：PDF、CSV 與規則／判定摘要匯出。
- `curriculum_registry.py`、`handbook_rules.py`、`policy_audit.py`、`rules_config.json`：課表、手冊規則與來源稽核。
- `public_course_catalog.py`、`data/public_course_catalog.json`：經來源及雜湊驗證的公開開課分類與資訊課程證據。
- `ui_components.py`、`streamlit_bootstrap/`、`static/`：主題、響應式外殼與 PWA 資產。
- `research/`、`tests/`：規則研究紀錄與不含真實個資的自動／瀏覽器驗收工具。

## 更新規則的安全流程

1. 取得校方最新正式手冊、規章或系所公告，逐項記錄 URL、條文／表格位置與適用年度。
2. 更新對應 cohort 與目標課表版本，不使用全域模糊別名合併不同系所的同名或近似課程。
3. 為同名、改名、跨系合開、替代、等同、共享與抵認規則保留正式依據、核對狀態及人工確認原因。
4. 先跑單元／整合測試，再使用去識別化成績單跑瀏覽器驗收，檢查畫面、圖表與三種匯出使用相同 `snapshot_id`。
5. 證據不足時維持 `UNKNOWN`，不可用使用者自述、課名相似或舊年度規則代替核准證據。

## 部署到既有 Hugging Face Space

正式網站為 <https://sapphirejimmy-utaipei-credit-checker.hf.space/>，Space 為 `Sapphirejimmy/Utaipei-credit-checker`；同版原始碼同步至 [UTaipei-Student-Tools/Utaipei-credit-checker](https://github.com/UTaipei-Student-Tools/Utaipei-credit-checker)。部署前先通過完整測試與瀏覽器驗收，再以明確 allowlist 上傳程式、規則、PWA 靜態檔與固定依賴。`HF資訊.txt` 僅供本機授權測試與部署讀取，絕不提交、輸出或寫入日誌。

Streamlit 固定為 `streamlit==1.57.0`。PWA bootstrap 使用 `0.2.0`，部署依賴固定到不可變 artifact commit `593c7137262901b8cc1c5372d55d98888e66a83f` 與 SHA-256 `858a7d9fe2a82ea7d181dd9c3912b0021ab09c02838ebf0319cd876ba63c871e`。不可使用未固定版本、相對路徑或把 token 放進 requirements、Git 或 build log。

部署完成的驗收順序：等待 Space 建置、確認公開首頁載入、檢查 manifest／180×180 Apple touch icon／PWA 名稱／Service Worker／右上角更新選單，再以公開網址執行 Chromium 與 WebKit smoke test，並確認部署 commit 與本次程式碼一致。未完成上述公開驗證前，不得宣稱已部署完成。

## 已知限制

- PDF 解析依賴校方成績單欄位與版面；版面變更後可能需要重新核對欄位。
- 校務成績單版型可能不提供課號或開課系所；同年度、同系唯一的精確課名與學分仍可核對。只有受歧義、跨系抵認或缺少正式認定影響的條件列為待核對。
- 校務系統可能因維護、頁面改版或網路區域限制無法抓取；可改用上傳 PDF。
- 本專案的瀏覽器驗收使用自動化 Chromium／WebKit 與合成資料；沒有實體 iPhone、Safari 或 iOS PWA 的實機證據時，不宣稱已完成實機驗收。
