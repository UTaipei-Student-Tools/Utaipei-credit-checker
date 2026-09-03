# 臺北市立大學 111–115 學年度輔系規則證據矩陣

> 調查日期：2026-09-03  
> 範圍：地球環境暨生物資源學系、應用物理暨化學系電子物理組、應用物理暨化學系應用化學組、資訊科學系、數學系／數據科學與數學系。  
> 用途：提供「北市大畢業通」建立輔系規則、選擇流程與 fail-closed 判定。這不是校方個案審核或資格證明。

## 1. 結論先行

1. 校級《學生修讀輔系要點》只給共同底線；各系仍須另訂申請標準、名額、科目與學分並送教務處核備。學士班可在一年級第二學期至四年級第一學期申請，系所查核及系主任同意後，核准名單須送教務處登錄；核定後才得自次學期起修讀。[M1]
2. 學士班輔系至少 20 學分，但各系可提高：111–115 地生均為 24；APC、資科、數學均為 20。輔系學分應在原學系最低畢業學分外加修，原學系系訂必修不得兼充輔系；若因此不足，須由輔系指定替代科目。[M1]
3. 個人填寫「已申請」不是核准證據；完成課程也不等於正式取得輔系。正式結果至少要分開保存系所核准、教務處登錄、課程完成與學位證書加註。[M1]
4. 目標課表適用年度不能由入學年度、申請年度或目前年度推定。本次找到的校級要點沒有規定個案應套用哪一年度的目標系課表。系統應先選「目標課表年度」，再選目標系／組；未取得個案核准或校方可追溯依據前，適用性一律是 `UNKNOWN`。
5. 111–114 APC 兩組均明列 16 學分的八門基礎講授／實驗，另有 4 學分必修但沒有具名課程；因此只能確認固定 16／20，不能自動判定輔系完成。115 才改為每組各自完整列出八門共 20 學分，且兩組都明列微積分（一）（二）。[P111][P112][P113][P114][P115]
6. 111–115 資科均為 `計算機概論 3 + C 程式設計 3 + 本系其他開設課程 14 = 20`。原系已修上述課程時，改修其他資科課程須經資科系同意；不可由名稱相似或全域 mapping 自動替代。[P111][P112][P113][P114][P115]
7. 數學 111、112、114、115 的 20 學分結構完整；113 官方頁面保留多筆刪改，包含 `數學導論` 學分同時呈現 4 與 3，故涉及刪改列時必須人工確認。[P111][P112][P113][P114][P115]
8. 地生 111–115 的輔系均明定為該年度「共同必修 24」。信用分課程可以逐年追到共同必修表；但共同必修表同時含 0 學分課程，輔系學生是否也須完成這些 0 學分門檻，輔系頁沒有進一步說明，應另列人工確認而不能靜默忽略。[P111][P112][P113][P114][P115]

## 2. 證據與判定狀態

| 狀態 | 本報告用法 | 規則引擎可做的事 |
|---|---|---|
| `VERIFIED` | 官方文件在本報告採用的粒度上有明確、可重現的文字或表格 | 可建立候選 requirement；仍須通過個人適用年度、核准、教務登錄、成績與不重複計分等 gate |
| `PARTIAL` | 總量或一部分課程明確，但仍有未具名 bucket、適用範圍或必要條件不足 | 只顯示已確認部分；整體不得 `PASS` |
| `CONFLICTED` | 同一官方頁面有互斥數字、未清除的舊新版本或無法確定哪個值生效 | 保留兩個 assertion 與頁碼；涉及該列時輸出 `UNKNOWN／需人工確認` |
| `MISSING` | 在本次官方手冊、校級規章、系所公告範圍內未找到所需證據 | 不建立肯定規則；不得用相鄰年度或其他系規則補猜 |

`VERIFIED` 只表示「文件內容已核對」，不表示某位學生已獲核准、已正式登錄或已取得輔系。

## 3. 校級共同規則

