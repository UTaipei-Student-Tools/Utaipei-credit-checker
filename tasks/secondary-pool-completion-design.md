# Earth／APC／Math 次修課程池完成設計

## 決策摘要

本文件只處理 Earth、APC、Math 的輔系與雙主修課程池。申請資格、核准版本、個案替代、免修證據及跨主修學分守恆沿用既有 service／allocation 契約。

目前 `_unresolved_target_pool_bundle()`（`curriculum_registry.py:3854-3985`）把 Earth 與多數 Math 雙主修建成空 pool；`_minor_catalog()`（`curriculum_registry.py:3283` 起）也把若干已知額度維持 PARTIAL。原始手冊已足以完成一般候選課程池：

- Earth 雙主修的 16 學分明載為「專業領域選修課程（不分領域）」，可使用同一學年度兩領域的正式專業選修列項聯集。
- APC 的 4／24／20 學分明載為同一組別的「其餘必修課程」，可使用同一學年度、同一組別主修必修表中未列為次修基礎課的課程。
- Math 輔系與雙主修頁本身已完整列出選修候選，應直接逐年轉錄；不能改用所有數學系開課的無界 department pool。

以上一般候選不需個案核准。只有官方註記明載的免修、替代或跨系認定才走既有正式 evidence gate。

## 共通編譯契約

1. 所有 credit requirements 使用同一 `EXCLUSIVE` ledger。同一 CourseAttempt 不得同時計入原主修、命名基礎課及剩餘 quota。
2. named requirement 只接受同 cohort 的正式課程 identity 或正式 equivalency；課名相同本身不是身份證據。
3. pool candidate 必須保存 `curriculum_version`、`program_slug`、`track_slug`、原始課名、學分、component、來源頁及 stable official identity。
4. 從 primary catalogue 重用候選時，只重用「課程身份與官方類別」，建立新的 secondary pool membership；不得重用 primary requirement ID，也不得把 primary quota 複製到 target。
5. 一般 source-backed candidate 不帶 `department_approval_required`。個案替代仍要求 subject/version/program/track/authority 完整綁定。
6. 規則來源已完整但 transcript 尚缺正式身份時，該學生結果為 UNKNOWN；不得因此把整份 registry rule 標成 PARTIAL。

## Earth

### 官方條款與年度頁

五屆條文相同：

| Cohort | PDF／印刷頁 | 輔系 | 雙主修 |
|---|---|---|---|
| 111 | PDF p.39／印刷 p.38 | 共同必修 24 | 共同必修 24＋專業領域選修（不分領域）16＝40 |
| 112 | PDF p.39／印刷 p.38 | 同上 | 同上 |
| 113 | PDF p.45／印刷 p.44 | 同上 | 同上 |
| 114 | PDF p.47／印刷 p.46 | 同上 | 同上 |
| 115 | PDF p.55／印刷 p.54 | 同上 | 同上 |

來源分別為 `tmp/handbook_official_111.pdf` 至 `tmp/handbook_official_115.pdf`。雙主修頁另明載課程應在原主修最低畢業學分以外加修，故 target 使用 exclusive credits，不建立 shared shadow。

### 最小編譯

#### 輔系

- 建立該 cohort Earth `common_compulsory` 中所有正學分 named requirements，合計 24。
- 候選身份直接取同年度 primary Earth 共同必修正式列項；不含 primary-only 的領域必修或共同選修。
- 頁面只要求「共同必修學分共24」，沒有把 0 學分的大學生學習／服務學習列為輔系完成 gate。secondary 不建立這些 zero-credit gates；不得用 primary gate 阻擋輔系。
- 無 remainder pool。

#### 雙主修

- 基礎 24 與輔系相同。
- 建立 `earth_secondary_domain_elective` quota 16。
- eligible candidates 是同 cohort primary catalogue 中 `earth_environment.domain_elective` 與 `life_science.domain_elective` 的聯集。原文「不分領域」明確允許跨兩領域選擇，不能要求先選一個 track。
- 排除 `common_elective`、兩領域 compulsory、自由選修及其他系開課；這些不是「專業領域選修」。
- 不要求個案核准；正式 catalogue membership 足以配置。

