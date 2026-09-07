# 2026-09-05 優化驗證紀錄

## 基準

- 原始檔案：tmp/baseline-20260905-approved/source.zip，87檔與SHA256 manifest；不含憑證。
- 完整pytest原版：528 passed、4 skipped、747 subtests passed；1個Windows spawn啟動時載入Streamlit導致偶發timeout。
- 正式portal live smoke實測可登入、下載PDF；production supervised fetch也通過帳號比對與逐列確認。發現累計總額誤抓單學期，修正前不得當成學分正確性驗收通過。

## 主代理已執行

- tests/test_hf_bundle.py + test_hf_live_browser_smoke.py + test_scraper_lifecycle.py + test_portal_contract.py + test_transcript_only_portal.py：55 passed、3 skipped、6 subtests。
- tests/test_portal_hard_deadline.py：移動sidebar import至唯一UI測試函式，原逾時限制不變，11 passed。
- 新增test_transcript_reconciliation.py：修正前12 failed、6 passed（具體錯誤已重現，等待parser工作者修正）。
- UI首批預整合：49 passed、10 failed、21 subtests；8項為HTML改中文之旧碼斷言，2項為core WIP漏dataclass字段，已交各自範圍處理。
- 新增test_student_export_contract.py：修正前2 failed、1 passed；學生PDF/CSV漏未採計課程、漏報表編號。不可把此批當完成。
- Streamlit server.maxUploadSize讀值確認20，與parser 20 MB一致。
- tmp/browser_shell_review.py chromium、webkit：兩個瀏覽器空白首頁主題矩陣均通過；375/390/414/844橫向/768/1024/1440均無橫向溢出、操作控制>=44 px、單一stMain捲動區。這是首頁預驗證，最終尚需完整合成成績與匯出流程。
- Parser修正後父代理：test_transcript_reconciliation.py + test_portal_live_smoke.py + test_course_input_adapter.py + test_synthetic_transcript_fixture.py 共40 passed。
- 正式supervised portal quality audit修正後通過：登入帳號與文件相符；55原始課程→57逐學期標準化→57明確確認後釋出；累計修習與實得兩總額均精確相符，所有課名/學期存在，零學分未通過誤判0。來源PDF未提供課號/開課單位（55列）已確認是來源版型限制。此次未保存PDF、成績或截圖。
- core先前2項EvaluationRequest字段錯誤已由父代理重跑，2 passed。
- Parser與新增獨立測試的Ruff scoped檢查：All checks passed。先前表尾兩個診斷暫存檔已刪除並Test-Path確認不存在。

## 未完成的關鍵整合

- UI finalbatch父代理：64 passed、8 failed、18 subtests。8fail皆handbook_rules.get_credit_requirements:879缺free_elective引發legacy ReportNavigationTests錯誤，已交Rules修相容。新screen/PDF/CSV/noncredit/subset共用契約已過。
- Chromium迭代：已修chart open空字串與nestedsummary歧義；audit原碼提醒需先轉中文再和body比對。仍在全流程執行，不宣稱browser完成。
- 父代理視覺檢查：首頁四控制與套用現在在1280x720首屏內。另修primarybutton文字採ui-canvas、子節點繼承；新增瀏覽器4.5對比驗證（先重現原深色低對比，再抓到Streamlit p覆寫並修正）。
- Sol parser/deploy窄複審：parser核對與HFparent/hash正確；發現cohort改變重用確認cache、HFcleanup未檢查殘留editor兩項false-success，已分派UI代理窄修。GitHub需明列額外檔案與可執行add/hash/skipci/nonforce流程，亦已分派，不執行真發布。
- 父代理直接115官方PDF來源抽查：APC p6/p18、Earth p40/p44、CS p119/p121明載free15、院內3、排除GE（Earth/CS另體育，CS軍訓）；Math p80 free15但未見院內3，有外系cap/排除/指定學程例外。已送Rules/Core處理逐系predicate。

- UI完成批次後父代理重跑63 passed、21 subtests；學生PDF/CSV合成視覺驗證：2列（含未採計課）、1頁、兩匯出都有報表編號，無原始狀態碼或多餘課號/學期缺漏提示。
- 父代理額外新增畫面完整性測試：test_unallocated_earned_course_remains_visible_in_student_screen 失敗，renderer仍未顯示未採計B課（匯出已修好）。需UI窄修正。
- 完整Chromium瀏覽器測試已通過上傳/確認，於browser_acceptance.py:731失敗：圖表折疊區summary第二次被關閉，因get_attribute('open')空字串被誤認false；需改為is None並保留可見性驗證。
- 發布後hf_live_browser_smoke.py已由父代理更新新中文欄名/登入按鈕，5個隱私/目標限制測試通過。

- Core暫停等待Sol窄設計：primary零學分/體育學期門檻、通識及自由選修policy編譯，詳tasks/policy-gate-integration.md。不能以資料表建好取代正式evaluate正例。
- UI已續接finishbatch，仍須未採計課完整展示與匯出、中文parser原因、報表編號及完整browser驗收。
- Rules正核對逐年度來源與coverage矩陣。少數真實來源衝突需精確列明，尚未編碼不可誤稱校方無資料。

