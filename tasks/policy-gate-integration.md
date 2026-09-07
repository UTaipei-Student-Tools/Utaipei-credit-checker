# 新增來源政策與非學分門檻：需要架構決策

Core第一批已實作pool mapping/合法witness/申請日期與有效性，正在測試；原始diff可由tmp/review_baseline_diff.py取得。2個EvaluationRequest漏字段已由父代理驗證修好。

主代理發現與Rules新增registry的兩個跨模組缺口，不能直接发布：

1. primary.non_credit_requirements含PE4學期、服務學習、輔導/生涯等零學分門檻；catalog也保留列。graduation_service._requirement_specs在credits<=0直接continue，只有minor已有特殊gate。需独立非学分判定，不得全部学分够就漏PE。必须按distinct terms计数，零學分F/W/停/未不完成，免修例外需依据。零门槛不可变成虚构学分补总额。
2. primary.course_pools某些資料是空candidate_courses + 已知policy；如official_category_policy（通識分類、共同選修）、official_open_elective_policy（自由學分、理學院至少3）。Core _course_pool_candidates只展開exact候選，這些池會永遠填不滿。既有資料清楚的政策不可被報為『官方未提供』；但free15/理学院至少3等不能不核對來源就套全部科系/年份。

需Sol決定窄可執行契約：規則白名單、可信來源/必要字段、policy編譯到attempt membership及零學分獨立result如何進snapshot/UI，缺元資料的正常校務PDF如何仍正確規劃；不得任意accept_any，也不能以去掉required rows讓學生可過。

AG102真實PDF：沒有course_code/offering_department，course_type=必或選，成績與學期皆可讀。Source缺课号不是一律失败理由；精确同系名称+学分+手册范围有唯一来源可认，跨系同名需依据。

驗收至少一個真實形狀的完整Earth主修合成案例满足全部学分+零学分门槛；含未列在专业封闭名单但符合正式自由学分条件的课。再去掉一门必修/一个PE学期/理学院自由学分子条件等，必须说明具体缺口。所有5年/系组/角色覆盖矩阵仍须报告来源真实缺口。

Rules代理正核对policy来源并跑registry测试。UI代理正在finish学生显示与exports，不要让Sol改它们。Sol只读决定，Core随后继续实现测试。