### 完整性

Earth 輔系及雙主修可由 blanket PARTIAL 升為 `VERIFIED / COMPLETE / automatic_decision=True`，前提是 primary Earth 同 cohort 的共同必修與兩領域選修 catalogue 已是 COMPLETE，且 service 能把正式 identity 映射到上述 secondary memberships。缺學生課程 identity 只影響該次判定。

## APC

### 年度、組別與基礎列項

111–114 兩組的次修表均列相同八門、合計 16：

- 普通物理學（一）3、普通物理實驗（一）1
- 普通化學（一）3、普通化學實驗（一）1
- 普通物理學（二）3、普通物理實驗（二）1
- 普通化學（二）3、普通化學實驗（二）1

115 改為每組各自的八門、合計 20：

- 電子物理組：普通物理學（一／二）各3、普通化學（一／二）各3、普通物理實驗（一／二）各1、微積分（一／二）各3。
- 應用化學組：普通物理學（一／二）各3、普通化學（一／二）各3、普通化學實驗（一／二）各1、微積分（一／二）各3。

次修頁是獨立 target 規則。111–114 主修的跨組實驗免修不得套用到上述明列的 secondary 八門。

### 額度契約

| Cohort | Track | 官方頁 | 輔系 | 雙主修 |
|---|---|---|---|---|
| 111 | physics | PDF p.10／印刷 p.9 | 基礎16＋其餘必修4＝20 | 基礎16＋其餘必修24＝40 |
| 111 | chemistry | PDF p.19／印刷 p.18 | 同上 | 同上 |
| 112 | physics | PDF p.10／印刷 p.9 | 同上 | 同上 |
| 112 | chemistry | PDF p.19／印刷 p.18 | 同上 | 同上 |
| 113 | physics | PDF p.11／印刷 p.10 | 基礎16＋其餘必修4 | 基礎16＋其餘必修24 |
| 113 | chemistry | PDF pp.23–24／印刷 pp.22–23 | 同上 | 同上 |
| 114 | physics | PDF pp.11–12／印刷 pp.10–11 | 同上 | 同上 |
| 114 | chemistry | PDF pp.23–24／印刷 pp.22–23 | 同上 | 同上 |
| 115 | physics | PDF pp.12–13／印刷 pp.11–12 | 明列20，無 remainder | 基礎20＋其餘必修20＝40 |
| 115 | chemistry | PDF pp.24–25／印刷 pp.23–24 | 明列20，無 remainder | 基礎20＋其餘必修20＝40 |

111–112 頁尾雖簡寫「必修課程應修4／24學分」，頁首總額20／40與可見16學分共同確定其為剩餘額度；113–115 使用「其餘必修課程」明文。這不是來源衝突。

### remainder 候選

- `apc_secondary_remaining_required` 必須綁定 cohort＋track。
- 候選為同 cohort、同 track 的 primary「專業必修／組別必修」列項，排除 secondary 表已明列的 base identities。
- 不納入該組專業選修、另一組必修、校共同、自由選修。
- 不要求一般個案核准。頁面以「其餘必修」指向同一組別既有必修表，足以建立候選 pool。
- 若學生用正式核准的非表列替代課補某門或補 quota，走既有 equivalency evidence；不能由相似名稱或任意系所欄位自動納入。

### 現行程式調整邊界

- 補齊 `_APC_PHYSICS_DM_ROWS` 的 111–114；現行只有 115（`curriculum_registry.py:722-732`）。
- `_apc_target_catalog()` 保留逐門 base requirements，但把 generic empty footer quota 改成有 `eligible_pool_ids` 的 remaining-required pool；現行 `curriculum_registry.py:964-1073` 將它誤當「完整目錄缺失」。
- `_minor_catalog()` 對 111–114 也使用同一 track remaining-required pool 4；115 不產生 remainder。
- base rows 與 remainder quota 相加即 target total，不再另建一個重複的 aggregate 20／40 requirement。

