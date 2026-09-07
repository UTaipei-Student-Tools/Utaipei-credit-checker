# UI 第一批暫停點與剩餘驗收

UI工作者已落地 app/sidebar/snapshot_renderer/snapshot_exports/ui_components 與部分測試。主代理為優先修正正式parser錯誤，於2026-09-05 17:49左右中斷其未完成批次，沒有回復任何修改。

## 已觀察

- 本機 Streamlit 127.0.0.1:8505，程序session 18086，fileWatcherType=none；最終驗收前重啟避免cached module。
- CUA in-app browser tab2，1280x720。header已縮成單行，但設定仍全直排，入學年度控制項y490，第二手冊y600，主修/資料匯入皆在首屏下。
- app使用新build_student_pdf/build_student_allocation_csv；舊machine exporter保留。逐列編輯狀態已有中文雙向映射。
- 重複的『官方判定』原始狀態區塊已移除，集中由snapshot_renderer顯示。
- 重啟後用新tab3確認：UI工作者暫停前已把年度/手冊、主修/規劃類型改成雙欄（舊tab2是舊session畫面），這項不用重做。新server session 73878。仍有header→重複提示→設定caption→手冊caption等多層說明，主修欄位仍在y700；建議刪掉重複開始提示/設定caption/過多legend，把『手冊來源』折疊移到設定最後，讓主要四個控制項更靠前。不要僅放大空白卡片。

## 需收斂

1. desktop設定至少年度/手冊兩欄、主修/規劃類型兩欄；手機直排。移除重複大heading/多餘空白。可將特殊手冊override折疊，常態只選入學年度；務必保留原本明確設定語意和套用流程。
2. app._parser_confirmation目前忽略parse_diagnostics.fatal_warnings，只顯示PARSER_INCOMPLETE泛稱。請使用安全中文核對訊息，讓學生看見哪個總額不符；不要raw例外或個資。parser工作者維持complete/fatal/fatal_warnings相容。
3. tests/test_snapshot_exports.py需更新rendered文字斷言為中文，而保留machine JSON/legacy machine exports之完整性斷言。新增student PDF/CSV中文欄位、不露UNKNOWN/工程codes、數字守恆、公式注入與個資遮罩檢查。
4. tests/browser_acceptance.py尚未更新新student CSV/PDF/新renderer selectors。修正適用斷言，不可刪確認閘門、守恆、snapshot一致性、手機/主題/PWA/匯出檢查。
5. 確認 app editor 不把opaque attempt_group等內部欄位展示成主要內容，必要時隱藏而保留資料。
6. 主代理新增 tests/test_student_export_contract.py，並用tmp/inspect_student_exports.py確實發現學生CSV/PDF漏掉未配置課程：既有_s​​napshot fixture實得5、A課已配置3、B『普通課程』2未配置，但CSV只有A，PDF也無B。新增『尚未採計課程』可展開清單，顯示未分配/部分未分配/修習中/失敗等所有已確認來源；學生CSV/PDF同樣完整保留，別讓需要自由學分調整的課被隱藏。
7. 新學生CSV/PDF丟掉snapshot_id，雖然同一物件產生，無法與audit檔核對報表版本；以中文『報表編號』欄/頁腳保留（不必放在主要畫面），獨立測試已驗收。來源無課號不需要每門顯示『代碼待補』；未修課無學期也不需要叫學生補學期。

## 父代理預驗證

命令：pytest -q tests/test_snapshot_renderer.py tests/test_report_ui.py tests/test_snapshot_exports.py tests/test_app_snapshot_integration.py tests/test_settings_flow.py

49 passed、10 failed、21 subtests passed。
8項fail是tests/test_snapshot_exports.py::_assert_fail_closed_media仍要求HTML直接露CREDIT_CONSERVATION_FAILED，實際已顯示中文『學分來源與分配結果無法相互核對，請重新確認成績列』。
2項fail是core WIP EvaluationRequest漏application_event_evidence_id字段，已通知core工作者修正，不由UI處理。

不把第一批視為完成；后续由UI工作者依本檔接續，父代理再独立验证。


## 2026-09-05 真實 gate payload 的後續整合（待指派）

