# 111–115 校共同、自由選修與體育政策來源對照

這份對照只記錄規則引擎需要的校級政策欄位。它不是學生畢業資格核定書，也不把通識課程名稱中的關鍵字直接當成正式分類。

## 校共同 28 學分

通識教育中心的[課程手冊頁](https://genedu.utaipei.edu.tw/p/412-1018-3380.php?Lang=zh-tw)列出各學年度手冊。本批逐年採用官方 PDF，並以該年頁面核對校共同結構：111 年為國文、英文必修 8 學分，四個通識分類各 4 學分（合計 16），通識共同選修 2 學分，再以 2 學分彈性補足至 28；112–115 年則為國文、英文必修 10 學分、四個通識分類 16 學分與通識共同選修 2 學分。

| 學年度 | 官方 PDF | 校共同來源頁 | Registry source reference |
|---|---|---:|---|
| 111 | [111 手冊](https://genedu.utaipei.edu.tw/var/file/18/1018/img/693734522.pdf) | PDF p.4 | `genedu:general_manual:111:common:p.4` |
| 112 | [112 手冊](https://genedu.utaipei.edu.tw/var/file/18/1018/img/315234034.pdf) | PDF p.4 | `genedu:general_manual:112:common:p.4` |
| 113 | [113 手冊](https://genedu.utaipei.edu.tw/var/file/18/1018/img/738224170.pdf) | PDF p.3 | `genedu:general_manual:113:common:p.3` |
| 114 | [114 手冊](https://genedu.utaipei.edu.tw/var/file/18/1018/img/659664717.pdf) | PDF p.4 | `genedu:general_manual:114:common:p.4` |
| 115 | [115 手冊](https://genedu.utaipei.edu.tw/var/file/18/1018/img/928/400409910.pdf) | PDF p.4 | `genedu:general_manual:115:common:p.4` |

這些是 `shared.university_common.evidence_by_cohort` 的年度 source contract；不得以理學院手冊、其他年度通識手冊或 shared/default URL 代替。通識分類的候選名稱仍須由官方課程目錄的分類欄位或 attempt-bound membership 核驗，`shared.university_common.ge_categories.categories` 只作搜尋提示。

### 111 通識彈性補足

111 年 PDF p.4 的校共同表是國文、英文 8 學分、四類通識 16 學分、通識共同選修 2 學分，另有 2 學分彈性補足至校共同 28 學分；來源為[111 學年度通識手冊](https://genedu.utaipei.edu.tw/var/file/18/1018/img/693734522.pdf)，Registry reference 為 `genedu:general_manual:111:common:p.4`。彈性補足是唯一的 `ge_flex` 額度 requirement，不另建立第二個校共同 28 學分 consumer，也不轉成非學分門檻。

彈性 requirement 直接接收四個正式分類 pool（藝術與美感、人文與文化思考、公民素養與社會探索、自然、生命與科技）及通識共同選修 pool 的超額；五個來源 requirement 的 overflow route 均指向同一個 `ge_flex` requirement。這保留 4 學分分類的最低額度，又允許已滿分類的 2 學分課程或單門 3 學分課程按 2+1 分配。五個來源與彈性額度均標記 `excluded_from_free`，不得灌入自由選修。

111 年共同必修只包含國文一、國文二、英文一、英文二各 2 學分；英文三不是該年度必修，也不能只憑課名取代當期正式分類或替代證據。112–115 年仍依各年手冊採國文、英文 10 學分，沒有 `ge_flex`。

## 資訊應用與設計非學分門檻

通識教育中心的[資訊應用與設計政策頁](https://genedu.utaipei.edu.tw/p/412-1018-4255.php?Lang=zh-tw)以 108 學年度起的適用範圍定義 111–115 年主修 IT policy。Registry 每年建立 `university.it_application_design` 的正式列項：完成一門至少 2 學分的列課，使用 server-owned `university_it_direct_completion` membership；該門檻不增加學分總額。逐年 source reference 為 `genedu:it_policy:108-onward:scope:<cohort>`，正式政策與實際學期課程清單分開記錄。

[112-1 官方課程清單](https://genedu.utaipei.edu.tw/p/406-1018-104384,r5.php?Lang=zh-tw)及其既有 public catalog 資料只涵蓋 112-1 與 115-1 的 semester membership；它們是課程身分 evidence，不是 111–115 共用的歷史政策來源。public catalog adapter 仍須依實際 term、課程身分與來源 evidence 提供 membership，未涵蓋學期不借用鄰期名單。

IT 列項的年度、主修、track、curriculum version、evidence、coverage 與 automatic decision 都寫入 registry，這些欄位是學生適用範圍與 waiver scope；課程供應的 membership 不要求帶上學生主修、track 或版本（`membership_program_required`、`membership_track_required`、`membership_version_required` 均為 `false`）。正式通識中心授權 ID 僅採 server-owned `official:genedu`，waiver matcher 仍要求評估 context 的 subject、版本、主修與 track 完全相符。資科系為 `NOT_APPLICABLE`，其他三系主修列項才是 required；這個 registry contract 不把 Math 本系自動採認或個案免修寫死在來源資料。

## 體育非學分門檻

五份本機官方理學院手冊的共同課程模組頁均直接寫明：`體育課程（大一、大二必修0學分，須修習4門不同科目名稱；體育學院、舞蹈學系及體育學系除外）`。

| 學年度 | 理學院手冊直接證據 | Registry 可執行欄位 |
|---|---|---|
| 111 | `3-理學院.pdf` PDF p.4（印刷 p.3） | 4 門不同科目名稱、0 學分；該頁沒有 8 小時／每門 2 小時／每學期一門文字 |
| 112 | `3-理學院 (112).pdf` PDF p.4（印刷 p.3） | 同上，採 112 source contract |
| 113 | `3-理學院 (113).pdf` PDF p.4（印刷 p.3） | 同上，採 113 source contract |
| 114 | `3-理學院 (114).pdf` PDF p.4（印刷 p.3） | 4 門不同科目名稱、0 學分；8 小時等補充見同年度通識手冊 p.5 |
| 115 | `3-理學院 (115).pdf` PDF p.4（印刷 p.3） | 4 門不同科目名稱、0 學分；8 小時等補充見同年度通識手冊 p.5 |

114、115 同年度通識手冊 p.5 另明載：`一、二年級體育為學期課程，須修習八小時零學分（每門二小時、合計四門）；除重修生外每學期一門且項目不得重複。` 因此 registry 只有 114/115 填入 `required_hours=8`、`hours_per_completion=2`、`max_completions_per_term=1`；111–113 保留 0／未載，不能把後年度條文倒填。五年都以本年 p.4 的四門不同名稱作 `DISTINCT_TERM_ITEM_COUNT` 的 4 項非學分 gate，且 `affects_credit_ledger=false`。

Registry 同時保留正式 membership `university_physical_education_completion` 與活動 membership prefix `university_physical_education_activity:`，並把 PE 列在 `excluded_from_free`。正式活動碼由 public catalog adapter 提供；本研究檔的 label alias 只用於可追溯的活動名稱提示，不構成跨年度免修或 waiver 授權。

活動名稱只建立有官方錨點的 label-only alias：[95 學年度通識手冊 PDF p.4（印刷 -40-）](https://genedu.utaipei.edu.tw/var/file/18/1018/img/794/96.pdf)可核實高爾夫、桌球、網球、羽球、游泳、籃球、排球等名稱；[羽球課綱](https://my.utaipei.edu.tw/utaipei/ag_pro/ag064_print_oth.jsp?arg01=109&arg02=2&arg04=19071411%2C05430.02&get_online=okey)另保留 `羽球`／`體育(羽球)`。這些來源只錨定活動名稱，不單獨宣稱 111–115 入學適用；alias metadata 的 `applicability_state=LABEL_ONLY`，不得由學生自行填寫系所身份放行。

## 自由選修政策

`free_total` 是一個 exclusive pool；固定課程與候選課程不得因同名或清單出現而重複計入。Earth／APC／CS 的規則是同一個 15 學分 minimum pool 加上 3 學分理學院院內 subset；Math 的頁面則是外系／外校專門科目採計上限，不能套用理學院 3 學分 subset。

| 系組 | 111–115 來源頁（逐年） | 原文要點與配置 |
|---|---|---|
| 地生（地球環境、生命科學） | 111/112 PDF p.26、詳細課程圖 p.30；113 p.31/p.35；114 p.32/p.36；115 p.40/p.44 | `自由選修課程至少15學分，可於本系、跨系或跨校選修，不含通識。其中至少選修3學分為理學院院內課程。` |
| 物化（物理組、化學組） | 五年各 PDF p.3、修課須知 p.6 | `自由選修課程至少15學分，可於本系、跨系或跨校選修，不含通識課程。其中院內選修至少3學分。` |
| 資科 | 111 p.113/p.115；112 p.108/p.110；113 p.103/p.106；114 p.108/p.110；115 p.119/p.121 | `自由選修課程至少15學分，可於本系、外系或跨校選修，其中至少3學分須為理學院院內課程，且不含通識課程、軍訓、體育。` |
| 數學 | 111 p.69；112 p.64；113 p.65；114 p.69；115 p.80 | `【自由選修】` 可選本系、外系或跨校專門科目；外系／外校採計至多 15 學分，111/112 師資生至多 11 學分、113–115 師資生至多 15 學分；排除通識共同必修／分類／共同選修、教育學程、大三大四體育、全民國防等，相同科目名稱僅採認一門，指定學分學程外系／外校例外。頁面沒有理學院院內至少 3 學分。 |

每一年度／系組的 `policy_source` 都保留該主修 section 的 source reference、官方 URL、PDF／印刷頁與研究矩陣。官方課程目錄尚未逐年度完整編譯時，registry 使用空 candidate 加上 verified policy predicate；這是待 membership adapter 編譯的實作缺口，不是官方規則不存在。`eligible_pool_ids` 只出現在額度／policy requirement；具名必修保留精確 `pool_ids`，候選課程 row 是 `candidate_only=true`。

## 主修非學分課程系列（111–115）

主修手冊的非學分列項由 registry 建立獨立的 `non_credit_course_series` 描述器，與學分課程池分開。每一列均為 `OFFICIAL_LISTED_COURSE_COMPLETION`，只接受 server-owned、逐學期核對的正式課程 membership；0 學分是課程列項的必要條件，不會增加或消耗任何畢業學分。`applicable_curriculum_version`、`applicable_program_slug`、`applicable_track_slug` 是選定課程表的適用範圍，不能當成學生自行提供的開課系所欄位。

| 系組 | 年度 | 生活學習與輔導 | 服務學習 | 主修手冊頁面 |
|---|---:|---:|---:|---|
| 物化（物理／化學組） | 111–114 | 8 個不同學期 | 2 個不同學期 | 111 p.6、p.15；112 p.6、p.15；113 p.7、p.18；114 p.8、p.19 |
| 物化（物理／化學組） | 115 | 8 個不同學期 | 主修表未列，不建立門檻 | p.8；服務學習缺列保留於來源紀錄 |
| 地生（地球環境／生命科學） | 111–114 | 8 個不同學期 | 2 個不同學期 | 111 p.27、pp.31–32；112 p.27、pp.31–32；113 p.32、pp.36、38；114 p.33、p.40 |
| 地生（地球環境／生命科學） | 115 | 8 個不同學期 | 主修表未列，不建立門檻 | p.41、p.48；服務學習缺列保留於來源紀錄 |
| 數學系 | 111–112 | 8 個不同學期 | 2 個不同學期 | 111 p.70；112 p.65 |
| 數學系 | 113–115 | 8 個不同學期 | 主修表未列，不建立門檻 | 113 p.67（服務學習整列刪線）；114 pp.71–72；115 p.82 |
| 資科系 | 111–113 | `大學生活學習與輔導 Part 1–8`，8 個不同學期 | 2 個不同學期 | 111 pp.115–117；112 pp.110–112；113 pp.107–108 |
| 資科系 | 114–115 | `大學生活學習與輔導 Part 1–8`，8 個不同學期 | 主修表未列，不建立門檻 | 114 pp.111–112；115 pp.122–123 |

生活學習系列每個主修課程表建立 `required_count=8`、`distinct_term_required=true`、`max_completions_per_term=1`；服務學習建立 `required_count=2`，採相同的不同學期限制。物化、數學與資科的服務學習表／注意事項另載每學期 24 小時、其中至少 12 小時為公共服務，registry 以 `required_hours=48`、`hours_per_completion=24`、`minimum_public_service_hours_per_completion=12` 保存這項完成標準；這些不是學生輸入時數。地生 reviewed pages 沒有可安全核對的時數數字，因此只保存兩學期完成數，不補填時數。

資科生活學習的正式列項名稱是 `大學生活學習與輔導 Part 1` 至 `Part 8`；其他三個系組只使用手冊列出的 `大學生活學習與輔導`。不以相似課名、跨年度清單或學生填寫的分類取代正式 membership。每個 active descriptor 的 membership ID 依下列格式由 server-owned catalog adapter 提供：

* `university_primary_life_guidance:<cohort>:<program>:<track-or-department>`
* `university_primary_service_learning:<cohort>:<program>:<track-or-department>`

物化與地生保留各自的正式 track；數學與資科使用 `department` 作為穩定識別段，但不要求開課紀錄攜帶學生 track。數學 113 的服務學習列項以 `amendment_action=DELETE` 保存來源刪線證據；物化／地生 115、資科 114–115 與數學 114–115 的缺列只保存 scoped omission provenance，均不產生 `required=false` 佔位列。輔系與雙主修 target 不套用這些主修 series。

## Registry policy contract

`course_pools` 中的 `official_category_policy` 與 `official_open_elective_policy` 均包含：

- `policy_id`、`revision`、`applies_to`（年度、系、組、`primary` role）；
- `predicate`（分類／exclusive free_total／science subset constraint，或 Math 的 maximum/exclusion semantics）；
- `evidence_state`、`coverage_state`、`automatic_decision`；
- 直接官方 `source_reference`、URL、頁碼、原文條款，以及完整 `policy_source`。

## 研究狀態與剩餘缺口

1. 共同 28、五年 PE 四門不同名稱、以及四系自由選修的數額／排除／Science College subset（Math 除外）已有逐年 source contract；PE 111–113 未載的小時／每學期限制刻意維持未填。
2. 通識分類 membership、自由選修的官方課程目錄 membership／跨校審核、以及各年度完整開課候選清單仍待 policy/membership adapter 編譯；不能把空 candidate 報成「官方未提供規則」。
3. Math 111/112 雙主修原文的總額 40、必修最低 21、選修最低 18 是共同 minimum constraints，可用必修 21＋選修 19 達 40，並非互斥衝突；registry 改為 `evidence_state=VERIFIED`、`coverage_state=PARTIAL`，剩餘只是逐課目錄／配置尚未完整建置。
4. 真正保留人工認定的列項衝突是 APC 111/112 化學組可見 16 與表尾 24 的語義、Math 113 表頭 14 與可見必修 21、Math 114 主修列項、CS 114 分拆，以及 CS 115 圖表額度／缺具名列項等。這些不是本批用共同政策常數修正的項目。
