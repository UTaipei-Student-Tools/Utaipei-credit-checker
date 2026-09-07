# 學分查詢優化執行計劃

使用者已核准 2026-09-05 計劃並要求開始實作、實測及更新既有 Hugging Face Space。
同日追加授權：同步完成版本至 GitHub 既有同名儲存庫。已確認實際組織為 `UTaipei-Student-Tools`（單數 Student），儲存庫為 `UTaipei-Student-Tools/Utaipei-credit-checker`；不得誤用個人其他專案。
GitHub 初始 main 為 `d950d3382a5e1c802005138d71d5460a73ba4928`，已有完整原始版與自動 force-push 至組織 HF 的 workflow。使用者已明確確認 HF 只更新 `Sapphirejimmy/Utaipei-credit-checker`。此次 GitHub commit 使用 `[skip ci]` 跳過既有錯目標同步工作，不變更另一個 Space，也不另設服務或憑證。

## 產品目標

- 111–115 年度的地生、物化物理/化學組、資科、數學：主修、雙主修、輔系依各自適用手冊。
- 首頁簡潔，學分類別可深入查看已修、尚缺、修習中、需認定課程與規則來源。
- 學生畫面、PDF、CSV 不直接顯示 UNKNOWN 或工程代碼；不確定事實仍保留，提供具體中文原因與處理方式。
- 在官方允許的分類間自動配置，總學分守恆。合法多解與證據不足分開，修課完成與行政核准分開。
- 成績單擷取、解析與帳號隔離優先。課表僅於資料來源與完整流程可靠時納入，否則正式入口不提供。
- 敏感檔、憑證、Cookie、真實成績不進部署包或日誌。

## 架構方向

沿用 Streamlit → 已確認課程 → graduation_service.evaluate → DecisionSnapshot → UI/匯出。
補齊 registry 到 RequirementSpec 的課程池/轉移映射；不以逐欄貪婪計數代替合法全域配置。
申請日期、入學年度、課表版本、規章修訂、生效日期各自保存。既有正式資格不因缺少歷史送件日期失效。
一組已驗證完整合法配置可證明可行；最省/唯一須有足夠搜尋證據。未建置規則不得冒充學生缺資料。

## 分工與順序

1. 主代理建立基準、真實擷取檢查、整合驗證與部署。
2. Sol 以既有唯讀審查完成核心契約，Terra 實作後再做重要規則/資料完整性複審。
3. Terra UI 擁有 app/sidebar/snapshot_renderer/snapshot_exports/ui_components 及其 UI 測試。
4. Terra Core 擁有 allocation_engine/graduation_service/application_resolution/decision_snapshot/snapshot_projection 及核心測試。
5. Terra Rules 擁有 curriculum_registry/handbook_rules/rules_config/research 規則來源及其測試，與 Core 先協調 course-pool 契約。

互不覆蓋寫入範圍。每個批次先有針對性測試，整合後再跑完整測試與瀏覽器。

## 驗收

- 各年度/系所/修讀身分的官方已知規則對照，有達標與未達標案例；來源未解的精確原因單列。
- 正式服務入口可合法跨類別配置，無重複計總學分、無未授權跨系兼充。
- 多解可行 witness、搜尋未完成、假官方證據、錯版本/錯學生分別測試。
- 真實校務成績下載成功並通過PDF及課程列完整性驗證；實測不留個資。
- 手機/桌面 UI 可讀、明細可展開、中文輸出、畫面/CSV/PDF統計一致。
- 部署 allowlist 無秘密，既有 HF Space 建置與部署後 smoke test 完成。
- GitHub 與 HF 正式程式內容一致；GitHub 另可包含不含個資的測試與部署工具，排除 HF資訊.txt、真實成績、tmp、虛擬環境及本機設定。
