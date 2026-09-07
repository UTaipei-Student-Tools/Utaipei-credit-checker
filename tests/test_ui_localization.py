"""Unit tests for UI localization and zero-machine-leak guarantees in equivalency_ui and sidebar."""

from __future__ import annotations

import re
import unittest

from equivalency_ui import (
    _build_candidate_frame,
    _build_decision_frame,
    _build_missing_frame,
    _course_label,
    _format_target_requirement_label,
)
from sidebar import _curriculum_label

FORBIDDEN_UI_PATTERNS = [
    re.compile(r"\battempt:[a-zA-Z0-9_:-]+"),
    re.compile(r"\buuid:[a-zA-Z0-9_-]+"),
    re.compile(r"\bcustom:[a-zA-Z0-9_:-]+"),
    re.compile(r"\btarget:\d+:[a-zA-Z0-9_.:-]+"),
    re.compile(r"\bapc\.dm\.[a-zA-Z0-9_.-]+"),
    re.compile(r"\bREQUIREMENT_[A-Z0-9_:-]+"),
    re.compile(r"\bAPPLICATION:[A-Z0-9_:-]+"),
    re.compile(r"\bSEARCH_[A-Z0-9_:-]+"),
    re.compile(r"[0-9a-f]{32,64}"),  # Raw MD5 / SHA-256 hashes
]


class TestCourseLabel(unittest.TestCase):
    """Test _course_label under canonical, legacy, and extreme course dictionary inputs."""

    def test_canonical_course_confirmation_keys(self):
        """Canonical COURSE_FIELD_ALLOWLIST keys must not collapse into '未命名｜0 學分｜已得 0 學分'."""
        course = {
            "course_name": "微積分(一)",
            "credits": 3.0,
            "earned_credits": 3.0,
            "academic_term": "113-1",
        }
        label = _course_label(course)
        self.assertIn("微積分(一)", label)
        self.assertIn("113-1", label)
        self.assertIn("3 學分", label)
        self.assertIn("已得 3 學分", label)
        self.assertNotIn("未命名", label)
        self.assertNotIn("0 學分｜已得 0 學分", label)

    def test_legacy_keys_compatibility(self):
        """Legacy keys (name, completed_credit, total_credit) remain supported."""
        course = {
            "name": "普通物理學(一)",
            "total_credit": 3.0,
            "completed_credit": 3.0,
            "term": "112-2",
        }
        label = _course_label(course)
        self.assertIn("普通物理學(一)", label)
        self.assertIn("112-2", label)
        self.assertIn("3 學分", label)
        self.assertIn("已得 3 學分", label)

    def test_raw_name_and_in_progress_course(self):
        """Course with raw_name and zero earned credits renders cleanly."""
        course = {
            "raw_name": "高等化學實驗",
            "credits": 2.0,
            "earned_credits": 0.0,
            "academic_term": "113-2",
        }
        label = _course_label(course)
        self.assertIn("高等化學實驗", label)
        self.assertIn("2 學分", label)
        self.assertIn("已得 0 學分", label)

    def test_empty_and_none_input(self):
        """Empty dictionary or None input fails gracefully with Chinese default."""
        self.assertEqual(_course_label({}), "未命名課程｜0 學分｜已得 0 學分")
        self.assertEqual(_course_label(None), "未命名課程｜0 學分｜已得 0 學分")