| 規則 | 正式來源 | 證據狀態 | 系統門檻 |
|---|---|---|---|
| 各系可互為輔系；各系自訂申請標準、名額、科目與學分並送教務處核備 | 《學生修讀輔系要點》第 3 點 | `VERIFIED` | 找不到目標系該期申請標準時，資格只可顯示 `UNKNOWN`，不可解讀為「無門檻」 |
| 學士班自一下至四上可申請；核定通過者自次學期起修讀 | 同要點第 4 點 | `VERIFIED` | `application_year/semester` 與 `effective_year/semester` 分開；「已送件」不啟用正式輔系 gate |
| 依行事曆期限申請，經相關學系查核、系主任同意，核准名單送教務處登錄 | 同要點第 5 點 | `VERIFIED` | `department_approved` 與 `registrar_recorded` 都須有正式證據；使用者自述不得代替 |
| 學士班輔系為目標系指定的系訂專業必、選修至少 20 學分 | 同要點第 6 點 | `VERIFIED` | 20 只是下限；實際採各目標系該版本較高或更具體的規定 |
| 輔系須在原系最低畢業學分外加修；原系系訂必修不得兼充；不足由輔系指定替代 | 同要點第 7 點 | `VERIFIED` | 同一實得學分不能同時計入原系必修與輔系；替代課須有目標系核准 evidence |
| 所有輔系規定課程與學分及格才加註歷年成績表及學位證書；畢業時未修滿不加註 | 同要點第 9 點 | `VERIFIED` | `coursework_complete` 只能產生「待校方授予」；正式 `AWARDED` 需要校方紀錄 |
| 原系已可畢業但輔系未完成者，可申請放棄；放棄後課程是否改列原系選修由原系主任認定 | 同要點第 10、11 點 | `VERIFIED` | `abandoned` 不得保留輔系 PASS；改列原系選修需另一筆核准 evidence |
| 學則的畢業與延長修業仍回指輔系專門要點 | 《臺北市立大學學則》第 16 條 | `VERIFIED` | 不能只以總學分達標推導輔系授予；須走輔系專門 gate [S1] |

### 3.1 本次沒有找到的共同證據

- APC、地生、數學各申請學期的系級名額、審查方式、成績或年級加碼門檻：`MISSING`。
- 個別學生應套用哪一年度「目標輔系課表」的通則：`MISSING`。因此 `admission_cohort`、`primary_handbook_year`、`target_curriculum_year`、`application_year/semester` 必須是四個獨立欄位。
- 「同名課」「跨系合開」「改名課」可以無條件等同的通則：`MISSING`。課名相同只可成為候選，不能直接產生抵認。
- 資科 113-1 公告可證明該期學士班輔系為一下至四上、有意願可申請，仍需繳正式成績單／申請表及面試通過；它只適用該次公告，不可複製到其他年度或其他系。[CS-A113]

## 4. 111–115 × 目標系／組證據矩陣

頁碼均先寫 PDF 實體頁，再於括號寫頁尾印刷頁。每列的「自動化處置」假設尚未取得個案核准；因此即使課表 `VERIFIED`，正式輔系資格仍不是 PASS。

