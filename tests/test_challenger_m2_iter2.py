"""Adversarial stress-test suite for Milestone 2 Iteration 2 remediations.

Covers:
1. equivalency_ui table builders under extreme hostile inputs.
2. sidebar._curriculum_label under unmapped colon strings, UUIDs, custom schemes, empty strings.
3. Verification of line 251 and status warning messages in equivalency_ui.py.
"""

from __future__ import annotations

import re
import unittest
from typing import Any

from equivalency_ui import (
    _build_candidate_frame,
    _build_decision_frame,
    _build_missing_frame,
    _course_label,
    _format_target_requirement_label,
)
from sidebar import _curriculum_label

FORBIDDEN_PATTERN = re.compile(
    r"\b(?:REQUIREMENT_|APPLICATION:|SEARCH_IN|SEARCH_EX|handbook:\d|primary:\d|target:\d|"
    r"WAIVER_DECISION_REQUIRED|RULE_CONTEXT:MANUAL_REVIEW|CREDIT_CONSERVATION_FAILED|"
    r"attempt:|uuid:|custom:)\b"
)


class TestAdversarialEquivalencyUI(unittest.TestCase):
    """Hostile input stress tests on equivalency_ui.py table builders."""

    def _assert_zero_forbidden_in_dataframe(self, df, context_msg=""):
        """Check all string representations in all cells of a DataFrame."""
        for col in df.columns:
            for val in df[col]:
                val_str = str(val)
                match = FORBIDDEN_PATTERN.search(val_str)
                self.assertIsNone(
                    match,
                    f"Forbidden token '{match.group(0) if match else ''}' found in column '{col}': '{val_str}' [{context_msg}]",
                )

    def test_candidate_frame_hostile_inputs(self):
        """Candidate frame under extreme hostile inputs (hashes, UUIDs, dotted IDs, missing keys)."""
        hostile_candidates = [
            # 1. 64-char sha256 attempt hash + dotted apc.dm ID
            {
                "source_attempt_id": "attempt:v2:46b3f9180708f51a1362e6d9d16b1e6057bc6719ab1f6fce7c99277d3f11d13f",
                "source_course_name": "微積分(I)",
                "target_requirement_id": "apc.dm.115.chemistry.calculus_1",
                "target_requirement_name": "微積分(一)",
                "state": "proposed",
                "reason": "REQUIREMENT_DEFICIT:123 需人工審查",
            },
            # 2. Raw UUID in target requirement ID + unmapped colon reason
            {
                "source_attempt_id": "uuid:550e8400-e29b-41d4-a716-446655440000",
                "source_course_name": "普通物理學",
                "target_requirement_id": "uuid:e7b0c442-98fc-1c14-9afb-f4c8996fb924",
                "target_requirement_name": "物理專題",
                "state": "pending",
                "reason": "APPLICATION:DOUBLE_MAJOR_NOT_APPROVED",
            },
            # 3. Custom scheme in target requirement ID + missing target name
            {
                "source_attempt_id": "custom:113:physics",
                "source_course_name": "有機化學實驗",
                "target_requirement_id": "custom:115:chemistry:lab",
                "target_requirement_name": "",
                "state": "rejected",
                "reason": "CREDIT_CONSERVATION_FAILED",
            },
            # 4. Deep dotted non-apc ID + citation target ID
            {
                "source_attempt_id": "64_char_raw_hash_0123456789abcdef0123456789abcdef0123456789abcdef",
                "source_course_name": "分析化學",
                "target_requirement_id": "dept.track.cohort.program.module.submodule.course_xyz",
                "target_requirement_name": "",
                "state": "approved",
                "reason": "handbook:113:earth:p.45",
            },
            # 5. Target citation code
            {
                "source_attempt_id": "attempt:v2:9999999999999999999999999999999999999999999999999999999999999999",
                "source_course_name": "無機化學",
                "target_requirement_id": "target:115:apc:chemistry:compulsory:chem_lab_1",
                "target_requirement_name": "普通化學實驗(一)",
                "state": "proposed",
                "reason": "RULE_CONTEXT:MANUAL_REVIEW",
            },
            # 6. Completely empty candidate item
            {},
            # 7. Candidate item with all None values
            {
                "source_attempt_id": None,
                "source_course_name": None,
                "target_requirement_id": None,
                "target_requirement_name": None,
                "state": None,
                "reason": None,
            },
            # 8. Blocker tokens embedded in reason and state
            {
                "source_attempt_id": "attempt:v2:1111",
                "source_course_name": "地質學",
                "target_requirement_id": "REQUIREMENT_COVERAGE_UNKNOWN:113:earth",
                "target_requirement_name": "地質學概論",
                "state": "WAIVER_DECISION_REQUIRED",
                "reason": "SEARCH_INCOMPLETE: 深度已達上限，SEARCH_EXHAUSTED",
            },
        ]

        df = _build_candidate_frame(hostile_candidates)
        self._assert_zero_forbidden_in_dataframe(df, "Hostile candidate frame")

        # Verify specific clean values
        self.assertEqual(df.loc[0, "來源修課編號"], "第 1 門修課")
        self.assertEqual(df.loc[0, "來源修課"], "微積分(I)")
        self.assertIn("微積分(一)", df.loc[0, "目標要求"])
        self.assertEqual(df.loc[0, "狀態"], "候選／建議")

    def test_decision_frame_hostile_inputs(self):
        """Decision frame under extreme hostile inputs."""
        hostile_decisions = [
            # 1. 64-char sha256 attempt hash + blocker tokens in authority & evidence
            {
                "source_attempt_id": "attempt:v2:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
                "source_course_name": "普通化學",
                "target_requirement_id": "target:115:apc:chemistry:compulsory:chem_lab_1",
                "target_requirement_name": "普通化學實驗(一)",
                "state": "approved",
                "authority": "APPLICATION:APPLICATION_FORMAL_APPROVAL_MISSING",
                "evidence_reference": "handbook:113:earth:p.45",
                "approved_credits": "1.0",
            },
            # 2. Raw UUIDs in requirement and authority
            {
                "source_attempt_id": "uuid:11112222-3333-4444-5555-666677778888",
                "source_course_name": "微積分(一)",
                "target_requirement_id": "uuid:99998888-7777-6666-5555-444433332222",
                "target_requirement_name": "基礎微積分",
                "state": "rejected",
                "authority": "uuid:admin-uuid-12345",
                "evidence_reference": "custom:manual:ref",
                "approved_credits": None,
            },
            # 3. Blocker token in state and credit string corruption
            {
                "source_attempt_id": "attempt:v2:0000",
                "source_course_name": "",
                "target_requirement_id": "apc.dm.115.chemistry.calculus_1",
                "target_requirement_name": "",
                "state": "WAIVER_DECISION_REQUIRED",
                "authority": "RULE_CONTEXT:MANUAL_REVIEW",
                "evidence_reference": "CREDIT_CONSERVATION_FAILED",
                "approved_credits": "invalid_float",
            },
            # 4. Completely empty dict
            {},
        ]

        df = _build_decision_frame(hostile_decisions)
        self._assert_zero_forbidden_in_dataframe(df, "Hostile decision frame")

        self.assertEqual(df.loc[0, "來源修課編號"], "第 1 門修課")
        self.assertEqual(df.loc[0, "來源課程"], "普通化學")
        self.assertEqual(df.loc[0, "狀態"], "已核准（需證據）")

    def test_missing_frame_hostile_inputs(self):
        """Missing frame under extreme hostile inputs."""
        hostile_missing = [
            # 1. Dotted apc.dm requirement
            {
                "target_requirement_id": "apc.dm.115.chemistry.calculus_1",
                "name": "微積分(一)",
                "category": "專業必修",
                "credit": 3.0,
            },
            # 2. Raw UUID requirement ID
            {
                "target_requirement_id": "uuid:550e8400-e29b-41d4-a716-446655440000",
                "target_requirement_name": "高等物理選修",
                "category": "custom:category",
                "credit": "2.0",
            },
            # 3. Citation requirement ID
            {
                "target_requirement_id": "target:115:apc:chemistry:compulsory:chem_lab_1",
                "target_requirement_name": "普通化學實驗(一)",
                "credit": 1.0,
            },
            # 4. Blocker token as requirement ID
            {
                "target_requirement_id": "REQUIREMENT_DEFICIT:apc_chem_core",
                "target_requirement_name": "",
                "category": "基礎核心必修",
                "credit": None,
            },
            # 5. Empty dictionary
            {},
        ]

        df = _build_missing_frame(hostile_missing)
        self._assert_zero_forbidden_in_dataframe(df, "Hostile missing frame")

    def test_format_target_requirement_label_exhaustive(self):
        """Test _format_target_requirement_label across hostile patterns."""
        vectors = [
            # (target_id, target_name, default_label, expected_substring, forbidden_pattern)
            ("apc.dm.115.chemistry.calculus_1", "微積分(一)", "目標要求", "微積分(一)"),
            ("apc.dm.115.physics.compulsory.mechanics", "", "專業必修", "物化系（物理組）必修"),
            ("uuid:550e8400-e29b-41d4-a716-446655440000", "雙主修專題", "目標要求", "雙主修專題"),
            ("uuid:550e8400-e29b-41d4-a716-446655440000", "", "目標要求", "目標要求"),
            ("custom:113:physics", "自訂物理", "專業選修", "自訂物理"),
            ("custom:113:physics", "", "專業選修", "專業選修"),
            ("target:115:apc:chemistry:compulsory:chem_lab_1", "普通化學實驗(一)", "目標要求", "普通化學實驗(一)"),
            ("REQUIREMENT_DEFICIT:123", "", "目標要求", "尚缺學分"),
            ("REQUIREMENT_COVERAGE_UNKNOWN:113:earth", "", "目標要求", "目標要求"),
            ("dept.deep.nested.code.v9", "", "目標要求", "目標要求"),
            ("", "", "目標要求", "目標要求"),
            (None, None, "自訂目標", "自訂目標"),
        ]

        for target_id, target_name, default_label, expected_sub, *rest in vectors:
            result = _format_target_requirement_label(target_id, target_name, default_label=default_label)
            self.assertIn(expected_sub, result, f"Failed for target_id='{target_id}', target_name='{target_name}'")
            match = FORBIDDEN_PATTERN.search(result)
            self.assertIsNone(match, f"Forbidden token '{match.group(0) if match else ''}' in '{result}'")

    def test_course_label_exhaustive(self):
        """_course_label handles canonical, legacy, None, and empty dictionaries."""
        # Canonical COURSE_FIELD_ALLOWLIST keys
        c1 = {"course_name": "微積分(一)", "credits": 3.0, "earned_credits": 3.0, "academic_term": "113-1"}
        self.assertEqual(_course_label(c1), "微積分(一)｜113-1｜3 學分｜已得 3 學分")

        # Legacy keys
        c2 = {"name": "普通化學", "total_credit": 3.0, "completed_credit": 3.0, "term": "113-2"}
        self.assertEqual(_course_label(c2), "普通化學｜113-2｜3 學分｜已得 3 學分")

        # Empty and None
        self.assertEqual(_course_label({}), "未命名課程｜0 學分｜已得 0 學分")
        self.assertEqual(_course_label(None), "未命名課程｜0 學分｜已得 0 學分")


