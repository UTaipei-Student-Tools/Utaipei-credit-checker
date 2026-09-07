# Sol 核定的第二批實作契約

兩條管線：non_credit_requirements 是獨立非加總gate；official policy由可信registry編譯pool membership。沿用現有allocator守恆及witness，不用accept_any，不靠任意文字關鍵字。

## Policy編譯

_safe_course_pools保留selection_rule、policy、required_credits與完整安全provenance；_safe_curriculum保留non_credit_requirements。
白名單僅official_category_policy及official_open_elective_policy。
每policy有policy_id/revision、applies_to(curriculum_versions/program_slugs/track_slugs/roles)、predicate、VERIFIED/COMPLETE/automatic_decision、官方source_reference/URL/page/clause。來源適用不明顯示RULE_POLICY_SCOPE_UNVERIFIED，不改成學生少資料、不回填鄰年。

通識分類：官方source category欄位/經來源核實的官方結構標記、官方逐課catalog唯一exact title+credits，或subject/attempt-bound正式分類紀錄。shared.ge_categories中的『藝術/文化/歷史』泛關鍵字只能找候選，不能做正式分類。舊credit_engine有成績單[通選公民]等標記解析，但目前使用substring/keywords，不能直接照抄其不安全判斷；需官方標記白名單及精確界線。

自由選修：已通過、正學分、未被其他EXCLUSIVE消耗且不落入官方列明排除項目的確認修課，可加入已核實open pool；不需要課號/開課單位。原始request不能自帶可信pool，僅service根據registry政策產生。
Named match仍須identity VERIFIED；policy pool match只需該membership可信，不能被不相關的named identity UNKNOWN擋住。

## 自由學分子條件要進搜尋

不要將free15拆成science3+remaining12，否則science metadata缺失會錯把已確定的free15卡成12。
一個EXCLUSIVE free_total=15，其RequirementSpec含subset_constraints，例如constraint_id=science_college_minimum、membership_id=science_college、minimum_credits=3。
subset只查同一批配置進free_total的EXCLUSIVE portions，不另產生CreditPortion。搜尋評分/合法完整witness必須同時滿足15+子条件，不能先任意填15再事後誤判science FAIL。

每個membership獨立有pool_id/state(VERIFIED或UNKNOWN)/source_reference，不能只共用一個pool_evidence_state。兼容舊接口但不能讓UNKNOWN的特定membership被全局VERIFIED覆蓋。
- free VERIFIED + science UNKNOWN：free可計，science只候選。
- verified science已達門檻PASS；不足但加未知候選可達為UNKNOWN；覆蓋完整且相關課全確定不是science才FAIL。
- 4學分science課若exclusive用4，free與subset觀察皆4（門檻顯示3/3）；只用3則兩者3、餘1守恆處理，不造18學分。
- 對外單獨顯示free15/15與其中science3/3。

## 非學分管線

registry：requirement_id/kind/name/required_count/match(exact_titles, official_aliases)/completion_statuses/waiver_allowed/version/program/track/role/evidence/coverage/automatic/source。
一般COURSE_COMPLETION；PE用DISTINCT_TERM_ITEM_COUNT，另外required_completions=4、required_hours=8、hours_per_completion=2、max_completions_per_term=1、distinct_term_required、distinct_activity_required、title_base=體育、官方activity_aliases、applicability_basis/effective interval。

- 只count COMPLETED；FAILED/WITHDRAWN/停/未/NOT_TAKEN不算，IN_PROGRESS另列。
- 無課號可由適用scope+唯一exact normalized title+0學分匹配；必/選不作activity分類。
- 體育(羽球)採anchored parser，項目必須符合來源驗證的alias→canonical ID；以term↔activity最大匹配計合法門數，避免同學期兩門或同項目跨學期重複。4門且8小時PASS。
- generic體育缺項目只能證明學期有體育，不證明項目不重複；只PE待核對，不拖累其他學分。
- 正式subject-bound NON_CREDIT_WAIVER_RECORD可核准免修（target_requirement/authority/evidence/version/subject）；自述不等於免修。
- 永不建立CreditPortion，不改source/recognized/unallocated/shadow ledger。

service獨立NonCreditRequirementResult：id/name/kind/status/required_count/completed_count/completed_terms/in_progress_terms/matched_attempt_ids/waived/evidence/coverage/blockers/provenance/affects_credit_ledger=false。
primary_graduation合併credit_requirement_status + non_credit_aggregate_status + rule/evidence gates。
snapshot新增non_credit_results及subset結果/來源，decisions.primary_graduation保留non_credit_status。不要塞進純學分allocation.requirement_results；UI只讀snapshot，不重算。

## 來源範圍

15/3/4不允許程式default。Rules逐cohort/系組查證或提供明確applies_to校級assertion。
114/115通識手冊p5可證體育4門8小時、每學期一門、項目不重複；111–113需自己的handbook/適用性證據，不倒填114/115。113.12.25體育要點須驗證對舊cohort適用基準。

## 必要驗收

1. 真實AG102形狀完整Earth主修合成（缺碼/開課單位），滿必修/通識/free/science/PE/服務學習/輔導等後primary PASS。
2. 分別少必修、少一PE學期、缺science證據、少服務學習，精確缺口；free15可獨立確定而science待核對。
3. 15非science+後面3science，搜索必找free15/science>=3的合法解；12非science+4science同理，exclusive守恆15。
4. 4學期4項目PE PASS；重複項目不通過；同學期2項最多1；3具名+1generic待核對。
5. 任意自稱pool/category、錯scope政策不可產生可信membership；跨系同名不誤當named/science，但合法open free仍可用。
6. 來源scope缺口不消滅已確定其他要求。約50–70門正式evaluate性能/節點/搜尋耗盡/守恆資料。

Core工作者擁有engine/service/application/snapshot/projection及核心tests；Rules與UI各自獨立。UI需接收新non-credit/subset投影契約，不得自行推算。
