# 資科主修甲乙課群：Sol正式來源與模型契約

111–115皆31專業必修+54系選修+GE28+free15=128。54內的甲全部必修，不是任選。原research115漏甲4門、乙多門且舊名誤用，必須用原PDF表格轉錄/影像抽查。

## 年度資料

甲每年12門32學分：微積分一3、程式課3、機率3、計網3、數位電路實驗1、系統程式3、組語3、計算機結構3、自動機形式語言3、資料庫系統3、人工智慧課3、資訊專題二1。111/112程式课Java軟體實務，113+程式設計技巧。人工智慧111–114帶概論，115不帶。

乙領域111–113是common/software/network三個各>=1門；114–115只有software/network兩個各>=1。正式同一雙領域課可作兩個observationalwitness，學分只計一次。

來源111架構113/須知115/課表118–120；112108/110/113–115；113104/106/108–111；114108/110/112–115；115119/121/124–126。均PDF頁。父代理115p124親看影像與表格，12甲32沒有刪線；tmp/cs115-elective-source-rows.json完整表格原始列含notes與creditcolumns。115乙包括編譯、資料科學、C++、校外實習、圖論、密碼學、資料探勘；按原表保留名稱有無概論及數位學習不帶概論。

## Requirement與路由

12甲named RequirementSpec合计32；一個cs_beta_remainder required22，只有该年乙池。presentation-only rollup_group_id=cs_primary_elective_54、rollup_required_credits54，不再建立另一個54creditconsumer。

候選metadata：cs_elective_alpha:<cohort>、cs_elective_beta:<cohort>、cs_beta_domain:<cohort>:common/software/network。甲只自己的namedrequired；freepolicy排除甲membership。乙可補22，超額依法free；其他合法外系free仍照正式規則。公開課程目錄只驗證身份，不創造alpha/beta/domainmembership。

乙remainder的subset_constraints新增minimum_course_count1，observed_requirement_ids明列remainderID，membership指定該domain。只觀察其中EXCLUSIVE portions，unique有效attempt，不能拿free或unallocated替系選領域過關；未知membership令該domainUNKNOWN。完成的同一雙領域乙課可同時見證兩個gate而ledger不加第二份。countconstraint參與search/witness，必要時換乙配置保留所有領域。

## 驗收

每年甲12門32；31+32+22+28+15=128。甲少資料庫即使系選>54仍缺named；年度beta3/2domains；雙領域課一次credit兩domainwitness；free不補domain；有合法替代要找出；甲不可灌free；115人工智慧不能模糊頂114人工智慧概論。UI顯示系選54rollup与甲/乙明細，點入每門已修/未修。