| 目標課表年 | 目標系／組 | 官方課程要求 | 位置 | 證據 | Fail-closed 自動化處置 |
|---|---|---|---|---|---|
| 111 | APC 電子物理組 | 八門基礎課 16；另「必修課程應修 4 學分」；總計 20 | [P111] p.10（p.9） | `PARTIAL` | 固定八門最多顯示 16／20；額外 4 未具名，整體 `UNKNOWN` |
| 111 | APC 應用化學組 | 與同年電子物理組相同；八門 16 + 未具名必修 4 | [P111] p.19（p.18） | `PARTIAL` | 同上；不能推定額外 4 是微積分或任何相鄰年度課 |
| 111 | 地生（系級，不分兩專業領域） | 輔系 = 共同必修 24 | [P111] p.39（p.38）；逐課 p.32（p.31） | `VERIFIED` | 依 111 共同必修建候選；0 學分門檻適用性另標人工確認 |
| 111 | 資訊科學系 | 計算機概論 3、C 程式設計 3、其他本系開課 14；共 20 | [P111] p.121（p.120） | `VERIFIED` | 其他 14 須有開課系證據；與原系必修重疊時須資科核准替代 |
| 111 | 數學系 | 微積分（一）4、（二）4；表列選修至少 12；共 20 | [P111] pp.77–79（pp.76–78） | `VERIFIED` | 套用本系開課、免修補足、A/B/C 軟體課僅擇一 3 學分 |
| 112 | APC 電子物理組 | 八門基礎課 16；另「必修課程應修 4 學分」；總計 20 | [P112] p.10（p.9） | `PARTIAL` | 固定八門最多顯示 16／20；額外 4 未具名，整體 `UNKNOWN` |
| 112 | APC 應用化學組 | 與同年電子物理組相同；八門 16 + 未具名必修 4 | [P112] p.19（p.18） | `PARTIAL` | 同上；不能從 115 反推微積分 |
| 112 | 地生（系級，不分兩專業領域） | 輔系 = 共同必修 24 | [P112] p.39（p.38）；逐課 p.32（p.31） | `VERIFIED` | 依 112 共同必修建候選；0 學分門檻另標人工確認 |
| 112 | 資訊科學系 | 計算機概論 3、C 程式設計 3、其他本系開課 14；共 20 | [P112] p.116（p.115） | `VERIFIED` | 動態 14 學分須驗證開課系；重疊替代需資科核准 |
| 112 | 數學系 | 微積分（一）4、（二）4；表列選修至少 12；共 20 | [P112] pp.72–74（pp.71–73） | `VERIFIED` | 本系開課；A/B/C 軟體課僅擇一 3；免修後仍須補足學分 |
| 113 | APC 電子物理組 | 八門基礎課 16；「其餘必修課程應修畢 4 學分」；總計 20 | [P113] p.11（p.10） | `PARTIAL` | 額外 4 的課名仍未列；最多自動確認 16／20 |
| 113 | APC 應用化學組 | 與同年電子物理組相同；八門 16 + 其餘必修 4 | [P113] p.23（p.22） | `PARTIAL` | 同上；不得把主修必修目錄任意挑 4 學分填入 |
| 113 | 地生（系級，不分兩專業領域） | 輔系 = 共同必修 24 | [P113] p.45（p.44）；逐課 p.38（p.37） | `VERIFIED` | 依 113 共同必修；專題研究／專業實習為 2 學分二選一 |
| 113 | 資訊科學系 | 計算機概論 3、C 程式設計 3、其他本系開課 14；共 20 | [P113] p.111（p.110） | `VERIFIED` | 其他 14 與替代仍需開課／核准 evidence |
| 113 | 數學系 | 微積分 8 + 表列選修至少 12；頁面保留多筆刪改，數學導論同時呈現 4、3 | [P113] pp.74–76（pp.73–75） | `CONFLICTED` | 不受刪改影響的課可建立候選；任何使用衝突列的完成判定為 `UNKNOWN` |
| 114 | APC 電子物理組 | 八門基礎課 16；其餘必修 4；總計 20 | [P114] pp.11–12（pp.10–11） | `PARTIAL` | 額外 4 未具名，整體不得 PASS |
| 114 | APC 應用化學組 | 八門基礎課 16；其餘必修 4；總計 20 | [P114] p.23（p.22） | `PARTIAL` | 同上 |
| 114 | 地生（系級，不分兩專業領域） | 輔系 = 共同必修 24 | [P114] p.47（p.46）；逐課 p.40（p.39） | `VERIFIED` | 依 114 共同必修；書報討論 2 取代前年度專題／實習必修列 |
| 114 | 資訊科學系 | 計算機概論 3、C 程式設計 3、其他本系開課 14；共 20 | [P114] p.116（p.115） | `VERIFIED` | 其他 14 與重疊替代須逐課證據 |
| 114 | 數學系 | 微積分（一）4、（二）4；表列選修至少 12；共 20 | [P114] pp.77–79（pp.76–78） | `VERIFIED` | Matlab／Python 僅擇一 3；免修仍須以其他選修補足 |
| 115 | APC 電子物理組 | 普物一二各 3、普化一二各 3、普物實驗一二各 1、微積分一二各 3；共 20 | [P115] p.12（p.11） | `VERIFIED` | 八門均須獨立配對；外系同名課只列候選，未核准不算抵認 |
| 115 | APC 應用化學組 | 普物一二各 3、普化一二各 3、普化實驗一二各 1、微積分一二各 3；共 20 | [P115] p.24（p.23） | `VERIFIED` | 化學實驗不能由講授或物理實驗替代；同名外系課仍需正式依據 |
| 115 | 地生（系級，不分兩專業領域） | 輔系 = 共同必修 24 | [P115] p.55（p.54）；逐課 p.48（p.47） | `VERIFIED` | 依 115 共同必修；不要沿用 111–113 的專題／實習或服務學習列 |
| 115 | 資訊科學系 | 計算機概論 3、C 程式設計 3、其他本系開課 14；共 20 | [P115] p.127（p.126） | `VERIFIED` | 規則與 111–114 相同但仍保存獨立版本；其他 14 須驗證開課系 |
| 115 | 數據科學與數學系 | 微積分（一）4、（二）4；表列選修至少 12；共 20 | [P115] pp.88–90（pp.87–89） | `VERIFIED` | 使用 115 改名後目錄；Matlab／Python 僅擇一 3 |