APC primary 同 cohort/track 必修 catalogue COMPLETE 後，以上 scopes 可升 COMPLETE；不需等待個案核准資料。

## Math

### 必修及總額

| Cohort | 輔系 | 雙主修 |
|---|---|---|
| 111 | 微積分（一／二）各4＋表列選修至少12＝20 | 必修21：微積分（一／二）4、線性代數（一／二）3、高等微積分（一）4、代數學（一）3；表列選修至少18；總計40 |
| 112 | 同111 | 同111 |
| 113 | 微積分（一／二）各4＋表列選修至少12＝20 | 現行必修14：微積分（一／二）4、線性代數（一／二）3；表列選修至少26；總計40 |
| 114 | 同113輔系 | 必修14＋表列選修至少26＝40 |
| 115 | 同113輔系 | 必修14＋表列選修至少26＝40 |

來源頁：

- 111：輔系 PDF pp.77–79、雙主修 pp.80–82。
- 112：輔系 PDF pp.72–74、雙主修 pp.75–77。
- 113：輔系 PDF pp.74–76、雙主修 pp.77–79。
- 114：輔系 PDF pp.77–79、雙主修 pp.80–82。
- 115：輔系 PDF pp.88–90、雙主修 pp.91–93。

111／112 的 21＋至少18＝39 並非矛盾。應同時保留 named-required 21、elective minimum 18、target total 40 三個條件；在沒有免修時，總額自然要求至少19選修學分。`total40` 是觀察同一 exclusive target ledger 的 aggregate gate，不另消耗40學分。

113 原頁的高等微積分（一）4與代數學（一）3已從必修刪除，並在同頁選修表重新列入。它們只屬 elective candidates。數學導論採修訂後3學分；刪除前4學分僅保留 provenance。

### 選修候選

- 每個 cohort 直接逐列轉錄 secondary 頁面的選修表。該表本身就是完整 candidate catalogue，不使用 primary 全系 elective union 取代。
- 每個 candidate 同時要求：命中該 cohort 表列 identity，且正式 offering 證明為本系所開課。這落實各屆修課須知「學分採計以本系所開課程為限」。
- 不接受只帶 `department=math` 的學生自述；正式 public/department catalogue membership 才可使用。
- 111／112 的數學軟體應用與實作 A／B／C 建一個 `max_courses=1, max_credits=3` choice group。
- 113 依修訂後名稱使用 Matlab／Python，兩者僅擇一採計3；舊 A／B／C 只作 amendment aliases/provenance，不與新課重複建候選。
- 114／115 的 Matlab／Python 同樣僅擇一採計3。
- 115 使用當屆名稱，例如微分方程、數值分析、應用統計方法、數學遊戲數位設計與實務；不得沿用114帶「（一）」或舊課名自動合併。

### 免修與補足

五屆均規定：三年內曾就讀數學相關系所、完成相當學分的表列必修者，可檢附成績與課綱申請免修；經本系核可的免修學分必須以其他選修補足。

- 這是個案 waiver/equivalency，不是 programme-wide 自動 membership。
- waiver 對 named requirement 產生零學分完成狀態；不得生成 credits。
- target total20／40仍要求實際 exclusive credits，因此被免修的學分自然由表列選修補足。
- 未附精確 subject、cohort、program、`track_slug=department`、authority 及 evidence reference 時不得通過。

### 完整性

Math 次修頁沒有未命名 remainder。逐年表格完整轉錄、修訂刪改按 operative row 處理、department-offering membership 接通後，可將輔系與雙主修一般規則升為 COMPLETE。免修學生缺個案證據只影響該學生，不應使整個 cohort registry 維持 PARTIAL。

## 真正未解與不應形成的 blocker

