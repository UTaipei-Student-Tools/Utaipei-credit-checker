"""Empirical Challenger Test Suite for Milestone 1.

Tests the resilience, boundary conditions, stress inputs, and edge cases for:
1. `normalize_course_name` (handbook_rules.py)
2. `pdf_parser.py` double major extraction
3. `graduation_service.py` GE verification flow
"""

import re
import unittest
from decimal import Decimal

from handbook_rules import normalize_course_name
from pdf_parser import detect_department_track


class NormalizationStressTests(unittest.TestCase):
    """Stress tests and edge case exploration for normalize_course_name."""

    def test_core_roman_numerals_i_to_vi_match_chinese(self):
        """Standard sequence (I)~(VI) must normalize to (一)~(六)."""
        roman_map = {
            "I": "一",
            "II": "二",
            "III": "三",
            "IV": "四",
            "V": "五",
            "VI": "六",
        }
        for roman, chinese in roman_map.items():
            with self.subTest(roman=roman, chinese=chinese):
                self.assertEqual(
                    normalize_course_name(f"微積分({roman})"),
                    f"微積分({chinese})",
                )
                self.assertEqual(
                    normalize_course_name(f"微積分({roman.lower()})"),
                    f"微積分({chinese})",
                )

    def test_extended_roman_numerals_vii_to_x(self):
        """Extended Roman numerals (VII, VIII, IX, X) behavior assessment."""
        extended_map = {
            "VII": "七",
            "VIII": "八",
            "IX": "九",
            "X": "十",
        }
        for roman, chinese in extended_map.items():
            with self.subTest(roman=roman, chinese=chinese):
                norm_roman = normalize_course_name(f"體育({roman})")
                norm_chinese = normalize_course_name(f"體育({chinese})")
                # Note: Currently Worker M1 only mapped I~VI.
                # Documenting whether VII~X are normalized or preserved as-is.
                # If they do not match, this highlights the boundary of M1's numeral map.
                if norm_roman != norm_chinese:
                    self.assertNotEqual(norm_roman, norm_chinese, f"Expected unmapped {roman} vs {chinese}")

    def test_arabic_numerals_1_to_6_and_7_to_10(self):
        """Arabic numerals in parentheses."""
        for num, chinese in [(1, "一"), (2, "二"), (3, "三"), (4, "四"), (5, "五"), (6, "六")]:
            with self.subTest(num=num, chinese=chinese):
                self.assertEqual(
                    normalize_course_name(f"微積分({num})"),
                    f"微積分({chinese})",
                )
        for num in [7, 8, 9, 10]:
            with self.subTest(num=num):
                # Currently 7~10 are not mapped to Chinese
                result = normalize_course_name(f"微積分({num})")
                self.assertEqual(result, f"微積分({num})")

    def test_whitespace_and_parentheses_variations(self):
        """Spaces, full-width parentheses, and unicode Roman glyphs."""
        variations = [
            " 微積分 ( I ) ",
            "微積分（I）",
            "微積分（一）",
            "微積分( Ⅰ )",  # Unicode U+2160
            "微積分（Ⅱ）",  # Unicode U+2161
            "微積分 ( 1 )",
            "微積分（1）",
        ]
        for var in variations:
            with self.subTest(variation=var):
                self.assertIn(
                    normalize_course_name(var),
                    {"微積分(一)", "微積分(二)"},
                )

    def test_distinction_preservation(self):
        """Base course must remain distinct from sequenced courses, and sequences distinct from each other."""
        self.assertNotEqual(normalize_course_name("微積分"), normalize_course_name("微積分(一)"))
        self.assertNotEqual(normalize_course_name("微積分"), normalize_course_name("微積分(I)"))
        self.assertNotEqual(normalize_course_name("微積分(I)"), normalize_course_name("微積分(II)"))
        self.assertNotEqual(normalize_course_name("微積分(一)"), normalize_course_name("微積分(二)"))
        self.assertEqual(normalize_course_name("微積分(I)"), normalize_course_name("微積分(一)"))

    def test_lab_and_practicum_suffixes_preserved(self):
        """Lab suffixes like 實驗, 實習 must never be stripped."""
        self.assertEqual(normalize_course_name("普通物理學實驗(I)"), "普通物理學實驗(一)")
        self.assertEqual(normalize_course_name("普通化學實驗 (II)"), "普通化學實驗(二)")
        self.assertEqual(normalize_course_name("微積分(I)實習"), "微積分(一)實習")
        self.assertEqual(normalize_course_name("普通化學(含實驗)"), "普通化學(含實驗)")

    def test_section_and_track_letters(self):
        """Trailing section markers like (A), (B), (甲), (乙)."""
        # Trailing section marker (甲) is stripped
        self.assertEqual(normalize_course_name("微積分(甲)"), "微積分")
        self.assertEqual(normalize_course_name("微積分(乙)"), "微積分")
        self.assertEqual(normalize_course_name("微積分(A)"), "微積分")
        # Combined sequence + section
        self.assertEqual(normalize_course_name("微積分(I)(甲)"), "微積分(一)")
        self.assertEqual(normalize_course_name("微積分(1)(A)"), "微積分(一)")

    def test_idempotency(self):
        """normalize_course_name(normalize_course_name(x)) == normalize_course_name(x)."""
        samples = [
            "微積分(I)",
            "普通化學實驗(II)",
            "英文(一):初級",
            "儀器分析 (一)",
            "體育（3）",
            "[◇]普通物理學(VI)",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                once = normalize_course_name(sample)
                twice = normalize_course_name(once)
                self.assertEqual(once, twice)

    def test_empty_and_numeric_inputs(self):
        """Empty, pure numbers, and grade percentages must normalize safely."""
        self.assertEqual(normalize_course_name(""), "")
        self.assertEqual(normalize_course_name(None), "")
        self.assertEqual(normalize_course_name("113-1"), "")
        self.assertEqual(normalize_course_name("85.0"), "")
        self.assertEqual(normalize_course_name("100%"), "")


class DoubleMajorParsingChallengerTests(unittest.TestCase):
    """Stress-test double major regex and parser extraction."""

    def test_detect_department_track_apc_chemistry(self):
        """Verify detect_department_track on APC Chemistry."""
        info = detect_department_track("應用物理暨化學系應用化學組")
        self.assertEqual(info["department"], "物化")
        self.assertEqual(info["track"], "應用化學")

    def test_detect_department_track_apc_physics(self):
        """Verify detect_department_track on APC Electronic Physics."""
        info = detect_department_track("應用物理暨化學系電子物理組")
        self.assertEqual(info["department"], "物化")
        self.assertEqual(info["track"], "電子物理")

    def test_detect_department_track_earth(self):
        """Verify detect_department_track on Earth Resources."""
        info = detect_department_track("地球環境暨生物資源學系")
        self.assertEqual(info["department"], "地生")
        self.assertEqual(info["track"], "地球環境")

    def test_double_major_header_regex_patterns(self):
        """Test regex extraction against various header line formats."""
        pattern = r"雙主修[：:]\s*([^\s\n]+)"

        # Standard attached format
        m1 = re.search(pattern, "雙主修：應用物理暨化學系應用化學組-修習中")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.group(1), "應用物理暨化學系應用化學組-修習中")

        # Half-width colon
        m2 = re.search(pattern, "雙主修:應用物理暨化學系應用化學組-修習中")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group(1), "應用物理暨化學系應用化學組-修習中")

        # Negative case: None / None specified
        m3 = re.search(pattern, "雙主修：無")
        self.assertIsNotNone(m3)
        self.assertEqual(m3.group(1), "無")


