# 核准規劃需求的最小方案比較（Sol唯讀設計）

現有 remediation 是 DIRECTION_ONLY，不能聲稱最少補修解。既有要求投影有指定未修/修習中課程、額度缺額、其他合法配置，應直接重用，不建立假CourseAttempt、不做課表排程。

## 缺的薄層

已選輔系/雙主修者需要與『只看單主修的規劃比較』並列；單主修者不用重複方案。必須對同一份已確認成績重新evaluate單主修，不從含次修的配置推算，否則可能漏掉主修合法配置。

介面可獨立scenario adapter模組，保留evaluate/EvaluationRequest/DecisionSnapshot既有語意：

EvaluationScenarios(selected:DecisionSnapshot, primary_only:DecisionSnapshot|None)
evaluate_scenarios(request, evidence_resolver=None)

- selected=evaluate(request)，永遠保留目前正式選擇。
- 僅 secondary_kind=double_major/minor 執行第二次。
- primary-only保留confirmed rows/fingerprint、primary version、as_of、搜尋上限與主修來源；移除target identity/次修申請核准授予/專屬證據。
- binding只有兩端都存在primary-only要求時才能保留。未驗證binding不因移除次修而升級採計；不能讓已移除次修binding阻擋主修。
- primary-only次修行政決策NOT_APPLICABLE；advisory=True，不能覆蓋selected結果或學生修讀資格。

## 比較呈現

純投影build_plan_comparison(selected, primary_only=None)，不重新配置。每方案含scenario_id/advisory/snapshot_id/primary_status/secondary_coursework_status/administrative_status/credit_conservation/feasible_witness/既有requirements投影。

學生選擇次修後可看兩方案目前進度。補修方向重用官方指定未修/修習中、額度池缺額與來源不確定說明；DIRECTION_ONLY及minimality_proven=False語意保留。未來規劃列不得更改現在earned、verdict、ledger或snapshot id。

## 驗收

- 單主修一次evaluate；次修兩份相同fingerprint/attemptIDs/primary/as_of。
- primary-only無target要求、次修行政NA，selected不變。
- 共用3學分各方案分別守恆，不把兩方案總數相加。
- selected次修待確認但primary-only主修可PASS時，同時呈現並清楚標為規劃比較。
- 未修官方課程NOT_ATTEMPTED/零已得，修習中不入已得；額度不捏造課名。
- 未驗證target/binding不升級selected。

待目前核心policy-gate完成後由Terra實作adapter/測試，再由UI接比較投影/快取/畫面。避免同時修改重疊檔案。
