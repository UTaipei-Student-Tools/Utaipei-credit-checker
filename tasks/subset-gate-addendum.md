# Subset gate 最小擴充（Sol 唯讀設計後執行）

不建立第二份學分 ledger。沿用 RequirementSpec.subset_constraints、可信 membership 與完整 witness 搜尋。

## 資訊應用與設計課群（IT completion，2026-09-05 官方來源校正）

官方112-1清單 https://genedu.utaipei.edu.tw/p/406-1018-104384,r5.php?Lang=zh-tw 註3及第19、20筆明定包含專業選修，學分留原領域或類別。IT必須觀察全部已確認 attempts（包括未配置者），不是只看GE配置。

- requirement_id=university.it_application_design；kind=OFFICIAL_LISTED_COURSE_COMPLETION。
- required_completions=1；minimum_earned_credits_per_completion=2；completion_statuses=[COMPLETED]。
- affects_credit_ledger=false；waiver_allowed=true；108起適用，資科系NOT_APPLICABLE。
- membership_id=university_it_direct_completion；必須同實際修課term的正式IT清單、可信來源VERIFIED。
- 完成一門至少2實得學分；兩門1學分不得合併。修課中／不及格／停修不計完成。
- 觀察全部completed CourseAttempts，包含GE／專業／free／unallocated；不新增CreditPortion，原學分仍只配置一次。
- 無課號 exact normalized name + exact credits + term，只在所有候選皆正式列入同學期IT清單時VERIFIED。不得跨學期借用名單。
- https://genedu.utaipei.edu.tw/p/412-1018-4255.php?Lang=zh-tw 的C語言／Python只證明可申請免修，不能自動完成。正式subject/version/requirement-bound、通識中心authority、APPROVED waiver才通過gate，產生零學分；GE28仍須足額。
- 沿用non-credit completion觀察管線。observed_requirement_ids跨池subset擴充僅供Math上限等學分subset，IT不使用此機制。

## Math 外系／跨校上限

- 111–112 母池為系選修64／44，非師資上限15、師資上限11；不另創free15最低額。
- 113–115 母池為 free_total，minimum15、external subset maximum15。
- constraint: membership_id=external_or_cross_school_professional、maximum_credits、observed_requirement_ids=[明列母requirement]、excluded_membership_id=approved_credit_program_cap_exempt、source_reference。
- verified external 超額為 FAIL；verified+全部unknown仍不超額為 PASS；unknown身分可能造成超额才 UNKNOWN。
- 指定學程例外需正式 membership；跨校事前審核仍另需證據，不能因沒超15就自動准許。
- maximum限制應讓搜尋挑選合法候選，不能抹去free total requirement。

## 測試

IT專業課完成即使未配置也PASS且ledger不變；同名不同term不能借membership；兩門1學分不合併；修課中不算完成；CS免證明；Python無核准不免、正式核准不補GE26缺2。Math49內+15外滿64；18外加替代內課可選≤15；外系未知但全部≤cap仍可過；113+14free缺1/15足額。

## 主代理驗證既有批次

allocation/service/application/decision/projection 五組：175 passed、22 subtests（2026-09-05）。這僅驗證當前 policy/gate 批次；真實 Earth metadata 缺college/membership及GE分類仍須資料實作，不以合成5門正例冒充全手冊驗收。
