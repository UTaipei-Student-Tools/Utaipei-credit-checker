# 校務成績單核對修正契約

## 已觀察問題

正式 supervised fetch、登入帳號與PDF學號比對、課名/學期、逐列確認均已實測成功。
AG102 表格本身沒有課號/開課單位；這是來源限制，不可虛構。

parse_transcript_pdf 內 extract_reported_totals_from_doc 只看「修習總學分數」下一個文字列。
實際表格有雙語/多層表頭，數字不是緊鄰下一列；找不到就回退到全文第一個「修習學分」，把單一學期數字誤當歷年總額。
total_reconciled 又用 parsed_total >= reported_total，因此低估門檻仍回complete=True。
parse_courses 的total_credit包含修習中，但正式表尾「修習總學分數」及「實得總學分數」不含修習中，須分開比較。

## 建議實作（只限解析與驗證）

- 用實際表頭座標/欄位對齊，取得明確的全歷年「修習總學分數」「實得總學分數」，不得將學期欄位當歷年總額。
- 解析總額分成：所有修課學分、已結束修課的修習學分、實得學分、修習中學分。依逐學期成績狀態計算，不用整門跨兩學期is_in_progress混算。
- 同口徑精確比對（小數容差），過多與過少都需顯示具體診斷。無總額欄位不得聲稱已核對，可保留成功解析狀態但reconciliation狀態為not_available。
- 多個衝突全歷年總額要明示衝突，不選最有利值。
- 回退y_tol重解析不得只選最大學分，應以同口徑總額與完整性選擇。最終選定courses之後重新計算全部診斷，避免stale parsed_total。
- 零學分F/W/停/低於及格分數不能is_completed=True；免修不增加實得。
- 免修/抵免語意須與 course_input_adapter 保持一致（免修實得為0；抵免僅正式登載實得可用），不要為讓總額相符而把缺資料抵免算成已取得學分。全表含抵免但缺正式實得時，明列核對限制，不能猜最有利數字。
- scripts/portal_live_smoke._verify_transcript_pdf 必須檢查parser fatal/complete/reconciliation，而不是有course rows就PASS。

## 測試

主代理已加入獨立驗收 `tests/test_transcript_reconciliation.py`：原解析器 12 failed / 6 passed，確實重現多層表頭、同口徑過多/過少、無累計、重複頁、衝突總額、零學分失敗問題。請保留這些觀察行為，增加必要邊界案例。`reported_total` 相容欄位語意改成明確全歷年修習總額，另可增加清楚分開的 totals/reconciliation 欄位。

用合成資料，不保存真實成績單或課程：例如15總修課，12已結束，9實得，3在修。
在第1頁放單學期修習學分；第2頁放雙語表頭與全歷年12/9，驗證讀正確欄位。
測包含不及格、在修、重複頁/超額、漏列、無總額、衝突總額、零學分未通過與資料關閉。
原診斷表尾座標暫存已於正式修正實測通過後刪除；後續重現使用合成fixture即可，不需真實成績。

## 目前基準測試

完整基準：528 passed、4 skipped、747 subtests passed；test_child_exception_crosses_only_as_stable_code一次在大量測試時timeout，單獨重跑1 passed。
測試檔頂層import sidebar/Streamlit，spawn double時重載UI可能造成3秒timeout。宜把spawn worker double移至輕量fixtures module，保留原本hard deadline與錯誤代碼assert；不要放寬正式逾時。

主代理已做更小修正：sidebar import 移到唯一使用它的測試函式內，Windows spawn 不再載入 Streamlit。原 deadline 不變，test_portal_hard_deadline.py 11 passed。解析工作者不需再修改此測試。