class TestEquivalencyUITables(unittest.TestCase):
    """Test candidate, decision, and missing DataFrames for zero debug token leaks."""

    def test_candidate_frame_zero_leak(self):
        """Candidate table must replace attempt hashes and target machine codes with clean text."""
        raw_attempt_hash = "attempt:v2:46b3f9180708f51a1362e6d9d16b1e6057bc6719ab1f6fce7c99277d3f11d13f"
        candidates = [
            {
                "source_attempt_id": raw_attempt_hash,
                "source_course_name": "微積分(I)",
                "target_requirement_id": "apc.dm.115.chemistry.calculus_1",
                "target_requirement_name": "微積分(一)",
                "state": "proposed",
                "reason": "來源序號明確，但外部／跨系認定仍需核准證據。",
            }
        ]
        df = _build_candidate_frame(candidates)
        df_content = df.to_string()

        # Must NOT contain raw attempt ID or hash
        self.assertNotIn("attempt:", df_content)
        self.assertNotIn("46b3f9180708f51a", df_content)
        # Must NOT contain dotted target code
        self.assertNotIn("apc.dm", df_content)
        # Must contain clean human-readable representation
        self.assertIn("第 1 門修課", df_content)
        self.assertIn("微積分(I)", df_content)
        self.assertIn("微積分(一)", df_content)
        self.assertIn("候選／建議", df_content)

        # Scanner check
        for pattern in FORBIDDEN_UI_PATTERNS:
            self.assertIsNone(pattern.search(df_content), f"Leak detected: {pattern.pattern}")

    def test_decision_frame_zero_leak(self):
        """Decision table must replace attempt hashes and target citations with clean text."""
        raw_attempt_hash = "attempt:v2:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        decisions = [
            {
                "source_attempt_id": raw_attempt_hash,
                "source_course_name": "普通物理學含實驗(一)",
                "target_requirement_id": "target:115:apc:chemistry:compulsory:chem_lab_1",
                "target_requirement_name": "普通化學實驗(一)",
                "state": "approved",
                "authority": "理學院教務分處",
                "evidence_reference": "手冊第 45 頁規定",
                "approved_credits": 1.0,
            }
        ]
        df = _build_decision_frame(decisions)
        df_content = df.to_string()

        # Must NOT contain raw attempt ID or target code
        self.assertNotIn("attempt:", df_content)
        self.assertNotIn("abcdef012345", df_content)
        self.assertNotIn("target:115:apc", df_content)
        # Must contain clean human-readable representation
        self.assertIn("第 1 門修課", df_content)
        self.assertIn("普通物理學含實驗(一)", df_content)
        self.assertIn("普通化學實驗(一)", df_content)
        self.assertIn("已核准（需證據）", df_content)
        self.assertIn("理學院教務分處", df_content)

        # Scanner check
        for pattern in FORBIDDEN_UI_PATTERNS:
            self.assertIsNone(pattern.search(df_content), f"Leak detected: {pattern.pattern}")

    def test_missing_frame_zero_leak(self):
        """Missing table must format machine IDs cleanly without raw token leaks."""
        missing_rows = [
            {
                "target_requirement_id": "apc.dm.115.chemistry.calculus_1",
                "name": "微積分(一)",
                "category": "專業必修",
                "credit": 3.0,
            },
            {
                "target_requirement_id": "uuid:550e8400-e29b-41d4-a716-446655440000",
                "target_requirement_name": "高等選修學門",
                "category": "專業選修",
                "credit": 2.0,
            },
        ]
        df = _build_missing_frame(missing_rows)
        df_content = df.to_string()

        self.assertNotIn("apc.dm", df_content)
        self.assertNotIn("uuid:", df_content)
        self.assertNotIn("550e8400", df_content)
        self.assertIn("微積分(一)", df_content)
        self.assertIn("高等選修學門", df_content)

        # Scanner check
        for pattern in FORBIDDEN_UI_PATTERNS:
            self.assertIsNone(pattern.search(df_content), f"Leak detected: {pattern.pattern}")

    def test_format_target_requirement_label_fallbacks(self):
        """Verify _format_target_requirement_label handles diverse inputs cleanly."""
        # Dotted apc.dm code
        dotted = _format_target_requirement_label("apc.dm.115.chemistry.calculus_1", "微積分(一)")
        self.assertNotIn("apc.dm", dotted)
        self.assertIn("微積分(一)", dotted)

        # UUID string
        uuid_str = _format_target_requirement_label("uuid:12345-abcde", "雙主修專題")
        self.assertNotIn("uuid:", uuid_str)
        self.assertIn("雙主修專題", uuid_str)

        # Empty target with UUID
        uuid_empty = _format_target_requirement_label("uuid:12345-abcde", "")
        self.assertEqual(uuid_empty, "目標要求")

        # Citation code
        citation = _format_target_requirement_label("target:115:apc:chemistry:compulsory:chem_lab_1", "化學實驗(一)")
        self.assertNotIn("target:115", citation)
        self.assertIn("化學實驗(一)", citation)

    def test_unlocalized_status_string_removed(self):
        """Verify '審查結果保留 UNKNOWN。' has been replaced by '審查結果保留『待確認』。'."""
        with open("equivalency_ui.py", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("審查結果保留 UNKNOWN。", content)
        self.assertIn("審查結果保留『待確認』。", content)


class TestCurriculumLabel(unittest.TestCase):
    """Test sidebar _curriculum_label fallback hardening under normal and extreme inputs."""

    def test_registered_primary_curriculum(self):
        """Registered primary curriculum returns standard formatted label."""
        label = _curriculum_label("primary:113:earth:earth_environment")
        self.assertIn("113", label)
        self.assertIn("地生", label)
        self.assertIn("地球環境", label)
        self.assertNotIn("primary:", label)

    def test_registered_double_major_target(self):
        """Registered double major target returns formatted label with target marker."""
        label = _curriculum_label("target:double_major:115:apc:chemistry")
        self.assertIn("115", label)
        self.assertIn("雙主修目標", label)
        self.assertIn("物化", label)
        self.assertIn("化學組", label)
        self.assertNotIn("target:double_major:", label)

    def test_handbook_citation(self):
        """Valid handbook citation translates to clean Chinese citation."""
        label = _curriculum_label("handbook:113:earth:p.45")
        self.assertIn("113 學年度", label)
        self.assertIn("地生系學生手冊", label)
        self.assertNotIn("handbook:", label)
        self.assertNotIn(":", label)

    def test_raw_uuid_fallback(self):
        """Raw UUID input must NOT leak to UI and must return '自訂／待確認課表'."""
        uuid_input = "uuid:550e8400-e29b-41d4-a716-446655440000"
        label = _curriculum_label(uuid_input)
        self.assertEqual(label, "自訂／待確認課表")
        self.assertNotIn("uuid:", label)
        self.assertNotIn("550e8400", label)

    def test_custom_scheme_fallback(self):
        """Custom colon scheme must return '自訂／待確認課表'."""
        custom_input = "custom:113:physics"
        label = _curriculum_label(custom_input)
        self.assertEqual(label, "自訂／待確認課表")
        self.assertNotIn("custom:", label)

    def test_unmapped_track_key_fallback(self):
        """Unmapped colon key must return '自訂／待確認課表'."""
        unmapped_input = "113:earth:unknown_track"
        label = _curriculum_label(unmapped_input)
        self.assertEqual(label, "自訂／待確認課表")
        self.assertNotIn(":", label)

    def test_debug_token_fallback(self):
        """Internal debug blocker tokens return '自訂／待確認課表'."""
        self.assertEqual(_curriculum_label("REQUIREMENT_DEFICIT:123"), "自訂／待確認課表")
        self.assertEqual(_curriculum_label("APPLICATION:DOUBLE_MAJOR_NOT_APPROVED"), "自訂／待確認課表")

    def test_empty_and_arbitrary_string_fallback(self):
        """Empty, None, or unmapped arbitrary ASCII identifiers return '自訂／待確認課表'."""
        self.assertEqual(_curriculum_label(None), "自訂／待確認課表")
        self.assertEqual(_curriculum_label(""), "自訂／待確認課表")
        self.assertEqual(_curriculum_label("unknown_test_token_v9"), "自訂／待確認課表")

    def test_clean_chinese_custom_label_preserved(self):
        """Clean Traditional Chinese input string is safely preserved."""
        self.assertEqual(_curriculum_label("個人自訂專用課表"), "個人自訂專用課表")


if __name__ == "__main__":
    unittest.main()
