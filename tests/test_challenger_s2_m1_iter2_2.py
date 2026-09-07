"""Challenger Empirical Test Suite for Milestone 1 Iteration 2.

Covers:
1. `test_normalization_keeps_only_explicit_analysis_fields_and_reports_unknowns` compatibility.
2. Courses with special characters, Roman numerals, and in-progress status.
3. UI state integrity and markdown table rendering (pipe escaping, single-render details).
4. Status conflict checking (IN_PROGRESS with earned credits).
"""

import unittest
from input_confirmation import (
    COURSE_FIELD_ALLOWLIST,
    NormalizedCourseRow,
    normalize_course_rows,
)
from handbook_rules import normalize_course_name
from pdf_parser import transcript_to_markdown
from course_input_adapter import adapt_transcript_records, _status_and_earned


class TestInputConfirmationCompatibility(unittest.TestCase):
    """Verify as_dict() conditional projection and allowlist boundaries."""

    def test_normalization_keeps_only_explicit_analysis_fields_when_ast_empty(self):
        """When AST fields are empty/omitted, as_dict() must strictly match the 12 base fields."""
        input_row = {
            "course_code": "CS-101",
            "course_name": "資料結構",
            "credits": 3,
            "earned_credits": 3,
            "status": "COMPLETED",
            "term": "113-1",
            "password": "do-not-store",
            "raw_pdf": b"secret",
            "extra_note": "不要進分析",
        }
        result = normalize_course_rows([input_row])

        self.assertFalse(result.valid)
        self.assertEqual(len(result.rows), 1)
        base_12_fields = {
            "course_code",
            "course_name",
            "credits",
            "earned_credits",
            "status",
            "term",
            "academic_year",
            "semester",
            "grade",
            "attempt_group",
            "department",
            "course_type",
        }
        row_dict = result.rows[0].as_dict()
        self.assertTrue(
            set(row_dict) <= base_12_fields,
            f"Expected row keys to be subset of 12 base fields, got: {set(row_dict)}",
        )
        self.assertEqual(set(row_dict), base_12_fields)

    def test_normalization_includes_ast_fields_when_populated(self):
        """When AST fields are provided with values, as_dict() includes them."""
        row = NormalizedCourseRow(
            course_code="CHE101",
            course_name="普通化學",
            credits=3,
            earned_credits=3,
            status="COMPLETED",
            term="113-1",
            raw_name="[通選自然]普通化學",
            prefix_tag="[通選自然]",
            clean_name="普通化學",
            normalized_name="普通化學",
            inferred_category="自然、生命與科技領域",
        )
        row_dict = row.as_dict()
        self.assertIn("raw_name", row_dict)
        self.assertIn("prefix_tag", row_dict)
        self.assertIn("clean_name", row_dict)
        self.assertIn("normalized_name", row_dict)
        self.assertIn("inferred_category", row_dict)
        self.assertEqual(row_dict["prefix_tag"], "[通選自然]")
        self.assertEqual(row_dict["inferred_category"], "自然、生命與科技領域")

    def test_in_progress_with_positive_earned_credits_triggers_conflict(self):
        """IN_PROGRESS with earned_credits > 0 must trigger STATUS_EARNED_CREDITS_CONFLICT."""
        input_row = {
            "course_code": "CS-102",
            "course_name": "演算法",
            "credits": 3,
            "earned_credits": 3,  # Invalid for IN_PROGRESS
            "status": "IN_PROGRESS",
            "term": "115-1",
        }
        result = normalize_course_rows([input_row])
        self.assertFalse(result.valid)
        diag_codes = {d.code for d in result.diagnostics}
        self.assertIn("STATUS_EARNED_CREDITS_CONFLICT", diag_codes)

    def test_in_progress_with_zero_earned_credits_is_valid(self):
        """IN_PROGRESS with earned_credits == 0 must NOT trigger conflict."""
        input_row = {
            "course_code": "CS-102",
            "course_name": "演算法",
            "credits": 3,
            "earned_credits": 0,
            "status": "IN_PROGRESS",
            "term": "115-1",
        }
        result = normalize_course_rows([input_row])
        diag_codes = {d.code for d in result.diagnostics}
        self.assertNotIn("STATUS_EARNED_CREDITS_CONFLICT", diag_codes)


