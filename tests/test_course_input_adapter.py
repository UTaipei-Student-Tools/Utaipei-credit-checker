import unittest

from course_input_adapter import (
    adapt_legacy_result,
    adapt_legacy_rows,
    expand_legacy_course_rows,
    parser_rows_to_confirmation,
)
from input_confirmation import (
    COURSE_FIELD_ALLOWLIST,
    ConfirmationState,
    confirm_confirmation,
    edit_confirmation,
    release_formal_attempts,
)


class CourseInputAdapterTests(unittest.TestCase):
    def test_two_semester_parser_row_becomes_two_auditable_attempts(self):
        source = {
            "course_code": "MATH101",
            "name": "微積分",
            "type": "必",
            "academic_year": "114",
            "sem1_credit": "3",
            "sem1_score": "80",
            "sem2_credit": "3",
            "sem2_score": "P",
            "offering_department": "數學系",
        }

        rows = expand_legacy_course_rows([source])

        self.assertEqual([row["term"] for row in rows], ["114-1", "114-2"])
        self.assertEqual([row["credits"] for row in rows], [3.0, 3.0])
        self.assertEqual([row["earned_credits"] for row in rows], [3.0, 3.0])
        self.assertEqual({"course_code", "course_name"}.issubset(rows[0]), True)
        self.assertTrue(all(set(row) <= COURSE_FIELD_ALLOWLIST for row in rows))
        self.assertEqual(rows[0]["attempt_group"], rows[1]["attempt_group"])

    def test_status_mapping_is_fail_closed_and_does_not_mint_waiver_or_transfer_credit(self):
        rows = expand_legacy_course_rows(
            [
                {"name": "及格", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "P"},
                {"name": "未修", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "未"},
                {"name": "不及格", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "F"},
                {"name": "停修", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "W"},
                {"name": "免修", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "免"},
                {"name": "抵免無實得", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "抵"},
                {"name": "抵免有實得", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "抵", "earned_credits": "2"},
                {"name": "未知", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "???"},
            ]
        )
        by_name = {row["course_name"]: row for row in rows}

        self.assertEqual(by_name["及格"]["status"], "COMPLETED")
        self.assertEqual(by_name["及格"]["earned_credits"], 2.0)
        self.assertEqual(by_name["未修"]["status"], "IN_PROGRESS")
        self.assertEqual(by_name["未修"]["earned_credits"], 0.0)
        self.assertEqual(by_name["不及格"]["status"], "FAILED")
        self.assertEqual(by_name["停修"]["status"], "WITHDRAWN")
        self.assertEqual(by_name["免修"]["status"], "WAIVED")
        self.assertEqual(by_name["免修"]["earned_credits"], 0.0)
        self.assertEqual(by_name["抵免無實得"]["status"], "TRANSFERRED")
        self.assertEqual(by_name["抵免無實得"]["earned_credits"], 0.0)
        self.assertEqual(by_name["抵免有實得"]["status"], "TRANSFERRED")
        self.assertEqual(by_name["抵免有實得"]["earned_credits"], 2.0)
        self.assertEqual(by_name["未知"]["status"], "UNKNOWN")

        confirmation = parser_rows_to_confirmation(
            [{"name": "抵免無實得", "academic_year": "114", "semester": "1", "total_credit": "2", "score": "抵"}]
        )
        self.assertEqual(confirmation.state, ConfirmationState.UNCONFIRMED)
        self.assertTrue(any(item.code == "TRANSFER_EARNED_CREDIT_UNVERIFIED" for item in confirmation.diagnostics))

    def test_no_term_or_credit_is_fabricated_and_unknown_score_is_diagnostic(self):
        rows = expand_legacy_course_rows([{"name": "缺資料", "score": "80"}])
        self.assertEqual(rows, ())
        result = adapt_legacy_rows([{"name": "缺資料", "score": "80"}])
        self.assertFalse(result.valid)
        self.assertTrue(result.diagnostics)

    def test_attempt_group_keeps_lecture_and_lab_separate(self):
        rows = expand_legacy_course_rows(
            [
                {"course_code": "BIO1", "name": "普通生物學", "type": "必", "academic_year": "114", "semester": "1", "total_credit": 3, "score": "80"},
                {"course_code": "BIO1", "name": "普通生物學實驗", "type": "實驗", "academic_year": "114", "semester": "1", "total_credit": 1, "score": "80"},
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["attempt_group"], rows[1]["attempt_group"])

    def test_curriculum_categories_do_not_split_repeat_group_but_explicit_components_do(self):
        category_rows = expand_legacy_course_rows(
            [
                {"course_code": "BIO1", "name": "普通生物學", "type": "系必修", "academic_year": "114", "semester": "1", "total_credit": 3, "score": "80"},
                {"course_code": "BIO1", "name": "普通生物學", "type": "系選修", "academic_year": "114", "semester": "2", "total_credit": 3, "score": "85"},
            ]
        )
        self.assertEqual(category_rows[0]["course_type"], "系必修")
        self.assertEqual(category_rows[1]["course_type"], "系選修")
        self.assertEqual(category_rows[0]["attempt_group"], category_rows[1]["attempt_group"])

        component_rows = expand_legacy_course_rows(
            [
                {"course_code": "BIO1", "name": "普通生物學", "component_type": "lecture", "type": "系必修", "academic_year": "114", "semester": "1", "total_credit": 3, "score": "80"},
                {"course_code": "BIO1", "name": "普通生物學", "component_type": "lab", "type": "系必修", "academic_year": "114", "semester": "1", "total_credit": 1, "score": "80"},
            ]
        )
        self.assertEqual(component_rows[0]["course_type"], "lecture")
        self.assertEqual(component_rows[1]["course_type"], "lab")
        self.assertNotEqual(component_rows[0]["attempt_group"], component_rows[1]["attempt_group"])

    def test_unrecognized_component_words_do_not_create_component_repeat_groups(self):
        rows = expand_legacy_course_rows(
            [
                {"course_code": "BIO1", "name": "普通生物學", "type": "collaboration", "academic_year": "114", "semester": "1", "total_credit": 3, "score": "80"},
                {"course_code": "BIO1", "name": "普通生物學", "type": "syllabus", "academic_year": "114", "semester": "2", "total_credit": 3, "score": "85"},
                {"course_code": "BIO1", "name": "普通生物學", "type": "required_course", "academic_year": "115", "semester": "1", "total_credit": 3, "score": "90"},
            ]
        )

        self.assertEqual([row["attempt_group"] for row in rows], ["BIO1", "BIO1", "BIO1"])

    def test_conflicting_component_fields_are_unconfirmed_and_not_silently_chosen(self):
        result = adapt_legacy_result(
            [
                {
                    "course_code": "BIO1",
                    "name": "普通生物學",
                    "component_type": "lecture",
                    "type": "lab",
                    "academic_year": "114",
                    "semester": "1",
                    "total_credit": 3,
                    "score": "80",
                }
            ]
        )

        self.assertFalse(result.valid)
        self.assertTrue(any(item.code == "CONFLICTING_COMPONENT_METADATA" for item in result.diagnostics))
        self.assertEqual(result.rows[0]["course_type"], "UNKNOWN")

    def test_unknown_explicit_component_is_unconfirmed_even_with_category_metadata(self):
        result = adapt_legacy_result(
            [
                {
                    "course_code": "BIO1",
                    "name": "普通生物學",
                    "component_type": "系必修",
                    "type": "系必修",
                    "academic_year": "114",
                    "semester": "1",
                    "total_credit": 3,
                    "score": "80",
                }
            ]
        )

        self.assertFalse(result.valid)
        self.assertTrue(any(item.code == "CONFLICTING_COMPONENT_METADATA" for item in result.diagnostics))
        self.assertEqual(result.rows[0]["course_type"], "UNKNOWN")

    def test_confirmation_starts_parsed_and_source_or_edit_invalidates_release(self):
        confirmation = parser_rows_to_confirmation(
            [{"name": "微積分", "academic_year": "114", "semester": "1", "total_credit": 3, "score": "80"}]
        )
        self.assertEqual(confirmation.state, ConfirmationState.PARSED)
        self.assertEqual(release_formal_attempts(confirmation, confirmation.fingerprint), ())

        confirmed = confirm_confirmation(confirmation, confirmation.fingerprint)
        self.assertEqual(confirmed.state, ConfirmationState.CONFIRMED)
        self.assertEqual(len(release_formal_attempts(confirmed, confirmed.fingerprint)), 1)
        edited = edit_confirmation(
            confirmed,
            expand_legacy_course_rows(
                [{"name": "微積分", "academic_year": "114", "semester": "1", "total_credit": 4, "score": "80"}]
            ),
        )
        self.assertEqual(edited.state, ConfirmationState.STALE)
        self.assertEqual(release_formal_attempts(edited, edited.fingerprint), ())

    def test_adapter_does_not_copy_forbidden_parser_values(self):
        confirmation = parser_rows_to_confirmation(
            [
                {
                    "name": "微積分",
                    "academic_year": "114",
                    "semester": "1",
                    "total_credit": 3,
                    "score": "80",
                    "student_id": "SENSITIVE-ID",
                    "password": "SENSITIVE-PASSWORD",
                    "raw_pdf": b"SENSITIVE-PDF",
                }
            ]
        )
        self.assertNotIn("SENSITIVE-ID", repr(confirmation))
        self.assertNotIn("SENSITIVE-PASSWORD", repr(confirmation))
        self.assertNotIn("SENSITIVE-PDF", repr(confirmation))


if __name__ == "__main__":
    unittest.main()