## 發布目標與基準

- 父代理完整 Chromium 合成成績流程已通過：上傳/確認、要求與圖表展開、PDF/CSV/audit 下載、設定持續保存、PWA 更新及 375–1440 px 響應式矩陣。主要按鈕實測文字對比 light 10.99、dark 7.41；未保存真實學生畫面。這是當時版本的整合預驗證，最終 core/scenario/cache 修正後仍需重跑。
- Rules 凍結批次父代理驗證：report_ui/registry/coverage/primary separation/minor 共 83 passed、72 subtests；唯一失敗為舊 HTML 原碼斷言。改驗「輔系申請與資格」及不含 raw key 後，該測試另跑 1 passed。
- 尚有數學 free_total 語義疑點：115 手冊 p.80 同時有自由選修 15 學分需求及外系/外校專門課程至多 15；registry 目前把整個 free_total 當 MAXIMUM，已請 Sol 依逐年來源判讀，不把疑點當成完成。

- HF：Sapphirejimmy/Utaipei-credit-checker，發布前sha a8b85aeb5858905f09e1002e6a6d1b1e77d061a8，RUNNING；尚未發布。
- GitHub：UTaipei-Student-Tools/Utaipei-credit-checker，main基準d950d3382a5e1c802005138d71d5460a73ba4928；已clone到tmp/github-release，尚未修改/提交/推送。
- 使用者已確認只更新Sapphirejimmy HF。GitHub既有workflow指向組織HF且使用force-push；本次GitHub commit採[skip ci]，不觸發另一個Space。
- GitHub clone繼承core.autocrlf=true。正式git add須使用單次 `git -c core.autocrlf=false -c core.safecrlf=false ...`，不改全域設定，避免GitHub blob換行與HF manifest雜湊不同。已存在的LFS圖示需以pointer oid對應實際payload SHA256核對。

## 最新父代理核對

- Core cap/strictwaiver engine:190 passed22subtests；PARTIAL安全測試改顯式注入registryPARTIAL，不依賴仍未補齊的真實年度。Sol確認engine三HIGH已解，另發現service sanitizer兩接線缺口，交public adapter批次處理。
- APC primary:73 passed52subtests；十組最低額均128，原PDF課名交叉檢查九組一致。114physics28候選有8個課名不在引用p10–11，原表25rows，已退回一次窄修正。五份本機/官網PDF byteidentical，114不是檔案版本差異。
- Student noncredit export coverage/evidence真實欄位fallback已修，helper確認中文「規則資料完整；來源已核對」。

- APC correction accepted:114physics25names/credits all原PDF p10–11，minimum128，28targettestsPASS。父代理再以PyMuPDF原表欄位核對ALL5years2tracks304筆elective candidate name/credit pairs，0 mismatches（非只核對測試期待值）。
- HF productionallowlist改逐檔static/config/bootstrap共16assets、TREE_ROOTS=()，目前50publicfiles；negativefixtures證明.streamlit/secrets.toml與static/transcript.json不納入。發布helpers23passed3platformskip+RuffPASS；未發布。
- Snapshotmax/ITwording29UI/exporttestsPASS+Ruff，maxcap12/15三media一致。

- University GE batch accepted:104passed52subtests。111 compulsory8+GE20/112+compulsory10+GE18 registrytotal28，各源池overflow+直接eligibleflex。FormalservicecompiledGEprobe additionally caught allowed_course_kinds=('UNKNOWN',) restriction rejects VERIFIED LECTUREpolicycourse; assignedCorepublicadapterboundary (data原字典allocate測試未覆蓋)。FormalIT metadata round-trip _safe_curriculum nowretains allscopeflagsfalse+waiverauthority/version/program/track, liveCoreWIPexplicitfalsepriority已檢查。
- Newzero-life/serviceallcohortsourcecontract tasks/primary-zero-credit-design.md，Data已接下一批，尚未完成。Math primary/CS primary/secondary/scenario/fullUI/finalrelease仍未完成。
- Parent report follow-up: matched gate attempt identity joins retained across HTML/PDF/CSV; subset without coverage/evidence flags uses actual source only, no fabricated missing provenance. tests/test_student_export_contract.py + test_snapshot_renderer.py + test_snapshot_exports.py:29 passed; scoped Ruff passed.
- Parent zero-credit batch accepted:143 passed52subtests (primary zero/registry/university). Inspected dedicated descriptors, source scopes and service-term applicability; Core membership integration remains outstanding. Data now implements approved Math primary.
- Parent actual Earth111 integration probe tmp/formal_earth_probe.py:68 synthetic rows,128 credits incl PE/IT/Life8/Service2. Fails formal recognition. Sol identified Decimal-scale index mismatch, public_catalog evidence lowering, generic quota blanket downgrade and skip-first search. Core assigned smallest fixes; not accepted yet.
- User requested faster delivery after6hours: preserve validated features, stop unimplemented optional scenario comparison, focus only required graduation rules/allocation/UI and release. No rewrite, no added timetable.
- Parent allocator integration: Sol design applied trusted public_catalog authority only to aggregate/quota, source required; constrained-course-first/allocation-first search; split potential unmatched uncertainty from hard binding/attempt/repeat/shared/waiver uncertainty. Initial116 public/service/allocator testsPASS. Added6 targeted cases; allocator76PASS+Ruff. Wider139PASS+2testexpectationfail (untrusted source contract should assert noPASS, not exactUNKNOWN); corrected new tests only,76PASS. Sol independent6PASS and final delta review: no remainingHIGH.
- Parent source docs corrected research/apc_cs_handbook_matrix_111_115.md and research/minor_program_matrix_111_115.md to reviewed facts (CSalpha32+beta22,115fullsecondary,APCold16+4/24,Math21+18withtotal40,zero scope). Removed obsolete evidence-gap narrative; no deployment claims.
- Parent UI Math113+ canonical domain selector added sidebar/app, unselected disablesApply/preventsanalysis, existing ID signature retains invalidation. Existing13 settings testsPASS+Ruff; new actualMathdomain test awaiting Data canonicalrecords. Newhelper subset names prevents internalID display;30 renderer/export testsPASS.
- Core service public batch received:Decimalkey/specificunresolvedmarker/zero-series descriptors working;17public+28service testsreportedpassed. Parent actual128 probe confirms all4noncreditgatesPASS. Found independent false GE memberships:public GEcommon emitsEarthdepartmentcommon and free despite exclusion. Core assigned one narrow service/public correction plus servermaxcapacity, owns only service/public/tests. Root currently owns allocator.