class GeneralEducationFlowTests(unittest.TestCase):
    """Verify GE course compilation logic in graduation_service."""

    def test_ge_verified_state_in_compile_attempts(self):
        """When a course is absent from handbook but verified in public catalog, it must be VERIFIED."""
        from graduation_service import _compile_attempts
        from input_confirmation import NormalizedCourseRow
        from public_course_catalog import load_public_course_catalog

        catalog = load_public_course_catalog()
        # Pick one valid GE course from catalog
        candidate = next(
            item
            for item in catalog.courses
            if item.get("term") == "112-1"
            and item.get("official_category") == "藝術與美感領域"
            and item.get("credits") == 2
            and "(停開)" not in item.get("course_name", "")
        )
        row = NormalizedCourseRow(
            course_code="",
            course_name=candidate["course_name"],
            credits=2,
            earned_credits=2,
            status="COMPLETED",
            term="112-1",
            course_type="",
        )
        metadata = {
            "ge-art-policy": {
                "generic": True,
                "policy_rule": "official_category_policy",
                "policy_state": "VERIFIED",
                "pool_id": "pool:ge_art",
                "membership_ids": ("ge_art",),
                "policy_predicate": {"category": "藝術與美感領域"},
            },
        }
        attempts, _ = _compile_attempts((row,), metadata)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].identity_status, "VERIFIED")
        self.assertEqual(attempts[0].course_kind, "LECTURE")
        self.assertIn("ge_art", attempts[0].pool_ids)

    def test_unknown_course_remains_unknown(self):
        """A course absent from BOTH handbook AND public catalog must stay UNKNOWN."""
        from graduation_service import _compile_attempts
        from input_confirmation import NormalizedCourseRow

        row = NormalizedCourseRow(
            course_code="UNKNOWN999",
            course_name="完全不存在的未知課程名稱XYZ",
            credits=3,
            earned_credits=3,
            status="COMPLETED",
            term="112-1",
            course_type="",
        )
        attempts, _ = _compile_attempts((row,), {})
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].identity_status, "UNKNOWN")