## 5. 可直接轉成規則資料的課程內容

### 5.1 APC

#### 111–114：兩組共同的已確認 16 學分

`普通物理學(一)3；普通物理實驗(一)1；普通化學(一)3；普通化學實驗(一)1；普通物理學(二)3；普通物理實驗(二)1；普通化學(二)3；普通化學實驗(二)1`。

- 111、112 表尾為「必修課程應修 4 學分」；113、114 為「其餘必修課程應修畢 4 學分」。四年度都沒有在輔系頁列出這 4 學分的課名。
- 引擎只能建立 `fixed_base_16` 與 `unnamed_required_4`。`unnamed_required_4` 不得用「任一 APC 課程」或主修必修目錄自動填滿。
- 111–114 的已確認八門沒有微積分；但因另 4 學分未具名，也不能反向宣告「微積分一定不算」。安全結果是 `UNKNOWN`，等待目標系書面指定。

#### 115：完整的組別版本

- 電子物理組：`普通物理學(一)3；普通化學(一)3；普通物理實驗(一)1；微積分(一)3；普通物理學(二)3；普通化學(二)3；普通物理實驗(二)1；微積分(二)3`。
- 應用化學組：`普通物理學(一)3；普通化學(一)3；普通化學實驗(一)1；微積分(一)3；普通物理學(二)3；普通化學(二)3；普通化學實驗(二)1；微積分(二)3`。
- 兩組的 115 課表不能共用一個無 track 的 rule ID；實驗 requirement 必須分別綁定物理實驗或化學實驗。

### 5.2 地生

輔系頁在五年度均說明「修讀本系之共同必修學分，共 24 學分」，沒有要求另選地球科學或生命科學領域。因此 UI 的目標是系級「地球環境暨生物資源學系」，不應強迫使用者再選地球／生命 track。

| 年度 | 24 學分的信用分課程 | 另列的 0 學分項目／人工注意 |
|---|---|---|
| 111–112 | 普通生物學學年課 3+3；普通生物學實驗 1；地球科學實驗 1；地球科學學年課 3+3；資料處理與分析 3；基礎生態學 3；環境影響評估 2；專題研究(一)／專業實習(一)二選一 1；專題研究(二)／專業實習(二)二選一 1 | 大學生活學習與輔導各學期 0、服務學習學年課 0；輔系頁未明說 0 學分 gate 是否全部適用 |
| 113 | 普通生物學 3+3；普通生物學實驗 1；地球科學實驗 1；地球科學 3+3；資料處理與分析 3；基礎生態學 3；環境影響評估 2；專題研究／專業實習二選一 2 | 大學生活學習與輔導 0、服務學習 0；是否為輔系非學分 gate 待確認 |
| 114 | 普通生物學 3+3；普通生物學實驗 1；地球科學實驗 1；地球科學 3+3；資料處理與分析 3；書報討論 2；基礎生態學 3；環境影響評估 2 | 大學生活學習與輔導 0、服務學習 0；不能把 113 的專題／實習二選一帶入 |
| 115 | 普通生物學 3+3；普通生物學實驗 1；地球科學實驗 1；地球科學 3+3；資料處理與分析 3；書報討論 2；基礎生態學 3；環境影響評估 2 | 詳細共同必修表仍列大學生活學習與輔導 0，但不再列服務學習；不可由前一年補回 |