父代理逐行檢查發現 renderer/export fixture 與 service 實際欄位有落差：NonCreditRequirementResult 實際是 `evidence` / `coverage`，CSV `_student_non_credit_row` 只讀 `evidence_state` / `coverage_state`，會把已核實gate輸出為來源尚未核對。請以正式 evaluate_graduation 回傳 snapshot 做 roundtrip 測試，不僅手寫 fixture。

- 非學分／資訊完成gate詳情列出 matched_attempt_ids 對應課名、学期、状态、学分，不能只有學期。
- IT是完成一門 >=2 學分課的零耗用觀察，不是0學分課；文案用「門檻不另外增加學分，課程學分仍歸原類別」。
- generic subset新增 maximum_credits/observed_requirement_ids，Math111系選64外系cap15也是subset，不能全部硬標「自由學分子條件」或顯示15/0最低值。以中文表示「已採計x，上限y」，有minimum才顯示至少。
- gate coverage/evidence 真實欄位明確轉換，保留兼容老fixtures但不能捏造VERIFIED。
- 顯示相關 matched courses 與來源，無原始UNKNOWN／工程ID洩漏到學生HTML/PDF/CSV。
- Math領域canonicalIDs與sidebar signature見 tasks/math-track-and-public-catalog-design.md。


父代理追加完成：snapshot_renderer/_subset_progress_text支援maximum顯示「已採計x／上限y學分」，min仍保留；泛用heading改學分採計條件，不再把Mathdepartmentcap叫free。IT/非學分門檻中文改不另外增加學分、課程依原類別。snapshot_exports coverage/evidence真實欄位fallback已修。29 UI/exporttests +Ruff PASS（包含max在HTML/CSV/PDF三media）。尚需matched_attempt_ids課程明細join、Math專業領域selector、CS54rollup、scenario比較。

其他實際payload需修：SubsetResult沒有coverage_state/evidence_state欄位（只有status/source_reference等），_student_subset_row目前會無條件寫「來源尚未完整；來源尚未核對」，即使正式subset已PASS。不可虛構資料缺口；有實際fields時照fields，缺fields時只說明「依列示規則來源」或joinownerrequirement實際provenance，不因PASS臆造完整度。未來CSdomain minimum_course_count結果要顯示門數而不是0/0學分。
父代理後續完成 matched_attempt_ids 明細 join：HTML／PDF／CSV 共用 _matched_gate_courses + _gate_course_text，依 immutable snapshot attempts 顯示課名、學期、修課狀態與課程學分，不重新計算。SubsetResult 無完整度欄位時僅顯示「依列示規則來源」，不捏造來源缺口。29 個報表測試與 scoped Ruff 通過。仍需正式 evaluate snapshot roundtrip、Math領域、CS54、scenario及CS門數進度。
父代理已接Math113+ sidebar canonical domain selector（無預設；未選disabledApply；更換handbook清選；non_teacher說明）；app擋空primaryID/113+bareMathID，不送未選領域分析。既有settings13PASS，新Mathdomain AppTest等Data完成canonicalrecords再跑。_subset_name已將正式无name結果的science_college/external/math_alpha轉中文，其他fallback不露internalID；30renderer/exporttestsPASS。額外scenario比較依使用者加速要求暫緩。

2026-09-06 Parent CS54展示完成：正式115CS snapshot compile consumer sum128；12甲32+1乙22共54作presentation-only collapsible group，HTML點開甲/乙實際requirements，不新建creditconsumer。PDF有54摘要；CSV沿各requirement加中文甲/乙類標籤不增加摘要ledgerrow。Core未完成CSdomain門數降低故不宣称CSacademic PASS。ActualCSmedia regression PASS；另補所有正式primary bucket中文，_requirement_kind_label注意snapshotserialized無kind時走bucketfallback，不能只改explicitkind。Math資訊adapter55parentPASS+Sol無blocking finding；Mathsubsetcompiler下一批Core負責。

Parent補充UI完成：正式statistics128修復後，新增registry non-consuming total descriptor連動總進度（128/128、尚缺0）；圖表F1各正式bucket中文化、F7類數超限時僅隱藏可選卡片。實際HTML測試以BeautifulSoup可見文字驗中文狀態，保留CSS data-status內部鍵以免破壞既有主題樣式。正式整合4PASS、其餘projection/snapshot/student-export68PASS，scoped Ruff PASS；等待整套瀏覽器驗收，不新增scenario。
