import unittest

from credit_engine import evaluate_graduation, find_and_consume_course
from handbook_rules import (
    get_apc_target_requirements,
    get_available_handbook_years,
    get_credit_requirements,
    get_rule_sets,
    normalize_course_name,
    validate_rule_collisions,
)
from pdf_parser import build_course_dict, parse_transcript_pdf


def course(name, credit=2, score="80", course_type="選", academic_year="114"):
    return build_course_dict(name, course_type, str(credit), score, "", "", academic_year)


class RuleTests(unittest.TestCase):
    def test_name_normalization_handles_full_width_punctuation(self):
        self.assertEqual(normalize_course_name(" 英文（III）：職場商旅 "), "英文(三)")

    def test_requirements_follow_config(self):
        single = get_credit_requirements("單主修", "資科系")
        double = get_credit_requirements("雙主修", "資科系")
        self.assertEqual(single["total"], 128)
        self.assertEqual(single["target_total"], 0)
        self.assertEqual(double["target_total"], 40)

    def test_all_supported_handbooks_are_available(self):
        self.assertEqual(get_available_handbook_years(), ["115", "114", "113", "112", "111"])
        self.assertEqual(validate_rule_collisions("111"), [])
        self.assertEqual(validate_rule_collisions("112"), [])
        self.assertEqual(validate_rule_collisions("113"), [])
        self.assertEqual(validate_rule_collisions("114"), [])
        self.assertEqual(validate_rule_collisions("115"), [])

    def test_year_specific_rules_do_not_bleed_between_versions(self):
        rules_112 = get_rule_sets("112")["earth_life_major"]
        rules_113 = get_rule_sets("113")["earth_life_major"]
        rules_114 = get_rule_sets("114")["earth_life_major"]
        self.assertEqual(rules_112["domain_electives"]["生命科學"]["生物化學實驗"], 2)
        self.assertEqual(rules_113["domain_electives"]["生命科學"]["生物化學實驗"], 1)
        self.assertEqual(rules_114["domain_electives"]["生命科學"]["生物化學實驗"], 1)
        self.assertEqual(len(rules_112["common_alternatives"]), 2)
        self.assertEqual(len(rules_113["common_alternatives"]), 1)
        self.assertIn("書報討論", rules_114["common_compulsory"])
        self.assertNotIn("書報討論", rules_113["common_compulsory"])

    def test_normalization_preserves_course_sequence_identity(self):
        self.assertEqual(normalize_course_name(" 微積分（Ⅰ） "), "微積分(I)")
        self.assertNotEqual(normalize_course_name("微積分"), normalize_course_name("微積分(I)"))
        self.assertNotEqual(normalize_course_name("微積分(I)"), normalize_course_name("微積分(II)"))
        self.assertNotEqual(normalize_course_name("微積分(一)"), normalize_course_name("微積分(I)"))

    def test_exact_matcher_rejects_substrings_and_wrong_credit(self):
        consumed = set()
        courses = [course("微積分(I)實習", 3), course("微積分(I)", 2)]
        self.assertIsNone(find_and_consume_course(courses, "微積分(I)", consumed, 3))
        self.assertEqual(consumed, set())

    def test_every_handbook_exposes_source_and_review_warnings(self):
        expected_sources = {
            "112": "3-理學院 (112).pdf",
            "113": "3-理學院 (113).pdf",
            "114": "3-理學院 (114).pdf",
        }
        for year, source in expected_sources.items():
            with self.subTest(year=year):
                rules = get_rule_sets(year)
                self.assertEqual(rules["academic_year"], year)
                self.assertGreaterEqual(len(rules["document_warnings"]), 1)
                from handbook_rules import get_rules_meta
                self.assertEqual(get_rules_meta(year)["source_file"], source)


class ParserTests(unittest.TestCase):
    def test_completed_and_in_progress_status(self):
        completed = course("測試課程", 2, "60")
        in_progress = course("另一門課", 3, "未")
        self.assertEqual(completed["completed_credit"], 2)
        self.assertTrue(completed["is_completed"])
        self.assertEqual(in_progress["completed_credit"], 0)
        self.assertTrue(in_progress["is_in_progress"])

    def test_rejects_non_pdf_bytes(self):
        with self.assertRaises(ValueError):
            parse_transcript_pdf(b"not a pdf")

