# Graduation Planning

北市大畢業通以可追溯的學生身分、課程證據與規則版本，產生保守且可人工複核的畢業規劃結果。

## Language

**Admission Cohort（入學 cohort）**:
學生首次入學所屬的學年度，用來選擇原主修畢業手冊；它不是雙主修申請日期。
_Avoid_: 手冊年、申請年、目前學年

**Primary Curriculum（原主修課表）**:
Admission Cohort 所對應的原主修必修、選修、自由學分與其他畢業條件集合。
_Avoid_: 主修總學分、原系規則

**Application Event（雙主修申請事件）**:
學生提出或取得雙主修核准的實際學年、學期與狀態；它只在有明確紀錄時成立。
_Avoid_: 入學年、推定申請年

**Target Curriculum Version（雙主修目標課表版本）**:
加修系用來審查雙主修科目與學分的官方版本；除非法規或核准文件明定，不能只由 Admission Cohort 或 Application Event 自動推定。
_Avoid_: 申請年課表、入學年課表

**Course Attempt（修課紀錄）**:
學生在特定學年、學期修讀的一筆課程紀錄；同名但課號、開課系所或學期不同者仍是不同紀錄。
_Avoid_: 課名、科目

**Requirement（畢業要求）**:
官方課表或法規中的一個可稽核門檻，可能是指定課程、替代群組、課程池額度或人工證據。
_Avoid_: 分類、欄位

**Allocation（學分配置）**:
把 Course Attempt 的可用學分指派給一個 Requirement 的結果；除非有核准的共用證據，同一來源學分不能重複配置。
_Avoid_: 認列、抵免

**Equivalency Decision（等同性決定）**:
由明確權責單位與證據，把一筆來源 Course Attempt 綁定到特定目標 Requirement 的核准或拒絕結果。
_Avoid_: 同義字、模糊比對、自動抵免

**Evidence State（證據狀態）**:
規則或個案證據的可信程度，只能是 VERIFIED、CONFLICTED、MISSING 或 MANUAL_REVIEW；它描述官方證據本身，不等於程式已完整建置。未知資料不能當成零或通過。
_Avoid_: 已核對、應該可以、預設通過

**Coverage State（建置覆蓋狀態）**:
目前工具把某份官方規則轉成可逐課判定資料的完整程度，只能是 COMPLETE、PARTIAL 或 NONE；官方證據已 VERIFIED 仍可能只有 PARTIAL 覆蓋。
_Avoid_: 證據狀態、規則可信度

**Rule Resolution（規則解析）**:
分別解析原主修課表、雙主修目標課表、校級規章、申請公告與系所審查依據的結果；任何必要維度未解析或互相衝突時，必須留下 blocker。
_Avoid_: 手冊選擇、套用年份

**Decision Snapshot（判定快照）**:
一次規劃請求所產生的完整且不可變結果，包含規則解析、要求、學分配置、判定閘門、證據、警告與引用；畫面、表格、圖表及匯出必須讀取同一份快照。
_Avoid_: 報表資料、目前結果

**Graduation Verdict（畢業判定）**:
依目前課程、規則與人工證據得出的 PASS、FAIL 或 UNKNOWN；只有所有必要要求都有足夠證據時才可 PASS。
_Avoid_: 進度、預估可畢業

**Formal Award State（正式學位狀態）**:
由學校正式畢業審核與教務紀錄確認的學位／雙主修授予狀態；規劃器的 Graduation Verdict 不能代替它。
_Avoid_: 可畢業、規劃通過