class TestSpecialCharactersAndRomanNumerals(unittest.TestCase):
    """Test course name normalization on special symbols, Roman numerals, and suffixes."""

    def test_roman_numerals_i_to_vi_and_variants(self):
        cases = [
            ("微積分(I)", "微積分(一)"),
            ("微積分(II)", "微積分(二)"),
            ("微積分(III)", "微積分(三)"),
            ("微積分(IV)", "微積分(四)"),
            ("微積分(V)", "微積分(五)"),
            ("微積分(VI)", "微積分(六)"),
            ("微積分(i)", "微積分(一)"),
            ("微積分(ii)", "微積分(二)"),
            ("微積分 ( I )", "微積分(一)"),
            ("微積分（I）", "微積分(一)"),
            ("微積分（一）", "微積分(一)"),
            ("微積分( Ⅰ )", "微積分(一)"),
            ("微積分（Ⅱ）", "微積分(二)"),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_course_name(inp), expected)

    def test_special_characters_and_bullet_symbols(self):
        cases = [
            ("[◇]普通物理學(VI)", "普通物理學(六)"),
            ("※普通化學", "普通化學"),
            ("◎地球科學概論", "地球科學概論"),
            ("★生態學", "生態學"),
            ("●環境變遷", "環境變遷"),
            ("微積分：初級", "微積分:初級"),
            ("英文(一):初級", "英文(一)"),
            ("微積分(甲)", "微積分"),
            ("微積分(A)", "微積分"),
            ("微積分(I)(甲)", "微積分(一)"),
            ("微積分(1)(A)", "微積分(一)"),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_course_name(inp), expected)

    def test_adapter_resolved_name_without_prefix_tag(self):
        """Verify course_input_adapter resolves normalized name even without prefix tags."""
        raw_rows = [
            {
                "name": "微積分(I)",
                "credits": 3.0,
                "sem1_credit": "3",
                "sem1_score": "80",
                "academic_year": "113",
                "type": "必",
            }
        ]
        attempts = adapt_transcript_records(raw_rows)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["course_name"], "微積分(一)")


class TestMarkdownTableRenderingAndPipeEscaping(unittest.TestCase):
    """Verify transcript_to_markdown formatting, GFM pipe escaping, and credit tallies."""

    def test_pipe_characters_are_escaped_in_table(self):
        """Pipe characters '|' in name, tag, or notes must be escaped as '\\|'."""
        courses = [
            {
                "name": "專題研究 | 成果展示",
                "prefix_tag": "[通選|跨向]",
                "course_type": "選|必",
                "academic_year": "113",
                "semester_code": "1",
                "credits": 2.0,
                "status": "COMPLETED",
                "earned_credits": 2.0,
                "grade": "88",
                "inferred_category": "藝術與美感|跨向領域",
            }
        ]
        md = transcript_to_markdown(courses, collapsible=False)
        for line in md.strip().split("\n"):
            if line.startswith("|") and not line.startswith("|:"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                self.assertEqual(len(cells), 8, f"Expected 8 columns, line was split into {len(cells)} cells: {line}")
        self.assertIn("專題研究 \\| 成果展示", md)
        self.assertIn("[通選\\|跨向]", md)

    def test_transcript_to_markdown_supports_both_parser_and_normalized_dicts(self):
        """Verify transcript_to_markdown handles both parser output and normalized rows."""
        parser_course = {
            "name": "生命科學與人生",
            "normalized_name": "生命科學與人生",
            "prefix_tag": "[通選自然]",
            "inferred_category": "自然、生命與科技領域",
            "academic_year": "113",
            "sem1_credit": "2",
            "sem1_score": "85",
            "total_credit": 2.0,
            "completed_credit": 2.0,
            "is_completed": True,
            "is_in_progress": False,
        }
        normalized_course = {
            "course_name": "都市景觀與敷地計畫",
            "normalized_name": "都市景觀與敷地計畫",
            "prefix_tag": "[通選藝術]",
            "inferred_category": "藝術與美感領域",
            "term": "115-1",
            "academic_year": "115",
            "semester": "1",
            "credits": 2.0,
            "earned_credits": 0.0,
            "status": "IN_PROGRESS",
            "grade": "未",
        }
        student_info = {
            "name": "測試生",
            "student_id": "U11300001",
            "department": "地球環境暨生物資源學系",
            "track": "地球環境組",
            "double_major": {"department": "物化", "track": "化學組", "status": "修習中"},
        }
        md = transcript_to_markdown([parser_course, normalized_course], student_info=student_info)
        self.assertIn("<details>", md)
        self.assertIn("</details>", md)
        self.assertIn("已修畢 **2** 學分", md)
        self.assertIn("修習中 **2** 學分", md)
        self.assertIn("累計 **4** 學分", md)
        self.assertIn("已修畢", md)
        self.assertIn("修習中", md)
        self.assertIn("自然、生命與科技領域", md)
        self.assertIn("藝術與美感領域（修習中，完成後認列）", md)

    def test_student_info_with_missing_double_major_keys_does_not_crash(self):
        """If double_major dict lacks 'department' or 'track', it must not raise KeyError."""
        courses = [{"name": "普通物理學", "credits": 3.0, "status": "COMPLETED", "earned_credits": 3.0}]
        student_info = {
            "name": "無雙主修生",
            "student_id": "U11300002",
            "double_major": {},
        }
        md = transcript_to_markdown(courses, student_info=student_info)
        self.assertIn("雙主修", md)


if __name__ == "__main__":
    unittest.main()