class EngineTests(unittest.TestCase):
    def test_total_is_preserved_across_classification(self):
        courses = [
            course("英文(一)", 2),
            course("地質學", 3),
            course("資料結構", 3, "未"),
        ]
        report = evaluate_graduation(
            courses,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系"},
        )
        self.assertEqual(report["summary"]["total_completed"], 5)
        self.assertEqual(report["summary"]["total_ip"], 3)
        self.assertEqual(report["summary"]["total_with_ip"], 8)

    def test_invalid_domain_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_graduation([], {"domain": "不存在", "program": "單主修"})

    def test_earth_calculus_never_counts_as_cs_calculus(self):
        courses = [course("微積分", 3), course("微積分(I)", 3), course("微積分(II)", 3)]
        report = evaluate_graduation(
            courses,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        self.assertEqual([c["name"] for c in report["target"]["elective_courses"]], ["微積分(I)", "微積分(II)"])
        self.assertIn("微積分", [c["name"] for c in report["major"]["other_elective_courses"]])
        self.assertEqual(report["summary"]["target_completed"], 6)

    def test_earth_combined_physics_alias_is_scoped_and_credit_exact(self):
        for handbook_year in get_available_handbook_years():
            with self.subTest(handbook_year=handbook_year):
                report = evaluate_graduation(
                    [course("普通物理(含實驗)", 3)],
                    {"domain": "地球環境", "program": "單主修", "handbook_year": handbook_year},
                )
                self.assertEqual(
                    [item["name"] for item in report["major"]["other_elective_courses"]],
                    ["普通物理(含實驗)"],
                )
                self.assertEqual(report["major"]["other_elective_completed"], 3)
                self.assertEqual(report["free"]["courses"], [])

                wrong_credit = evaluate_graduation(
                    [course("普通物理(含實驗)", 2)],
                    {"domain": "地球環境", "program": "單主修", "handbook_year": handbook_year},
                )
                self.assertEqual(wrong_credit["major"]["other_elective_courses"], [])
                self.assertEqual(
                    [item["name"] for item in wrong_credit["free"]["courses"]],
                    ["普通物理(含實驗)"],
                )

    def test_earth_combined_physics_alias_never_satisfies_apc_components(self):
        report = evaluate_graduation(
            [course("普通物理(含實驗)", 3)],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "114"},
        )
        self.assertEqual(report["target"]["basic_core_completed"], 0)
        self.assertEqual(
            [item["name"] for item in report["major"]["other_elective_courses"]],
            ["普通物理(含實驗)"],
        )
        missing = [item["name"] for item in report["target"]["basic_core_missing"]]
        self.assertIn("普通物理學(一)", missing)
        self.assertIn("普通物理實驗(一)", missing)

    def test_cs_alias_does_not_cross_into_chinese_numbered_apc_course(self):
        courses = [course("微積分I", 3), course("微積分(一)", 3)]
        report = evaluate_graduation(
            courses,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        self.assertEqual([c["name"] for c in report["target"]["elective_courses"]], ["微積分I"])
        self.assertNotIn("微積分(一)", [c["name"] for c in report["target"]["elective_courses"]])

    def test_cs_does_not_accept_keyword_guesses_or_substrings(self):
        courses = [course("跨域資訊程式設計", 3), course("微積分(I)實習", 3)]
        report = evaluate_graduation(
            courses,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        self.assertEqual(report["target"]["elective_courses"], [])
        self.assertEqual(report["summary"]["target_completed"], 0)

    def test_wrong_credit_does_not_satisfy_cs_required_course(self):
        report = evaluate_graduation(
            [course("計算機概論", 2)],
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        missing = [item["name"] for item in report["target"]["compulsory_missing"]]
        self.assertIn("計算機概論", missing)
        self.assertEqual(report["target"]["compulsory_completed"], 0)

    def test_combined_lab_course_does_not_split_into_apc_components(self):
        report = evaluate_graduation(
            [course("普通物理學(含實驗)", 3)],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "114"},
        )
        self.assertEqual(report["target"]["basic_core_completed"], 0)
        missing = [item["name"] for item in report["target"]["basic_core_missing"]]
        self.assertIn("普通物理學(一)", missing)
        self.assertIn("普通物理實驗(一)", missing)

    def test_apc_unresolved_quota_does_not_consume_primary_candidates(self):
        base = [
            course("普通物理學(一)", 3), course("普通物理實驗(一)", 1),
            course("普通化學(一)", 3), course("普通化學實驗(一)", 1),
            course("普通物理學(二)", 3), course("普通物理實驗(二)", 1),
            course("普通化學(二)", 3), course("普通化學實驗(二)", 1),
        ]
        without_required = evaluate_graduation(
            base + [course("微積分(一)", 3), course("量子計算導論", 3)],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "114"},
        )
        self.assertEqual(without_required["target"]["basic_core_completed"], 16)
        self.assertEqual(without_required["target"]["compulsory_completed"], 0)
        self.assertEqual(without_required["target"]["compulsory_missing"][0]["credit"], 4)

        with_required = evaluate_graduation(
            base + [course("物理數學(一)", 3), course("電磁學實驗", 1)],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "114"},
        )
        self.assertEqual(with_required["summary"]["target_completed"], 16)
        self.assertEqual(with_required["target"]["compulsory_completed"], 0)
        self.assertEqual(with_required["target"]["compulsory_missing"][0]["credit"], 4)
        self.assertEqual(with_required["free"]["completed"], 4)

    def test_apc_unresolved_quota_conserves_unallocated_credits(self):
        base = [
            course("普通物理學(一)", 3), course("普通物理實驗(一)", 1),
            course("普通化學(一)", 3), course("普通化學實驗(一)", 1),
            course("普通物理學(二)", 3), course("普通物理實驗(二)", 1),
            course("普通化學(二)", 3), course("普通化學實驗(二)", 1),
        ]
        report = evaluate_graduation(
            base + [course("物理數學(一)", 3), course("電磁學(一)", 3), course("電磁學實驗", 1)],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "114"},
        )
        self.assertEqual(report["target"]["compulsory_completed"], 0)
        self.assertEqual(report["summary"]["target_completed"], 16)
        self.assertEqual(report["free"]["completed"], 7)
        self.assertEqual(report["summary"]["total_completed"], 23)

    def test_cs_quota_caps_completed_and_in_progress_without_losing_credits(self):
        electives = [
            course("Java程式設計", 3),
            course("離散數學", 3),
            course("數位電子學", 3),
            course("線性代數", 3),
            course("資料結構", 3),
        ]
        completed_report = evaluate_graduation(
            [course("計算機概論", 3), course("C程式設計", 3), *electives],
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        self.assertEqual(completed_report["summary"]["target_completed"], 20)
        self.assertEqual(completed_report["free"]["completed"], 1)
        self.assertEqual(completed_report["summary"]["total_completed"], 21)

        in_progress_report = evaluate_graduation(
            [course("計算機概論", 3, "未"), course("C程式設計", 3, "未"), *electives],
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        self.assertEqual(in_progress_report["summary"]["target_completed"], 14)
        self.assertEqual(in_progress_report["summary"]["target_ip"], 6)
        self.assertEqual(in_progress_report["free"]["completed"], 1)
        self.assertEqual(in_progress_report["summary"]["total_completed"], 15)
        self.assertEqual(in_progress_report["summary"]["total_ip"], 6)

    def test_112_and_113_alternative_requirements(self):
        report_112 = evaluate_graduation(
            [course("專題研究(一)", 1), course("專業實習(二)", 1)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "112"},
        )
        alternative_missing_112 = [m for m in report_112["major"]["dept_compulsory_missing"] if "擇一" in m["name"]]
        self.assertEqual(alternative_missing_112, [])

        report_113 = evaluate_graduation(
            [course("專業實習", 2)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "113"},
        )
        alternative_missing_113 = [m for m in report_113["major"]["dept_compulsory_missing"] if "擇一" in m["name"]]
        self.assertEqual(alternative_missing_113, [])

        report_114 = evaluate_graduation(
            [course("專業實習", 2)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        self.assertIn("書報討論", [m["name"] for m in report_114["major"]["dept_compulsory_missing"]])

    def test_year_specific_cs_catalog_additions(self):
        item = [course("網路安全實務與社會", 3)]
        report_113 = evaluate_graduation(
            item,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "113"},
        )
        report_114 = evaluate_graduation(
            item,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": "114"},
        )
        self.assertEqual(report_113["target"]["elective_courses"], [])
        self.assertEqual([c["name"] for c in report_114["target"]["elective_courses"]], ["網路安全實務與社會"])

    def test_same_title_different_handbook_credit_is_not_reused(self):
        report_112 = evaluate_graduation(
            [course("生物化學實驗", 2)],
            {"domain": "生命科學", "program": "單主修", "handbook_year": "112"},
        )
        report_114 = evaluate_graduation(
            [course("生物化學實驗", 2)],
            {"domain": "生命科學", "program": "單主修", "handbook_year": "114"},
        )
        self.assertEqual([c["name"] for c in report_112["major"]["domain_elective_courses"]], ["生物化學實驗"])
        self.assertEqual(report_114["major"]["domain_elective_courses"], [])

    def test_year_specific_virus_and_semiconductor_titles(self):
        for year, valid_credit in (("112", 3), ("113", 2), ("114", 2)):
            with self.subTest(year=year, rule="病毒學"):
                accepted = evaluate_graduation(
                    [course("病毒學", valid_credit)],
                    {"domain": "生命科學", "program": "單主修", "handbook_year": year},
                )
                rejected = evaluate_graduation(
                    [course("病毒學", 2 if valid_credit == 3 else 3)],
                    {"domain": "生命科學", "program": "單主修", "handbook_year": year},
                )
                self.assertEqual(accepted["major"]["domain_elective_completed"], valid_credit)
                self.assertEqual(rejected["major"]["domain_elective_completed"], 0)

        old_title = course("半導體元件物理", 3)
        new_title = course("半導體物理", 3)
        report_112 = evaluate_graduation(
            [old_title, new_title],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "112"},
        )
        report_114 = evaluate_graduation(
            [old_title, new_title],
            {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": "114"},
        )
        self.assertIn("半導體元件物理", get_rule_sets("112")["apc_rules"]["divisions"]["物理組"]["compulsory"])
        self.assertNotIn("半導體元件物理", get_rule_sets("114")["apc_rules"]["divisions"]["物理組"]["compulsory"])
        self.assertIn("半導體物理", get_rule_sets("114")["apc_rules"]["divisions"]["物理組"]["compulsory"])
        # The old APC minor pages do not name the extra four-credit pool;
        # primary-track mappings are therefore candidates, not executable
        # target requirements.  Both reports must remain review-gated.
        self.assertEqual(report_112["target"]["compulsory_courses"], [])
        self.assertEqual(report_114["target"]["compulsory_courses"], [])
        self.assertEqual(report_112["target"]["compulsory_missing"][0]["credit"], 4)
        self.assertEqual(report_114["target"]["compulsory_missing"][0]["credit"], 4)

    def test_alternative_groups_never_double_count_or_cross_stages(self):
        report_112 = evaluate_graduation(
            [course("專題研究(一)", 1), course("專業實習(一)", 1)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "112"},
        )
        self.assertEqual(report_112["major"]["dept_compulsory_completed"], 1)
        self.assertTrue(any("(二)" in item["name"] for item in report_112["major"]["dept_compulsory_missing"]))

        report_113 = evaluate_graduation(
            [course("專題研究", 2), course("專業實習", 2)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "113"},
        )
        self.assertEqual(report_113["major"]["dept_compulsory_completed"], 2)
        self.assertEqual(len(report_113["major"]["dept_compulsory_courses"]), 1)

    def test_every_official_course_round_trips_through_its_scoped_engine_bucket(self):
        """Guard every configured title, not only a few hand-picked examples."""
        for year in get_available_handbook_years():
            rules = get_rule_sets(year)
            earth = rules["earth_life_major"]

            for name, credit_value in earth["common_compulsory"].items():
                with self.subTest(year=year, scope="earth_common", course=name):
                    report = evaluate_graduation(
                        [course(name, credit_value, academic_year=year)],
                        {"domain": "地球環境", "program": "單主修", "handbook_year": year},
                    )
                    self.assertEqual([c["name"] for c in report["major"]["dept_compulsory_courses"]], [name])

            for domain in ("地球環境", "生命科學"):
                for name, credit_value in earth["domains"][domain].items():
                    with self.subTest(year=year, scope=f"{domain}_required", course=name):
                        report = evaluate_graduation(
                            [course(name, credit_value, academic_year=year)],
                            {"domain": domain, "program": "單主修", "handbook_year": year},
                        )
                        self.assertEqual([c["name"] for c in report["major"]["domain_compulsory_courses"]], [name])

                for name, credit_value in earth["domain_electives"][domain].items():
                    with self.subTest(year=year, scope=f"{domain}_elective", course=name):
                        report = evaluate_graduation(
                            [course(name, credit_value, academic_year=year)],
                            {"domain": domain, "program": "單主修", "handbook_year": year},
                        )
                        self.assertEqual([c["name"] for c in report["major"]["domain_elective_courses"]], [name])

            for name, credit_value in rules["cs_rules"]["department_courses"].items():
                with self.subTest(year=year, scope="cs", course=name):
                    report = evaluate_graduation(
                        [course(name, credit_value, academic_year=year)],
                        {"domain": "地球環境", "program": "輔系", "target_dept": "資科系", "handbook_year": year},
                    )
                    target_names = [c["name"] for c in report["target"]["compulsory_courses"]]
                    target_names += [c["name"] for c in report["target"]["elective_courses"]]
                    self.assertEqual(target_names, [name])

            apc = rules["apc_rules"]
            for name, credit_value in apc["basic_core"].items():
                with self.subTest(year=year, scope="apc_basic", course=name):
                    report = evaluate_graduation(
                        [course(name, credit_value, academic_year=year)],
                        {"domain": "地球環境", "program": "輔系", "target_dept": "物化系物理組", "handbook_year": year},
                    )
                    self.assertEqual([c["name"] for c in report["target"]["basic_core_courses"]], [name])

            for division in ("物理組", "化學組"):
                target_program = "雙主修" if year == "115" else "輔系"
                target_plan = get_apc_target_requirements(year, division, target_program)
                for target_row in target_plan["requirements"]:
                    if target_row.get("kind") != "course":
                        continue
                    name = target_row["name"]
                    credit_value = target_row["credits"]
                    with self.subTest(year=year, scope=f"apc_{division}", course=name):
                        report = evaluate_graduation(
                            [course(name, credit_value, academic_year=year)],
                            {"domain": "地球環境", "program": target_program, "target_dept": f"物化系{division}", "handbook_year": year},
                        )
                        target_names = [c["name"] for c in report["target"]["basic_core_courses"]]
                        target_names += [c["name"] for c in report["target"]["compulsory_courses"]]
                        self.assertEqual(target_names, [name])

    def test_interleaved_year_evaluations_keep_their_own_rules(self):
        first_114 = evaluate_graduation(
            [course("書報討論", 2)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        middle_112 = evaluate_graduation(
            [course("書報討論", 2)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "112"},
        )
        last_114 = evaluate_graduation(
            [course("書報討論", 2)],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        self.assertEqual(first_114["major"]["dept_compulsory_completed"], 2)
        self.assertEqual(middle_112["major"]["dept_compulsory_completed"], 0)
        self.assertEqual(last_114["major"]["dept_compulsory_completed"], 2)


if __name__ == "__main__":
    unittest.main()