課程原始表把普通生物學、地球科學各列為學年課 3+3；若成績單呈現（一）／（二），必須以課號、學期或系所正式 mapping 對應，不能只拆字串後直接認定。

### 5.3 資訊科學系

五年度課表結構相同，但應保留五份版本記錄：

```text
required:
  - 計算機概論 / Introduction to Computer Science / 3
  - C 程式設計 / C Programming / 3
other_cs_offerings_min_credits: 14
total_min_credits: 20
```

手冊註記：若學生在所屬學系已修上述課程，經資科系同意後，得修資科系其他開設課程補足。這代表：

- 原系必修已使用的同一實得學分不能再次餵給資科輔系。
- 替代不是全域 alias；必須保存資科系同意、被替代 requirement、替代課與核准學分。
- 「本系其他開設課程」需要課程開設單位／課號的正式資料，不能只用課名猜測。
- 資科公開的認抵申請表要求附成績單、課程大綱，並由系所審核小組逐門勾選同意／不同意及可抵學分，進一步證明 mapping 必須是有核准的個案資料。[CS-R]

### 5.4 數學／數據科學與數學

共同必修固定為 `微積分(一)4 + 微積分(二)4`，另從該年度表列選修至少 12，合計 20。

| 版本 | 選修目錄與特別限制 | 狀態 |
|---|---|---|
| 111–112 | 線性代數一二、基礎數學、數學軟體應用與實作 A/B/C、計算機概論、基礎統計學、數論、C 語言程式設計、統計套裝軟體之應用、數學導論、高等微積分一二、代數學一二、機率論、統計學、幾何學、微分方程一二、高等線性代數、數值分析（一）、離散數學、數學教育及統計等表列課；A/B/C 僅擇一採計 3 | `VERIFIED`；完整逐課見 [P111] pp.77–79、[P112] pp.72–74 |
| 113 | 表格以刪改方式把基礎數學改為集合與邏輯、計算機概論改為資訊科學與科學計算、軟體 A/B/C 改為 Matlab/Python 等，且數學導論 4→3 同時保留；註腳也留有新舊文字 | `CONFLICTED`；完整刪改見 [P113] pp.74–76 |
| 114 | 線性代數一二、集合與邏輯、資訊科學與科學計算、統計與生活、數論、Python、Matlab、統計套裝軟體、數學導論、數學教育概論、數學遊戲教學設計與實務、高等微積分一二、代數學一二、統計學一二、微分方程、高等線性代數、數值分析、離散數學及後續表列數學／統計／數教課；Matlab/Python 僅擇一 3 | `VERIFIED`；完整逐課見 [P114] pp.77–79 |
| 115 | 依 115「數據科學與數學系」表列目錄；相較 114 包含改名後的「數學遊戲數位設計與實務」等本年度原名；Matlab/Python 僅擇一 3 | `VERIFIED`；完整逐課見 [P115] pp.88–90 |

各年度手冊另規定：以本系開課程採計；三年內曾就讀數學相關系所且修畢相當學分的表列必修，可附成績與課綱申請免修，但經核可免修的學分仍須由其他選修補足。這是「免修不生學分」的明文案例。

數學系現行大學部頁面又說明：輔系必修須在本系班級修課；校外選修最多 6 學分；APC、地生、資科學生若已在數學系開課中修過相關課，是否免修／抵免取決於該課是否已列原系畢業學分，且仍須補足；修課承認與抵免須經系務會議。[MATH-U] 該頁沒有可追溯的逐年生效日期，因此只可做人工審核提示，不能反向覆寫 111–115 手冊。

## 6. 年份優先的設定流程與資料契約

### 6.1 欄位順序