class TestAdversarialSidebarCurriculumLabel(unittest.TestCase):
    """Hostile input stress tests on sidebar._curriculum_label."""

    def test_curriculum_label_fallbacks(self):
        """Ensure clean Traditional Chinese fallback is always returned."""
        test_cases = [
            # (input_val, expected_output_or_condition)
            ("uuid:550e8400-e29b-41d4-a716-446655440000", "自訂／待確認項目"),
            ("550e8400-e29b-41d4-a716-446655440000", "自訂／待確認課表"),
            ("custom:113:physics", "自訂課程項目"),
            ("custom:unmapped:token", "自訂課程項目"),
            ("113:unknown:foo", "自訂／待確認課表"),
            ("test:namespace:key", "自訂／待確認課表"),
            ("", "自訂／待確認課表"),
            ("   ", "自訂／待確認課表"),
            (None, "自訂／待確認課表"),
            ("REQUIREMENT_DEFICIT:123", "自訂／待確認課表"),
            ("APPLICATION:DOUBLE_MAJOR_NOT_APPROVED", "自訂／待確認課表"),
            ("CREDIT_CONSERVATION_FAILED", "自訂／待確認課表"),
            ("unknown_test_token_v9", "自訂／待確認課表"),
            ("個人自訂專用課表", "個人自訂專用課表"),
        ]

        for input_val, expected in test_cases:
            result = _curriculum_label(input_val)
            self.assertEqual(result, expected, f"Failed for input: '{input_val}'")
            # Verify no forbidden tokens leak
            match = FORBIDDEN_PATTERN.search(result)
            self.assertIsNone(match, f"Forbidden token in result '{result}' for input '{input_val}'")
            # Verify result is valid Traditional Chinese text (no colons or raw ASCII slugs)
            self.assertNotIn(":", result)
            self.assertNotIn("uuid", result.lower())
            self.assertNotIn("custom", result.lower())


class TestEquivalencyUILine251Verification(unittest.TestCase):
    """Verify line 251 and status warning messages in equivalency_ui.py."""

    def test_line_251_and_warning_location(self):
        """Verify content of line 251 and actual location of status warning string."""
        with open("equivalency_ui.py", encoding="utf-8") as f:
            lines = f.readlines()

        # Check line 251 (1-indexed -> line index 250)
        line_251 = lines[250].strip()
        # Line 251 is `context: Mapping[str, Any] | None = None,`
        self.assertIn("context:", line_251)
        self.assertIn("Mapping[str, Any]", line_251)

        # Check line 377: status warning message
        line_377 = lines[376].strip()
        self.assertIn("審查結果保留『待確認』。", line_377)
        self.assertNotIn("UNKNOWN", line_377)

        # Confirm full file scan has zero user-facing "UNKNOWN"
        full_content = "".join(lines)
        self.assertNotIn("審查結果保留 UNKNOWN。", full_content)


if __name__ == "__main__":
    unittest.main()
