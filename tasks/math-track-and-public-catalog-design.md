# Math 路徑與正式課程分類整合（Sol 最終設計）

父代理已獨立讀113 p.65／114 p.69／115 p.80，確認115有年度差異，以下是更正後契約。

## Math primary canonical IDs

113/114各三個：`primary:<year>:math:math_scientific_computing`、`:data_science`、`:math_education`。
115僅前兩個。111/112維持 `primary:<year>:math`。

| 年度 | 領域 | 領域必修 | 系選修最低 | 領域＋系選修 |
|---|---|---:|---:|---:|
| 113/114/115 | 數學與科學計算 | 7 | 58 | 65 |
| 113/114/115 | 數據科學 | 6 | 59 | 65 |
| 113/114 | 數學教育 | 3 | 62 | 65 |

皆non_teacher，總結構GE28＋共同20＋專業65＋自由15＝128。師資生尚未有完整教育規則 record，本批不開可誤用的師資選項。111/112共同36＋系選64＋GE28，不新增free15最低額。

使用既有primary_curriculum_id作唯一請求權威，不加可能與ID不一致的math_domain或teacher自述覆寫欄位。Registry parser、track slugs、build、pool、list choices一起接通。每record只載其領域必修，其他領域課可依官方目錄進選修。113+裸Math ID缺領域不能默默fallback聯集或第一個領域。

Sidebar在113+Math顯示「主修專業領域」必選selectbox，選項value直接canonicalID。未選先停設定並提示，不送混合evaluation；變更ID令設定signature/舊結果失效。記錄student_type=non_teacher並顯示非師資生路徑。

## 公開課程分類資料

父代理 `tmp/collect_public_ge_catalog.py` 已從公開 `https://my.utaipei.edu.tw/utaipei/ag_pro/ag304_index.jsp` 依觀察到的表單，整理 `tmp/public-ge-catalog.json`：111-1至115-1九學期、2272列、348課名、0個(term,name,credits)分類歧義。無登入、無學生/教師/教室欄位。單一資料集，不複製進每屆registry。

新增server-owned loader/store，schema public-course-catalog:v1、dataset_id/content_hash、covered_terms及rows。保留term/name/credits/hours/official_course_code/section/type/category/class/campus/source_ref/URL/active。停開row active=false。

Registry政策僅引用dataset/revision、allowed categories、category_to_pool_id、coverage_terms；service _compile_attempts前精確匹配後提供現有candidate metadata。Catalog證明開課身份與分類，不定義畢業額度。

### 精確匹配

1. term完全相同（無term/不在coverage不得fallback入學年或鄰學期）。
2. 有官方coursecode以term/code/Decimalcredits；section有值再核對。無課號以term/標準化exactname/exactcredits。
3. 多section只有所有classification一致才可VERIFIED；同key不同classification為CONFLICTED。
4. 自述category/pool/URL不覆寫server結果。停開課名不以廣泛刪字變正常課。
5. 國文/英文映射既有exact必修；四領域映射各pool、共同選修映射common pool。
6. 所有已確認GE/國英/PE都給 university_common_excluded_from_free VERIFIED membership，避免被灌free。
7. PE只接受official_category=體育類且0學分；`英文(III)：體育`是英文課，不能靠體育關鍵字誤判。
8. PE活動id=pe:<official_course_code>；有來源的exactname或anchored體育(羽球)同term可對官方羽球；相同code跨term仍同活動。數量/小時/每學期限制仍由各屆規則定義。

Loader驗證term格式、有限非負credits、official category allowlist、HTTPS官方host、唯一source_ref、hash。Snapshot只留實際命中courseidentity/category/membership/source/evidence，不能帶2272列catalog。

### 驗證

不同term同名不同category不能跨期混用；無ID唯一匹配可VERIFIED；資料歧義/缺term不冒認；PE與英文名稱反例；GE排free；samePEcode仍同活動；真Earth正常無ID成績完整GE與4不同PE可判斷，已知不缺metadata不應全待確認。

## 111/112 額外必要子條件（父代理原文核對）

111原PDF p69(4)、112 p64(4)明文：「非師資生系選修至少64學分，其中甲類選修至少15學分方能畢業。」這15是系選64中的subset，不是額外consumer。兩年Mathdepartment_elective64添加math_alpha:<cohort> minimum_credits15，觀察該64exclusiveallocation。候選需按本年度完整甲/乙表附membership；缺甲15不得PASS。領域30/31證書則非所有非師資生畢業必要條件，不另加。

113–115改為所選domainrequired+elective65，沒有非師資生甲15硬門檻，不把111/112借過來。111/112本系C免資訊的自動帶入註記同樣在p69/p64，不只113存在。114/115自由選修excluded教育學程文字有刪改，需原圖判斷正式保留/刪除範圍，不能從113拷貝。

## 主修逐課來源整理（父代理）

原始表格+頁文字+PDFhash已整併tmp/math-primary-source-tables-111-115.json，非runtime，只供轉錄核對。111p70–76、112p65–71、113p67–73、114p71–76、115p82–87；新版前一頁是修課須知續頁，沒有表格。

必修程式課：111p70/112p65/113p67 C語言程式設計3；114p72/115p82已Python程式設計3。不要錯把114也用C。113p67原圖計算機概論有刪線，改資訊科學與科學計算3（黃色highlight）；服務學習整列有刪線，不能建立required服務gate。C語言未刪。父代理已看tmp/math-113-required-67.png及math-114-required-72.png。

Math編譯接線注意：目前_primary_pool_bundle會將subset_maxima的non_teacher15與teacher11都列出；本批可選record是non_teacher，因此只編譯該record適用的15，不能把兩種studenttype約束同時套用成11。111/112把external_department_or_school_professional cap15附到dept64，另math_alpha:<year> minimum15；113+把externalcap15附自由池（最少15），豁免學程會員按已核定來源，未知不可冒認。需給明確membership_id和observed_requirement_ids，不能只保留subset_id/student_type卻無法執行。