1. `admission_cohort`：學生入學年度。
2. `primary_handbook_year`：主修實際適用手冊；不得默認與入學年度永遠相同。
3. `primary_program`／`primary_track`。
4. `secondary_kind`：`none | minor | double_major`。
5. `target_curriculum_year`：先選 111–115；沒有選擇就停在 `UNKNOWN`。
6. `target_program`：只顯示該年度的系／組；115 數學顯示「數據科學與數學系」。
7. `target_track`：只有 APC 再選電子物理／應用化學；地生輔系是系級規則，不多做領域選擇。
8. `application_year`、`application_semester`。
9. `application_status_self_reported`：規劃中／已送件等使用者自述。
10. `department_approval_evidence`、`registrar_record_evidence`、`formal_award_evidence`：正式證據欄位，不能由前一欄自動填入。

### 6.2 穩定 scope key

```text
minor:{target_curriculum_year}:{target_program}:{target_track_or_department}
```

例：`minor:115:apc:physics`、`minor:115:apc:chemistry`、`minor:115:earth_life:department`、`minor:115:cs:department`、`minor:115:data_science_math:department`。

- 切換 `secondary_kind` 必須清除舊 target、適用性與核准證據；minor 與 double-major 不得共用同一 target role。
- 改 `target_curriculum_year` 必須先清空 program／track／rule snapshot，再依新年度重建選項。
- 改 program 必須清空 track 與該 target scope 的核准資料。
- 不得靜默選第一個年度、系或組，也不得把 admission cohort 當 target year 預設後立即執行正式判定。

### 6.3 判定狀態機

下列名稱是系統狀態，不冒充校方正式用語：

```text
PLANNING
  -> SUBMITTED (只有送件證據／自述；不得 PASS)
  -> DEPARTMENT_APPROVED (相關學系查核及系主任同意證據)
  -> REGISTRAR_RECORDED (教務處登錄證據)
  -> ACTIVE
  -> COURSEWORK_COMPLETE (同一 DecisionSnapshot 的課程配置達標)
  -> AWARD_ELIGIBLE_PENDING_REVIEW
  -> AWARDED (校方成績／學位文件已加註)

任一階段亦可為 REJECTED / ABANDONED / UNKNOWN。
```

只有 `REGISTRAR_RECORDED` 之後才可顯示「已正式取得修讀資格」；`COURSEWORK_COMPLETE` 只表示課表條件完成；沒有 `AWARDED` 證據時不得顯示「已正式取得輔系」。

## 7. Fail-closed 實作映射

| 規則／證據情況 | DecisionSnapshot 應輸出 | 禁止行為 |
|---|---|---|
| 未選 target year 或 program | `UNKNOWN: TARGET_SCOPE_INCOMPLETE` | 用入學年或第一個選項代填 |
| target year 已選，但無個案適用年度依據 | 課表可做 planning preview；正式 gate `UNKNOWN: TARGET_VERSION_UNCONFIRMED` | 把預覽課表當核准課表 |
| 只勾「已申請」 | `PENDING: USER_REPORTED_APPLICATION` | 自動改為 approved／qualified |
| 無系所核准或教務登錄 | `UNKNOWN: OFFICIAL_APPROVAL_MISSING` | 即使 20/20 也顯示正式 PASS |
| 規則為 `PARTIAL` | 顯示 verified 子要求與未具名缺口；整體 `UNKNOWN` | 用自由選修、任意系課或 shadow credit 補缺口 |
| 規則為 `CONFLICTED` 且配置碰到衝突列 | `UNKNOWN: SOURCE_CONFLICT`，附兩個原始 assertion | 選較有利數字或較新外觀值 |
| 原系系訂必修已使用同一實得學分 | 該 credit 不可再配置到輔系；若有替代，先要求核准 evidence | 同課雙重正式計分 |
| 免修／抵免但沒有實得學分 | 只滿足免修資格（若有核准），credit contribution = 0；另補學分 | 憑空產生 credit |
| 普物／普化講授與實驗 | 四種 requirement 分開；各自以課號／正式核准配對 | 因名稱相似把講授 3 當成含實驗 4 |
| 資科「其他本系課程」 | 驗證課程開設單位、實得學分與未重複配置 | 只看課名或全域 alias |
| 地生共同必修中的 choice group | 每組只取一條有效實際課程 | 專題與實習同時計入同一門檻 |
| 重修或重複紀錄 | 先形成單一重修群的有效 attempt，再參與全域配置 | 固定 requirement 與彈性 bucket 同時用同一重修群 |