1. 本次來源沒有發現 Earth／APC／Math 一般剩餘額度的官方矛盾。
2. Earth secondary 頁沒有要求 primary 的0學分學習／服務 gate；不能把這項「來源未載」轉成阻擋所有輔系學生的 UNKNOWN。
3. APC「其餘必修」可由同年度同組 primary 必修表建立候選；不能因 secondary 頁未重印整張主修表而維持空 pool。
4. Math 的一般選修不需逐門個案核准；正式表列＋本系開課證據已足夠。只有免修／替代需個案核准。
5. 若正式 course catalogue 無法證明某筆 transcript 的開課單位或 identity，該筆匹配保持 UNKNOWN；這是學生資料證據缺口，不是 registry 規則缺口。

## 實作批次與驗收

### 批次一：資料與 pool builder

- 建立 Earth secondary common-required／cross-domain elective pools。
- 建立 APC cohort＋track remainder-required pools，補 physics 111–114 base rows。
- 將 Math 次修表逐年轉錄為 exact candidate rows及 choice groups。

### 批次二：替換 blanket unresolved 路徑

- `_course_catalog()` 對上述 scopes 回傳正式 named rows及 quota rows，不再落入 `_unresolved_target_pool_bundle()`。
- `_minor_catalog()` 使用相同 pool contracts。
- 保留 `_unresolved_target_pool_bundle()` 給真正只有 aggregate、無可引用候選來源的其他 scope。

### Targeted tests

1. Earth 每年 minor 共同必修24 PASS；DM 同一領域16及跨兩領域合計16皆 PASS；共同選修不得進16。
2. Earth primary 已配置的同一 attempt 不得再計 target；secondary 不因 primary 0-credit gate 缺失而 UNKNOWN。
3. APC 111–114 每 track base16＋同 track remaining4/24 PASS；另一組必修與專業選修不得補 remainder。
4. APC 115 minor 八門剛好20；DM 八門20＋同組其餘必修20 PASS；物理／化學實驗不得跨組誤配。
5. Math 111／112 必修21＋選修18只有39時 FAIL，補任一合法1學分以上 portion達40才 PASS；不得重算 total gate。
6. Math 113 高等微積分（一）與代數學（一）只可進 elective；四門現行 required 合計14。
7. Math 各年 Matlab/Python 或 A/B/C 超過一門時最多採計3。
8. Math 表外本系課、表列但非本系開課、同名不同學分均不得確定採計。
9. 精確核准免修完成 named gate但增加0學分；未補足20／40仍 FAIL。
10. 每個完成案例驗證 `credit_conservation=True`，且沒有任何額外 aggregate quota 重複消耗 credits。

## 附錄：Math 111／112 最低選修、總額與配置容量

### 決策

不新增 `allocation_capacity_credits`，也不建立第二個會消耗學分的 optional remainder requirement。現有 `RequirementSpec` 已把最低門檻 `credits_required` 與可配置上限 `max_credits` 分開（`allocation_engine.py:435-507`），配置時也確實以 `max_credits-current` 作容量（`allocation_engine.py:1698-1733`）。缺口在 service adapter 目前將每列強制編成 `max_credits=credits`（`graduation_service.py:1916-1939`），使 registry 即使提供較大容量也無效。

Math secondary 應編譯如下：

- `math-secondary-elective`：111／112 `credits_required=18`、`max_credits=40`；113–115 `credits_required=26`、`max_credits=40`。`max_credits` 是此 pool 最多可承接的 target ledger 容量，不是對外顯示的新畢業最低門檻。
- 各 named requirement 保持官方逐門最低及逐門 cap；waiver 仍只完成該 named gate並配置0學分。
- `math-secondary-total`：建立不消耗學分的 subset gate，`credits_required=0`，以 `minimum_credits=20/40` 觀察所有 Math target named requirement IDs與 `math-secondary-elective`。觀察式 gate 只讀既有 EXCLUSIVE portions（`allocation_engine.py:2281-2296`），不得再產生 allocation portion。
- total constraint 的 `membership_id` 使用 server-owned `math-secondary:<cohort>:eligible-target-credit`。所有已被正式證明可計入該屆 Math 次修的 attempt 都帶 VERIFIED membership；因此 total 只加總合法 target credit，不會把表外課或其他 requirement 混入。
- service adapter 只允許已清理的 server registry row 傳入 `max_credits`，預設仍為 `required_credits`；不可接受 request/UI 同名欄位。這是把既有 `RequirementSpec.max_credits` 接通，不是 allocator 公開模型變更。