## 2026-09-06 完整正式案例通過

Parent已完成 demand-aware feasibility seed：exact named優先、動態slack、候選residual優先，沿用完整守恆/repeat/subset/evidence驗證。Sol review seed安全通過並定位residual；parent窄修後Earth111真實手冊128學分合成成績單PASS，含PE4/IT1/Life8/Service2，全部requirement及subset PASS。tests/test_formal_graduation_integration.py 3PASS（完整、缺named不能用陌生替代、HTML/PDF/CSV同snapshot中文與課名）；allocator78PASS；GE/服務/settings整合62PASS；Math113+必須選domain、114->115保留Math並清domain。HF bundle已明列public_course_catalog.py及data/public_course_catalog.json，helper16PASS3Windows skips。尚未发布。

ParentMath正式compiler檢查發現113+named domain+quota重複消耗，已指派Data窄修；修後30個非CS primary正式最低sum均128。Math71tests+51subtestsPASS，但正式probe揭示111alpha/external subset遺漏及moderncap membership/source空白，已指派Core服務接線修正，不接受只看thresholds或單元成功就完成。Parent清理math_earth研究舊錯述並依現行catalog更新共同C/Python課名；CS門數UI31PASS。

Parent追加正式統計檢查：Earth128 allocatorPASS但build_snapshot_view summarysource0/bybucketempty，F1/F5/F11 conservationfailed、F7unavailable，屬實際pipeline blocker。已交Sol readonly精準trace，root將修。新增test_formal_statistics_preserve_the_authoritative_credit_ledger必須128與4chartavailable，不能只驗證CSV/PDF含課名。UI先前47PASS不代表此正式統計完整。仍未发布。

發布preflight：HF仍a8b85aeb5858905f09e1002e6a6d1b1e77d061a8/RUNNING未变；GHmain由d950d33前進至c2a6aefecba2214de26621a6fbff64fbfa9cdb78，只有README固定StreamlitURL+.github/workflows/main.yml改manual workflow_dispatch/Sapphire target。隔離tmp/github-release乾淨，已ff-only到c2a6aef；rootREADME保留新固定網址，workflow維持remote版本不覆寫。新的發布parent須用c2a6aef；仍不forcepush、不觸發workflow，commit保留[skip ci]。

## 2026-09-06 正式統計與主修總進度修復

Parent + Sol 精準核對三個序列化問題：public evidence projection 後需重新建立有效 statistics digest；Decimal 必須在 JSON 字串化後固定；renderer 必須先驗 canonical snapshot，再做顯示隱私副本。保留真正舊雜湊/篡改數值的 fail-closed 判斷。Mapping allocation metadata 改用既有 _field 讀取，避免遺失 feasible witness。

主修總進度依 Sol 設計，由 service 發出已解析主修 registry 的非消耗型總額 descriptor，projection 僅加總同一 PRIMARY requirement scope 的 EXCLUSIVE 學分，排除 target、shared shadow、unallocated，來源/owner/守恆缺一不可。沒有新增128學分消耗要求。正式 Earth111128 來源/採計/總門檻全部128、尚缺0，F1/F5/F11可顯示。F7因15類超過圖表4類容量只隱藏可選圖，dataset保留診斷，未改規則。

最終正式整合4PASS；先前同輪其它68projection/snapshot/student-export testsPASS（當時唯一失敗是新增正式HTML測試誤把CSS data-status='PASS'當可見文字，現改驗可見文字且4PASS）。Scoped Ruff PASS。Sol review descriptor/scope/guard無新增finding。仍待secondary catalog與CS count合併後full suite/browser/release。