所有畫面、圖表、匯出、阻塞項目與補修建議，都必須只讀同一份 `DecisionSnapshot`；不得在 UI 或匯出層重新計算輔系學分。

## 8. 建議的 TDD 驗收矩陣

| 測試 | 輸入／操作 | 預期 |
|---|---|---|
| 年份優先 | 選 minor，尚未選 target year | program/track disabled；snapshot 為 `TARGET_SCOPE_INCOMPLETE` |
| 年度篩選 | 先選 115，再選 APC 化學 | 只載入 `minor:115:apc:chemistry`；顯示化學實驗、微積分 |
| 年度重設 | 已選 115 APC 化學後改 114 | program/track、approval scope、舊 snapshot 全清；不可殘留微積分 requirement |
| 組別隔離 | 115 APC 物理 ↔ 化學 | 物理實驗與化學實驗互不交叉；兩組 scope key 不同 |
| 舊 APC 缺口 | 111–114 任一 APC 組完成八門 16 | 顯示已確認 16／20 + 未具名必修 4；整體 `UNKNOWN`，不是 PASS |
| 微積分年度 | 114 APC 化學有微積分成績；115 APC 化學同成績 | 114 不自動投入未具名 4；115 依一、二各 3 配置 |
| 講授／實驗分離 | 只有普通化學（一）3，沒有化學實驗 | 115 化學組實驗仍缺 1；不得以講授補實驗 |
| 地生版本 | 112、113、114、115 各套同一組合成成績 | 111/112 為兩個 1 學分 choice；113 為單一 2 學分 choice；114/115 為書報討論 2 |
| 地生 0 學分 | 信用分 24 已滿、0 學分 gate 未確認 | credit subtotal 24；正式 completion 顯示非學分條件待人工確認 |
| 資科正常 | 計概3+C3+經驗證資科開課14 | 課表完成候選為 20；仍受正式核准／登錄 gate |
| 資科重疊 | 計概、C 已配置為原系系訂必修，無資科替代核准 | 兩課不可再計；顯示需要資科指定替代，不得 shadow credit |
| 數學 one-of | 111 同時有 A/B/C；115 同時有 Matlab/Python | 對應年度群組最多計 3 學分 |
| 數學免修 | 微積分獲免修但無實得學分 | requirement 可標核准免修候選，credit = 0，仍須選修補足 |
| 數學 113 衝突 | 配置使用數學導論 | 顯示 4↔3 來源衝突與頁碼；整體不得自動 PASS |
| 不重複計分 | 同一課同時可進主修自由學分與輔系 | 全域配置只正式選一個；除非另有明文共享規則 |
| 申請狀態 | 使用者選「已申請」，無核准檔 | 只顯示自述送件；`department_approved=false/unknown`，不得 qualified |
| 核准鏈 | 系所核准但未見教務登錄 | 顯示「系所已核准／教務登錄待確認」；不得 ACTIVE |
| Snapshot 一致 | 同一案例開啟 UI、圖表、CSV/XLSX、PDF | 學分、課程配置、UNKNOWN 原因與 provenance 完全一致 |
| 行動版流程 | 375/390/414 px 完成 year → program → track → application | 不依賴側欄；欄位順序固定，改值後不殘留舊 target，無水平捲動 |

所有測試使用合成課程與遮罩 ID；測試輸出不得含真實姓名、學號、成績單或登入資料。

## 9. 對現有程式的最小變更邊界（研究建議，未在本報告修改）

- `sidebar.py`：把 secondary kind 擴為 none/minor/double-major；依第 6 節改為 target year → program → track；把自述與正式核准分欄，實作依賴欄位清除。
- `curriculum_registry.py`：新增 `minor` role 與 25 個 target-version scope；每條 requirement 保存狀態、來源 URL、PDF／印刷頁、原始文字與人工原因。
- `graduation_service.py`：minor 與 double-major 使用同一全域 credit allocator，但有不同 rule scope；任何 `PARTIAL/CONFLICTED/MISSING` 的必要 bucket 都阻止正式 PASS。
- `decision_snapshot.py`：新增 minor program decision、application/approval gates、evidence provenance；成為 UI、圖表與匯出的唯一資料來源。
- 測試：先加入第 8 節的紅燈測試，再實作；不得用 CSS 字串或 sidebar label 存在就代替行為驗證。

