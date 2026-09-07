# 通識年度結構與正式IT/PE接線（Sol核定，父代理來源覆核）

111 source https://genedu.utaipei.edu.tw/var/file/18/1018/img/693734522.pdf p4（tmp/genedu-111-source.pdf）。112 source https://genedu.utaipei.edu.tw/var/file/18/1018/img/315234034.pdf p4。111明確8國英+四類16+共同2+可彈性補足2=28；112–11510國英（含英III）+四類16+共同2=28。

## 111通識flex2

shared.university_common.evidence_by_cohort建立cohort-scoped compulsory_total/courses/category_min_each/common_elective_min/flex_credits等compilecontract，兩個primary編譯函式用它而非global10。111國I/II、英I/II各2，不要求英III；112+保留5科10。

新增111唯一ge_flex排他性requirement2。其eligible_pool_ids直接包含本次實際四類pool與共同選修pool；同時五個來源requirement的overflow_routes指向flex canonical requirement ID。這樣已滿4的分類仍可再投入一門2學分，單門3學分也可分2補分類+1補flex。不另建GE28consumer，不shadow、不noncreditgate。

正確四類是藝術與美感、人文與文化思考、公民素養與社會探索、自然、生命與科技。按既有池ID生成，不使用Sol回覆中誤植的其他四領域名稱。公開catalog僅附原始categorymembership，無需ge_flex自身membership。GE來源全部excluded_from_free。

111英III不是必修，也不憑名字當成舊版共同選修；只有當期正式分類或正式替代證據可進相應GE池。

## IT正式registry（原只有corefixture）

111–115primary有requirement_id=university.it_application_design、kind=OFFICIAL_LISTED_COURSE_COMPLETION、requirement_type=non_credit、required_completions1、min_earned_credits_per_completion2、membership_id=university_it_direct_completion、affects_credit_ledgerfalse、waiver_allowedtrue。program==cs時requiredFalse/applicability_stateNOT_APPLICABLE。證據、coverage、automaticdecision與scope/provenance為本年度正式通識policy，科系/track/version明列；subject由實際evaluate context精確綁定，不寫死到registry。

waiver_authority_ids是server-owned官方通識中心授權清單，與Core已修strictwaivermatcher契約一致；沒有任意authority fallback。

## Math本系整批課程採認（與個案waiver分開）

Math113原PDFp65明列本系生自動帶入＋官方 https://genedu.utaipei.edu.tw/p/412-1018-4255.php?Lang=zh-tw 列Math本系必修C語言（1082-2核定）／必修Python（1132-3核定）。Sol依新原文改正先前「人人要個案函」結論：可對適用本系版本的已核定必修course建立PROGRAM_APPROVED_COURSE_EXEMPTION membership完成路徑，零額外學分，不要求學生另附個案函。

必須同時匹配Math本系主修適用版本、該年正式必修課（不是一般Math選修Python）、正式課程身分及已完成；跨系同名課或自述課名不能用此路徑。C/Python具體適用year/requiredset按來源與核准時點保存，不能把1132-3當任意某天生效；當as_of或條件不足時只該門檻需確認。個案waiver仍用subject/version/program/track/authority嚴格record。保留recognition_basis和官方頁/手冊來源，UI可分辨「本系核定課程採認」與「個案免修」。

## PE metadata

既有PEgate補membership_id=university_physical_education_completion、activity_membership_prefix=university_physical_education_activity:、affects_credit_ledgerfalse。各年門數/時數/每學期上限/不同活動照原policy，不另guess免修authority；沒有明確權責依據不開auto waiver。

## 驗收

111兩種flex来源（分類/共同）皆28正例、已滿來源仍直接填flex、3credit拆2+1守恆、缺英II不由英III頂替。112–115保持10+16+2且無flex。新ITgate真正在所有primary registry，有正式publicmembership可PASS而CSNA。Math核定必修本系路徑PASS、他系/選修Python不自動；個案waiver缺scope/authority不PASS。PE四活動來源確認可計，英文III體育不是PE。所有exclusive只計一次。