此模型的結果：111／112 未免修時 named21＋elective18只有39，elective requirement本身PASS但total gate FAIL；再配置1學分合法選修後total為40而PASS。若一門4學分named requirement獲正式免修，named gate PASS但提供0學分；17學分實得named＋23學分合法選修才使total PASS。額外選修仍只在 `math-secondary-elective` 消耗一次。

### Math「本系所開課」的身份合取

對沒有課號／正式course ID的 transcript，次修表中的名稱與學分只能證明「列在候選表」，不能單獨證明實際開課單位；因此仍需 term-bound 官方開課資料證明該次開課屬數學系。現行 `_direct_match()` 對 `eligible_course_ids`、verified pool與 `accept_any` 採 OR（`allocation_engine.py:1433-1474`），不可把 handbook pool與 department pool並列在 `eligible_pool_ids` 假裝成 AND。

最小方案是在 service-owned catalog adapter 先做合取，再只向 allocator發出一個複合 membership：

- `math-secondary:<cohort>:<course-key>`：精確命中該 cohort secondary row，且具可信的 Math-owned course identity／開課證據。
- `math-secondary:<cohort>:eligible-target-credit`：上述逐課 membership 的聯集，供 elective quota及total gate觀察。
- 有穩定官方 course ID/code，且該 identity 的權威 registry 本身明確是 Math-owned時，可直接形成 VERIFIED複合 membership。
- 無 ID 時，必須以 `term + normalized exact name + credits` 唯一命中官方 term catalog，且 department/program owner為 Math，才能形成 VERIFIED。名稱學分命中但缺 term、同 term多筆、或開課單位缺失時為 UNKNOWN；完整官方 term catalog明確顯示非 Math 開課時才可形成 server-owned NOT_MEMBER。
- Requirement不得另列可繞過上述複合 membership的裸 `eligible_course_ids`／generic department pool。正式個案 equivalency仍可依既有精確核准 binding進入，並保留其證據鏈。

這個合取放在 adapter 而非擴充 allocator 的通用 AND predicate，可把變更限制在 Math secondary catalog compilation與既有 membership evidence資料流。

### 附加驗收

1. 111 named21＋合法elective18＝39：elective PASS、total FAIL；同一 pool再增加1學分後total PASS，recognized target credits恰為40。
2. 111 一門4學分named獲精確waiver：named PASS且allocated0；實得named17＋elective22仍FAIL，elective23才PASS。
3. 一門3學分選修跨越40容量時，allocator可只配置到40，其餘留為 unallocated/合法 overflow；守恆仍成立。
4. 無ID、同term同名同學分且官方Math開課唯一命中可PASS；只有handbook名稱命中但缺開課證據為UNKNOWN；官方明確非Math開課不得採計。
5. 同一 attempt 即使同時帶裸course identity與非Math開課資料，也不能因 `eligible_course_ids OR pool` 繞過複合 membership。


父代理來源準備：tmp/math-secondary-source-tables-111-115.json包含五年次修原始table rows、page text與PDFhash，供逐屆轉錄；不能直接當runtime或免除修訂刪線影像確認。

## 2026-09-06 Parent source draft + Sol113原圖複核

完整五年MathDM draft：tmp/math-double-major-catalog-draft-111-115.json；required111/112各6門21、113+各4門14；electives39/39/36/35/35，每列page/table/row/hash。113原圖74–79確認red刪除yellow替換，舊新不能並列OR；正式DM36，minor加線代I/II=38。刪除數學軟體A、幾何學、微分方程II、數理統計I、拓樸學；Matlab/Python都有且max3擇一；C仍有效。高微I/代數I從DMrequired移至elective。現有minor113誤列多個舊名並漏MatlabPython，須於secondary批窄修；請依parent draft current names，不從現有minor copy。
