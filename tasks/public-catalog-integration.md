# 公開課程分類接入：Sol 精確介面契約

## 已整理、可直接使用的公開來源

- tmp/public-ge-catalog.json：2272列，111-1至115-1九學期，8類校共同課程（含國英/PE）。
- tmp/public-it-memberships.json：39列，112-1與115-1正式IT名單；catalog_matches精確join來源offering；所有39列已查得實際credits。
- tmp/public-it-professional-courses.json：112-1數位科技概論/資料視覺化各2學分，含正式course/class/selection code，來源官方公開課程查詢。
- tmp/public-science-catalog.json：四系同9學期本科正式課程，department_unit / college依真正sourceclass而非查詢所在班级。只非空college=理學院可形成science evidence；重複source_ref與GE資料應內容核對後去重，不能優先序猜。

所有資料只含公開課程學術欄位，沒有學生、教師、教室、帳號。正式runtime可整併成單一data/public_course_catalog.json與IT來源，含hash/schema/covered_terms，原tmp文件不部署。不要直接將公共列表塞進既有handbook metadata唯一性集合。

## 邊界

新增server-owned loader/resolver（public_course_catalog.py），在graduation_service._compile_attempts各列身份正規化後執行resolve_public_evidence；與既有handbook resolution兩軸分開，到CourseAttempt建構前合併。

索引term+officialcode+Decimalcredits，或term+exactnormalizedname+Decimalcredits；有可信原始section/selection/class欄位才縮小。不在termcoverage不fallback。多section只對每項屬性做all-candidate證明。來源HTTPS官方host/schema/hash/nonnegativefinitecredit/categoryallowlist/uniquesourceref驗證。

結果只回candidate_source_refs、public_identity_state、各自official_category_state/code/category、verified/uncertain_memberships、pe_activity_id。不建立requirement、requiredcredits或handbookcandidate。

Handbook curriculum-scoped official_course_identity仍是CourseAttempt.course_id，公共code只是alias；避免精確國英／系必修eligible_course_ids失聯。沒有handbookhit，公共allcandidates同code/name/credit才可VERIFYcourseidentity；多section同code不擋。

## Membership mapping

從本次已解析curriculum.course_pools按bucket找poolID，不硬編完整ID：國文/英文→university_compulsory（特定國英仍需官方handbookexactname/credit）；四GE正式category→ge_該類；共同選修→ge_common_elective；PE不進creditpool。上述全部國英/GE/PE給university_common_excluded_from_free VERIFIED。

CourseAttempt.pool_membership_evidence entries用(pool_id,state,source,kind=public_catalog)；不能信任request自己傳category/membership/source。正式四系professional source college給science_college evidence，department依officialsource；eligibility仍只由本屆手冊policy決定。

## IT與PE

IT offering先含專業2列。所有候選source_ref皆在同termIT名單→university_it_direct_completion VERIFIED；部分→UNKNOWN；全部不在不加，未覆蓋term仍UNKNOWN不借名單。112-1資料視覺化可能GE與專業兩候選皆IT：IT應PASS而GE仍待分類。

IT membership-only gate若沒有named/ID限制，可由可信、非legacy、具來源membership作gate relevant身份證明，不必整個course identity皆VERIFIED；named/IDgate仍按既有身份要求。coursecredits至少2、完成1門、無學分新增見tasks/subset-gate-addendum.md。

PE metadata：university_physical_education_completion、university_physical_education_activity:pe:<official_course_code>、excluded_from_free。RegistryPE配置membership_id / activity_membership_prefix，gate優先正式活動碼、fallback僅已核對alias。同code不同學期是同活動；英文(III)：體育不是PE。generic體育無活動仍只該gate待確認。

## 驗收

真實資料no-ID GE分類/排free、國英handbookID守恆、多section同類可核對、跨期不借、歧義各軸獨立、112-1兩專業IT含未配置PASS、部分IT候選UNKNOWN、4學期不同PEcodePASS/重複code不夠/英文體育反例、request自述無法冒認、總earned/exclusive不變。

最終須用實際Earth registry + 正式catalog課程構造一個完整128學分且門檻完成的合成成績，formal evaluate入口給可行畢業見證；不能只用5門任意OpenCourse toy fixture代替。Earth112+common12誤加問題另由Sol核實，等數據批次修正後才執行完整正例。