## 10. 核對紀錄與限制

- 官方入口：教務處課務組「歷年課程手冊」及 111–115 各年度頁，皆列出 `3-理學院.pdf`。[H0][H111][H112][H113][H114][H115]
- 本機官方 PDF：`學生手冊/3-理學院.pdf`、`3-理學院 (112).pdf`、`(113).pdf`、`(114).pdf`、`(115).pdf`。本次逐頁抽取上述所有 target 頁的文字；另以 180 DPI 實際目視核對 111 APC p.19、113 數學 p.74、115 APC 化學 p.24 的表頭、列項、刪改與表尾。
- 113 數學頁的黃色新增、刪除線與 4→3 同時存在於官方頁面，故沒有自行選定新值。
- 111–114 APC 額外 4 學分、0 學分條件對地生輔系的適用性、各系各學期申請名額／加碼資格、個人適用目標課表年度，仍是真正未完成的證據缺口。
- 本次只建立本研究檔；未修改規則、程式、測試或部署，也未讀取任何 token、帳密或個人資料。

## 正式來源

[M1]: https://reg.utaipei.edu.tw/var/file/31/1031/img/926/316943067.pdf "臺北市立大學學生修讀輔系要點"
[S1]: https://reg.utaipei.edu.tw/var/file/31/1031/img/926/108163803.pdf "臺北市立大學學則"
[H0]: https://curr.utaipei.edu.tw/p/412-1032-5.php?Lang=zh-tw "歷年課程手冊"
[H111]: https://curr.utaipei.edu.tw/p/405-1032-96198,c5.php?Lang=zh-tw "111課程手冊"
[H112]: https://curr.utaipei.edu.tw/p/405-1032-105200,c5.php?Lang=zh-tw "112課程手冊"
[H113]: https://curr.utaipei.edu.tw/p/405-1032-114642,c5.php?Lang=zh-tw "113課程手冊"
[H114]: https://curr.utaipei.edu.tw/p/405-1032-124717,c5.php?Lang=zh-tw "114課程手冊"
[H115]: https://curr.utaipei.edu.tw/p/405-1032-134435,c5.php?Lang=zh-tw "115課程手冊"
[P111]: https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MemN4TDNCMFlWODVNREkyTWw4eE56STBPREZmT0RBNU5qY3VjR1Jt&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5 "111 3-理學院.pdf"
[P112]: https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MelV5TDNCMFlWOHhNRFF3T1RKZk16YzNORGc0TVY4ek16ZzJOaTV3WkdZPQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5 "112 3-理學院.pdf"
[P113]: https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MemcxTDNCMFlWOHhNell5TmpoZk16TXhNREE0TVY4ek1qUXdNUzV3WkdZPQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5 "113 3-理學院.pdf"
[P114]: https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9MemN5TDNCMFlWOHhNemN4TWpSZk5UQTVNalkzTWw4ek9UY3lNUzV3WkdZPQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5 "114 3-理學院.pdf"
[P115]: https://curr.utaipei.edu.tw/app/index.php?Action=downloadfile&file=WVhSMFlXTm9Memt3TDNCMFlWOHhOelExTnpKZk1qTXlNak0yWHpjNE5qSXhMbkJrWmc9PQ==&fname=0054YSGHRK10PPXXTSZSTSYW14PKJDKKQO343510LP25LKQPZWROYSA43454QOUSSSPOCDYTVSPKDHDH&cg=5 "115 3-理學院.pdf"
[CS-A113]: https://cs.utaipei.edu.tw/p/405-1081-116948,c3219.php?Lang=zh-tw "113學年度第1學期資訊科學系輔系、雙主修申請公告"
[CS-R]: https://cs.utaipei.edu.tw/var/file/81/1081/img/994/269769035.pdf "臺北市立大學資訊科學系學生認抵科目學分申請表"
[MATH-U]: https://math.utaipei.edu.tw/p/412-1082-146.php?Lang=zh-tw "數據科學與數學系大學部修課注意事項"
