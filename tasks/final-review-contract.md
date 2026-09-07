# 核心複審契約（Sol 唯讀）

使用者核准之變更包括多年度手冊、合法彈性採計、申請規章適用、校務擷取正確性與學生報表。需獨立複審，不能以代理自述或測試數量當證明。

原始程式在tmp/baseline-20260905-approved/source.zip；tmp/review_baseline_diff.py 可逐檔diff。請針對實際修改審查，不重做整份repo盤點。

## 重點

- registry candidate_only列不得生成必修要求；named必修不得因同池而接受任一選修。pool membership來自已核對指定年度/系組的唯一精確身分，不能信任來源輸入自稱pool/official。
- 真實AG102沒有課號、開課單位，講授/實驗標籤亦不直接提供。正常同系精確課名/學分依來源唯一對應應可採計；跨系同名不可假等同。不能讓大量正常課一律待核對。
- overflow routes仅官方允许同owner类别，拒绝cycle/跨owner/不存在target；跨系兼充需正式依据，不得重计总学分。
- full valid witness可證明可行；多解或未證明最優不應自動變失敗。搜索未完成且無witness不能宣稱FAIL。偽造witness/守恆失敗仍不准過。
- 入學cohort、課表year、申請學期/日期、規章修訂與生效、學生subject綁定分開。自述不變官方資格；可信現在資格不必永遠重證歷史申請日期。正式授予與修課達標分開。
- 學生尚未有正式核准證據時，仍需能看『依所選課表的課程進度』與具體缺額；行政/適用性待核對不能把所有已知課程數字隱藏，也不能反向把規劃進度當成正式資格。請查app是否有可實際使用的流程，而非只有測試能注入resolver。
- parser全歷年修習/實得總額不可誤用單學期。已結束/在修/實得口徑一致，兩學期混合狀態/0學分未通過/免修抵免/漏列多列/重複頁/衝突總額正確處理。
- 已发现关键整合点：registry新增primary.non_credit_requirements（體育4學期、服務學習、輔導/生涯等），但舊_requirement_specs會跳過credits<=0。core/rules已被要求接上獨立門檻；複審一定測『全部學分足但漏PE/零學分必修』不准過，且同學期兩門體育不能冒充兩學期。
- parser fatal/reconciliation限制要到app confirmation及live smoke；不因『有課程列』就過。無總額與核對失敗要區分。
- GUI、學生PDF/CSV不露工程狀態碼，但不得隱藏未採計課程、手冊缺口或不確定理由。報表與機器JSON保持同一snapshot可核對。
- private資料不進匯出/日誌/發布包；來源遮罩與確認閘門不可弱化。查詢效能以代表規模evaluate驗證。
- 自由選修total與science subset同一批EXCLUSIVE portions，不拆3+12。搜尋必須能在15非science＋稍後3science與12非science＋4science找到合法15/3；free證據已知、science缺metadata只使子條件待核對，不抹去free採計。
- 父代理直接核對115官方理學院PDF：APC p6/p18、Earth p40/p44、CS p119/p121均排除通識進free；CS另排軍訓體育。Math p80有free15及外系/外校cap15、排通識/大三四PE/全民國防與指定學程例外，該頁未見science3。請核對registry逐系政策、分類排除與unknown membership，不得global套3或把多修GE灌free。
- PE若來源要求4不同項目/學期，必須最大匹配term↔activity；只有一個羽球alias不能宣稱完整PE支援。111–113歷史適用性沒有證據不得倒填114/115。
- 規則來源狀態不得以generic跨系/跨role原因全面封鎖。『總額40、必21、選修至少18』本身非衝突；應檢查三個最低限制，不要求分項最低值恰好加總40。
- scenarios（如果已落地）：selected不變，primary-only同成績重新evaluate且清除次修專屬要求/證據；兩方案數字不得加總。未來課程不加入現在已得帳本，不冒稱最少補修解。
- 部署helper（tmp/deploy_reviewed_bundle.py、tmp/prepare_github_release.py）只指定Sapphirejimmy HF、UTaipei-Student-Tools GitHub；來源allowlist/hash/parent guard、秘密不進payload/日誌，GitHub非force push並skip錯目標workflow。

## 輸出

按嚴重度列真正可重現問題：檔案/行號、觸發案例、錯誤結果、最小修正與驗證建議。沒有證據不要臆測。提出的問題由主代理分配Terra修正，Sol不要寫程式、不要登入或發布。
