# 時段查課與成績畫面整理

- 本學期課程先選星期、節次，再用開課單位及年級縮小範圍；無成績單也能查。
- 資料為使用者提供的 2026-09-07 博愛校區 115-1 快照，1,910 列，非即時名額或資格判定。
- 原始爬蟲資料不修改；只輸出白名單顯示欄位，不含登入資料、互動操作參數。
- 移除主流程的重複匯入預覽；保留成績一覽，編輯表預設收合。依 Impeccable distill 流程保留原有視覺。
- 解析快取加版本、重解析清理舊編輯狀態；顯示具體錯誤欄位。資料不完整及手冊不符不能因改一列就繞過。
- 使用者 56 列 / 89 學分的原始錯誤未取得；不可聲稱已證實其根因或已修復該份資料。

## 驗證

`python -B -X utf8 -m pytest -q tests/test_input_confirmation.py tests/test_course_input_adapter.py tests/test_course_display.py tests/test_app_snapshot_integration.py tests/test_semester_courses.py`

結果：65 passed, 4 subtests passed。

本機瀏覽器：星期一整天 233 列，第一節 31 列；手機視窗與頁面寬度均 390。
匿名 PDF 可按確認，重複匯入預覽為 0。真實使用者成績待提供錯誤原因後重現。
介面檢測僅標出未再呼叫的舊預覽函式既有色彩，新增介面未加入顏色。

## 重建課程資料

`python -B -X utf8 scripts/build_semester_catalog.py ../爬蟲/data_115_1_boa data/semester_courses_115_1.json`