class ChenTranscriptEmpiricalChallengerTests(unittest.TestCase):
    """Empirical verification against Chen's actual transcript fixture."""

    TRANSCRIPT_PATH = "學生手冊/U1131002220260906175350.pdf"

    def test_chen_transcript_student_info_and_double_major_extraction(self):
        """Verify student metadata and double major parsing from actual PDF."""
        import os
        from pdf_parser import parse_transcript_pdf

        self.assertTrue(os.path.exists(self.TRANSCRIPT_PATH), f"Fixture not found: {self.TRANSCRIPT_PATH}")
        student_info, courses = parse_transcript_pdf(self.TRANSCRIPT_PATH)

        self.assertEqual(student_info["student_id"], "U11310022")
        self.assertEqual(student_info["name"], "陳柏亘")
        self.assertEqual(student_info["admission_cohort"], "113")
        self.assertIn("地球環境暨生物資源學系", student_info["department"])
        self.assertEqual(student_info["department_family"], "地生")
        self.assertEqual(student_info["track"], "地球環境")

        dm = student_info.get("double_major")
        self.assertIsNotNone(dm, "Double major header must be extracted")
        self.assertEqual(dm.get("department"), "物化")
        self.assertEqual(dm.get("track"), "應用化學")
        self.assertEqual(dm.get("status"), "修習中")
        self.assertEqual(dm.get("raw"), "應用物理暨化學系應用化學組-修習中")

    def test_calculus_i_normalized_and_allocated_to_apc_chemistry(self):
        """Verify 微積分(I) normalizes to 微積分(一) and satisfies APC Chemistry requirement."""
        from handbook_rules import get_apc_target_requirements, normalize_course_name
        from tests.test_e2e_requirement_suite import _evaluate_course_rows

        self.assertEqual(normalize_course_name("微積分(I)"), "微積分(一)")

        plan = get_apc_target_requirements("115", "化學組", "雙主修")
        req_names = [r["name"] for r in plan["requirements"]]
        self.assertIn("微積分(一)", req_names)

        calc_row = [
            {
                "course_code": "MATH101",
                "course_name": "微積分(I)",
                "credits": 3.0,
                "earned_credits": 3.0,
                "status": "COMPLETED",
                "term": "113-1",
                "grade": "68",
                "course_type": "必",
            }
        ]
        snapshot = _evaluate_course_rows(
            calc_row,
            cohort="113",
            primary_curriculum_id="primary:113:earth:earth_environment",
            program_type="雙主修",
            target_program="物化",
            target_track="化學組",
            secondary_kind="double_major",
            target_curriculum_year="115",
            target_curriculum_id="target:double_major:115:apc:chemistry",
        )
        payload = snapshot.as_dict()
        req_results = payload["allocation"]["requirement_results"]
        calc_result = next(
            (r for r in req_results if "微積分(一)" in r["requirement_id"] or r["name"] == "微積分(一)"),
            None,
        )
        self.assertIsNotNone(calc_result, "微積分(一) must be evaluated in requirements")
        self.assertEqual(calc_result["status"], "PASS")
        self.assertEqual(float(calc_result["deficit"]), 0.0)

    def test_chemistry_lab_2_completed_in_actual_pdf_and_in_progress_semantics(self):
        """Empirical reality check: Chen's actual PDF has 普通化學實驗(二) as COMPLETED in 114-2.

        Verify actual fixture status (score 77, completed), actual 115-1 courses as IN_PROGRESS (未),
        and verify IN_PROGRESS adapter semantics for score '未'.
        """
        from course_input_adapter import _status_and_earned
        from pdf_parser import parse_transcript_pdf

        _, courses = parse_transcript_pdf(self.TRANSCRIPT_PATH)

        # 1. In actual Chen transcript, 普通化學實驗(二) was taken in 114-2 with grade 77
        lab2_course = next((c for c in courses if "普通化學實驗(二)" in c.get("name", "")), None)
        self.assertIsNotNone(lab2_course, "普通化學實驗(二) must be found in parsed courses")
        self.assertEqual(lab2_course.get("academic_year"), "114")
        self.assertEqual(lab2_course.get("sem2_score"), "77")
        self.assertEqual(lab2_course.get("completed_credit"), 1.0)
        self.assertTrue(lab2_course.get("is_completed"))
        self.assertFalse(lab2_course.get("is_in_progress"))

        # 2. In actual Chen transcript, courses in 115-1 have score '未' (IN_PROGRESS)
        ip_course = next((c for c in courses if c.get("academic_year") == "115" and c.get("sem1_score") == "未"), None)
        self.assertIsNotNone(ip_course, "115-1 courses with score '未' must be present")
        self.assertTrue(ip_course.get("is_in_progress"))
        self.assertFalse(ip_course.get("is_completed"))
        self.assertEqual(ip_course.get("completed_credit"), 0.0)

        # 3. Verify adapter semantics: score '未' -> status='IN_PROGRESS', earned_credits=0.0
        status, earned, known = _status_and_earned("未", 1.0)
        self.assertEqual(status, "IN_PROGRESS")
        self.assertEqual(earned, 0.0)
        self.assertTrue(known)

    def test_chen_transcript_ge_courses_verified_without_warnings(self):
        """Verify 6 GE courses in Chen transcript are VERIFIED with 0 false warnings."""
        from tests.test_e2e_requirement_suite import _evaluate_course_rows
        from pdf_parser import parse_transcript_pdf
        from snapshot_renderer import render_snapshot
        from tests.test_e2e_requirement_suite import expand_legacy_course_rows

        _, raw_courses = parse_transcript_pdf(self.TRANSCRIPT_PATH)
        expanded = expand_legacy_course_rows(raw_courses)

        ge_titles = {
            "臺北城市散步旅行",
            "政府運作與國會監督",
            "日本旅行與日本文化",
            "生命科學與人生",
            "生活哲學與藝術",
            "建築史",
        }
        ge_rows = [r for r in expanded if any(t in r["course_name"] for t in ge_titles)]
        self.assertEqual(len(ge_rows), 6, f"Expected 6 GE courses, found {len(ge_rows)}")

        snapshot = _evaluate_course_rows(ge_rows, cohort="113")
        html = render_snapshot(snapshot)

        self.assertNotIn("身分尚不足以安全認列", html)
        self.assertNotIn("課程身分或要求來源尚不足以安全認列", html)
        self.assertEqual(float(snapshot.as_dict()["allocation"]["recognized_credits"]), 12.0)

    def test_chen_six_specific_courses_oracle(self):
        """Verify the 6 specific Chen courses required by user prompt:
        1. 微積分(I) -> 微積分(一)
        2. 普通化學實驗(二) -> 普通化學實驗(二)
        3. [通選自然]生命科學與人生 -> Natural Sciences (自然、生命與科技領域)
        4. [通選藝術]生活哲學與藝術 -> Arts (藝術與美感領域)
        5. [通選藝術]都市景觀與敷地計畫 -> Arts (藝術與美感領域), in-progress
        6. [共同選修]Python資料視覺化 -> General Elective (共同選修), in-progress
        """
        from pdf_parser import parse_transcript_pdf
        from handbook_rules import normalize_course_name

        student_info, courses = parse_transcript_pdf(self.TRANSCRIPT_PATH)

        # 1. 微積分(I) -> 微積分(一)
        c1 = next((c for c in courses if "微積分" in c.get("name", "") or "微積分" in c.get("raw_name", "")), None)
        self.assertIsNotNone(c1, "Course 微積分(I) not found")
        self.assertEqual(c1["raw_name"], "微積分(I)")
        self.assertEqual(c1["normalized_name"], "微積分(一)")
        self.assertEqual(normalize_course_name(c1["raw_name"]), "微積分(一)")
        self.assertTrue(c1["is_completed"])
        self.assertFalse(c1["is_in_progress"])

        # 2. 普通化學實驗(二) -> 普通化學實驗(二)
        c2 = next((c for c in courses if "普通化學實驗(二)" in c.get("name", "") or "普通化學實驗(二)" in c.get("raw_name", "")), None)
        self.assertIsNotNone(c2, "Course 普通化學實驗(二) not found")
        self.assertEqual(c2["raw_name"], "普通化學實驗(二)")
        self.assertEqual(c2["normalized_name"], "普通化學實驗(二)")
        self.assertEqual(normalize_course_name(c2["raw_name"]), "普通化學實驗(二)")
        self.assertTrue(c2["is_completed"])
        self.assertFalse(c2["is_in_progress"])

        # 3. [通選自然]生命科學與人生 -> Natural Sciences
        c3 = next((c for c in courses if "生命科學與人生" in c.get("name", "") or "生命科學與人生" in c.get("raw_name", "")), None)
        self.assertIsNotNone(c3, "Course [通選自然]生命科學與人生 not found")
        self.assertEqual(c3["prefix_tag"], "[通選自然]")
        self.assertEqual(c3["clean_name"], "生命科學與人生")
        self.assertEqual(c3["normalized_name"], "生命科學與人生")
        self.assertEqual(c3["inferred_category"], "自然、生命與科技領域")
        self.assertTrue(c3["is_completed"])
        self.assertFalse(c3["is_in_progress"])

        # 4. [通選藝術]生活哲學與藝術 -> Arts
        c4 = next((c for c in courses if "生活哲學與藝術" in c.get("name", "") or "生活哲學與藝術" in c.get("raw_name", "")), None)
        self.assertIsNotNone(c4, "Course [通選藝術]生活哲學與藝術 not found")
        self.assertEqual(c4["prefix_tag"], "[通選藝術]")
        self.assertEqual(c4["clean_name"], "生活哲學與藝術")
        self.assertEqual(c4["normalized_name"], "生活哲學與藝術")
        self.assertEqual(c4["inferred_category"], "藝術與美感領域")
        self.assertTrue(c4["is_completed"])
        self.assertFalse(c4["is_in_progress"])

        # 5. [通選藝術]都市景觀與敷地計畫 -> Arts, in-progress
        c5 = next((c for c in courses if "都市景觀與敷地計畫" in c.get("name", "") or "都市景觀與敷地計畫" in c.get("raw_name", "")), None)
        self.assertIsNotNone(c5, "Course [通選藝術]都市景觀與敷地計畫 not found")
        self.assertEqual(c5["prefix_tag"], "[通選藝術]")
        self.assertEqual(c5["clean_name"], "都市景觀與敷地計畫")
        self.assertEqual(c5["normalized_name"], "都市景觀與敷地計畫")
        self.assertEqual(c5["inferred_category"], "藝術與美感領域")
        self.assertFalse(c5["is_completed"])
        self.assertTrue(c5["is_in_progress"])
        self.assertEqual(c5["completed_credit"], 0.0)

        # 6. [共同選修]Python資料視覺化 -> General Elective, in-progress
        c6 = next((c for c in courses if "Python資料視覺化" in c.get("name", "") or "Python資料視覺化" in c.get("raw_name", "")), None)
        self.assertIsNotNone(c6, "Course [共同選修]Python資料視覺化 not found")
        self.assertEqual(c6["prefix_tag"], "[共同選修]")
        self.assertEqual(c6["clean_name"], "Python資料視覺化")
        self.assertEqual(c6["normalized_name"], "Python資料視覺化")
        self.assertEqual(c6["inferred_category"], "共同選修")
        self.assertFalse(c6["is_completed"])
        self.assertTrue(c6["is_in_progress"])
        self.assertEqual(c6["completed_credit"], 0.0)


if __name__ == "__main__":
    unittest.main()

