import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from graduation_service import EvaluationRequest
from input_confirmation import (
    ConfirmationState,
    CourseConfirmation,
    InputDiagnostic,
    NormalizedCourseRow,
    confirm_confirmation,
    mask_person_name,
    mask_student_id,
)

ROOT = Path(__file__).resolve().parents[1]


class AppSnapshotIntegrationTests(unittest.TestCase):
    def test_app_does_not_render_a_duplicate_official_decision_section(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("_render_official_decisions", source)
        self.assertNotIn("官方判定（來自同一份分析快照）", source)

    def test_app_source_has_one_service_evaluate_call_and_no_legacy_evaluator_path(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        evaluate_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "evaluate"
        ]
        self.assertEqual(len(evaluate_calls), 1)
        for forbidden in ("credit_engine", "evaluate_graduation", "render_report", "equivalency_ui"):
            self.assertNotIn(forbidden, source)

    def test_renderer_and_all_exports_receive_identical_snapshot_object(self):
        snapshot = object()
        seen = []
        rendered = []

        def renderer(value):
            seen.append(("render", value))
            return "<section data-snapshot-report='true'>report</section>"

        def pdf(value):
            seen.append(("pdf", value))
            return b"pdf"

        def csv(value):
            seen.append(("csv", value))
            return "csv"

        def audit(value):
            seen.append(("audit", value))
            return "audit"

        fake_st = SimpleNamespace(
            session_state={"_analysis_exported": False, "_exports_ready": True},
            button=lambda *args, **kwargs: False,
            download_button=lambda *args, **kwargs: False,
            html=lambda *args, **kwargs: rendered.append((args, kwargs)),
            caption=lambda *args, **kwargs: None,
        )
        with patch.object(app, "st", fake_st), patch.object(
            app, "_load_presentation_api", return_value=(renderer, pdf, csv, audit)
        ):
            fake_st.session_state["_snapshot_artifact_cache"] = {
                "snapshot_id": f"object:{id(snapshot)}",
                "rendered_html": None,
                "exports": {},
            }
            app._render_snapshot_outputs(snapshot)

        self.assertEqual([kind for kind, _ in seen], ["render", "pdf", "csv", "audit"])
        self.assertTrue(all(value is snapshot for _, value in seen))
        self.assertIn(
            ("<section data-snapshot-report='true'>report</section>",),
            [args for args, _ in rendered],
        )
        self.assertTrue(all("unsafe_allow_html" not in kwargs for _, kwargs in rendered))

    def test_analysis_marker_is_emitted_after_output_buttons_and_reflects_export_click(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertLess(source.index("_render_snapshot_outputs(snapshot)"), source.rindex("_render_analysis_state_marker(active="))

        rendered = []
        snapshot = object()
        fake_st = SimpleNamespace(
            session_state={"_analysis_exported": False, "_exports_ready": True},
            button=lambda *args, **kwargs: False,
            download_button=lambda *args, **kwargs: True,
            html=lambda *args, **kwargs: rendered.append((args, kwargs)),
            markdown=lambda *args, **kwargs: rendered.append((args, kwargs)),
            caption=lambda *args, **kwargs: None,
        )
        fake_st.session_state["_snapshot_artifact_cache"] = {
            "snapshot_id": f"object:{id(snapshot)}",
            "rendered_html": None,
            "exports": {},
        }
        with patch.object(app, "st", fake_st), patch.object(
            app,
            "_load_presentation_api",
            return_value=(
                lambda _snapshot: "<main>snapshot</main>",
                lambda _snapshot: b"pdf",
                lambda _snapshot: b"csv",
                lambda _snapshot: b"audit",
            ),
        ):
            app._render_snapshot_outputs(snapshot)
            app._render_analysis_state_marker(active=True)

        markers = [
            args[0]
            for args, _ in rendered
            if args and "id='utaipei-analysis-state'" in str(args[0])
        ]
        self.assertEqual(len(markers), 1)
        self.assertIn("data-analysis-active='true'", markers[0])
        self.assertIn("data-exported='true'", markers[0])

    def test_one_failed_export_does_not_remove_the_snapshot_screen_or_other_exports(self):
        snapshot = object()
        rendered = []
        errors = []
        downloaded = []
        fake_st = SimpleNamespace(
            session_state={"_analysis_exported": False, "_exports_ready": True},
            button=lambda *args, **kwargs: False,
            download_button=lambda label, **kwargs: downloaded.append((label, kwargs["data"])) or False,
            html=lambda *args, **kwargs: rendered.append((args, kwargs)),
            caption=lambda *args, **kwargs: None,
            error=lambda message: errors.append(message),
        )
        fake_st.session_state["_snapshot_artifact_cache"] = {
            "snapshot_id": f"object:{id(snapshot)}",
            "rendered_html": None,
            "exports": {},
        }

        def broken_pdf(_snapshot):
            raise ValueError("PRIVATE-DETAIL-MUST-NOT-LEAK")

        with patch.object(app, "st", fake_st), patch.object(
            app,
            "_load_presentation_api",
            return_value=(
                lambda _snapshot: "<main class='snapshot-report'>snapshot</main>",
                broken_pdf,
                lambda _snapshot: b"csv",
                lambda _snapshot: b"audit",
            ),
        ):
            app._render_snapshot_outputs(snapshot)

        self.assertTrue(any("snapshot-report" in args[0] for args, _ in rendered))
        self.assertEqual([label for label, _ in downloaded], ["下載課程配置 CSV", "下載規則與判定摘要"])
        self.assertTrue(any("PDF" in message for message in errors))
        self.assertNotIn("PRIVATE-DETAIL-MUST-NOT-LEAK", " ".join(errors))

    def test_request_builder_keeps_target_candidate_and_self_reports_separate(self):
        confirmation = SimpleNamespace(
            rows=(),
            fingerprint="fingerprint",
            state=SimpleNamespace(value="PARSED"),
            confirmed_fingerprint=None,
        )
        request = app._build_evaluation_request(
            {
                "admission_cohort": "114",
                "primary_curriculum_id": "primary:114:cs",
                "program_type": "雙主修",
                "target_curriculum_id": "target:115:cs",
                "target_program": "資科",
                "target_track": None,
                "application_year": "115",
                "application_semester": "1",
                "application_status": "已核准",
                "school_approval_status": "自述已核准",
            },
            confirmation,
        )
        self.assertIsInstance(request, EvaluationRequest)
        self.assertEqual(request.target_curriculum_id, "target:115:cs")
        self.assertEqual(request.application_year, "115")
        self.assertEqual(request.application_semester, "1")
        self.assertEqual(request.application_status, "已核准")
        self.assertEqual(request.school_approval_status, "自述已核准")
        self.assertFalse(request.transcript_confirmed)
        self.assertFalse(hasattr(request, "student_id"))
        self.assertNotIn("password", request.as_dict())

    def test_masked_identifiers_are_safe_for_default_display(self):
        self.assertEqual(mask_student_id("A12345678"), "A1••••78")
        self.assertEqual(mask_person_name("王小明"), "王＊＊")
        self.assertNotEqual(mask_student_id("A12345678"), "A12345678")

    def test_safe_error_does_not_echo_exception_text(self):
        error = app._safe_error_message(ValueError("PASSWORD-OR-STUDENT-ID"))
        self.assertNotIn("PASSWORD-OR-STUDENT-ID", error)
        self.assertIn("輸入資料格式不正確", error)

    def test_parser_reconciliation_diagnostics_show_both_totals_in_safe_chinese(self):
        messages = app._parser_diagnostic_messages(
            {
                "complete": False,
                "total_reconciled": False,
                "reconciliation": {
                    "status": "mismatch",
                    "attempted": {"parsed": 10, "reported": 12, "difference": -2, "reconciled": False},
                    "earned": {"parsed": 8, "reported": 9, "difference": -1, "reconciled": False},
                },
                "fatal_warnings": [
                    "修習學分核對過少：解析出的已結束修習學分 10，成績單全歷年修習總額 12，差 2。",
                    "PRIVATE-DETAIL-MUST-NOT-LEAK",
                ],
            }
        )

        joined = " ".join(messages)
        self.assertIn("修習學分核對結果：課程列合計 10 學分，成績單標示 12 學分，相差 2 學分", joined)
        self.assertIn("實得學分核對結果：課程列合計 8 學分，成績單標示 9 學分，相差 1 學分", joined)
        self.assertIn("修習學分核對過少", joined)
        self.assertNotIn("PRIVATE-DETAIL-MUST-NOT-LEAK", joined)
        self.assertNotIn("UNKNOWN", joined)

    def test_parser_missing_metadata_explains_scoped_effect(self):
        messages = app._parser_diagnostic_messages(
            {
                "course_code_missing": 55,
                "offering_department_missing": 55,
            }
        )

        joined = " ".join(messages)
        self.assertIn("未提供課號", joined)
        self.assertIn("未提供開課系所", joined)
        self.assertIn("已能依課程名稱與學分核對的課程可照常處理", joined)
        self.assertIn("跨系同名或需要系所條件的規則才需人工確認", joined)
        self.assertNotIn("請補齊課號", joined)

    def test_editor_hides_opaque_attempt_group_but_keeps_column_mapping(self):
        config = app._confirmation_column_config()
        self.assertIn("attempt_group", config)
        self.assertIsNone(config["attempt_group"])

    def test_parser_fatal_confirmation_rows_cannot_be_confirmed_from_ui(self):
        class _Expander:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        button_calls = []
        row = NormalizedCourseRow(
            course_code="AG102",
            course_name="普通課程",
            credits=2.0,
            earned_credits=2.0,
            status="COMPLETED",
            term="114-1",
        )
        confirmation = CourseConfirmation(
            rows=(row,),
            fingerprint="fingerprint",
            state=ConfirmationState.UNCONFIRMED,
            diagnostics=(InputDiagnostic(code="PARSER_INCOMPLETE", message="成績資料尚未完整。"),),
        )
        fake_st = SimpleNamespace(
            session_state={"_student_display": {"name": "＊＊", "student_id": "••••"}},
            caption=lambda *_args, **_kwargs: None,
            warning=lambda *_args, **_kwargs: None,
            success=lambda *_args, **_kwargs: None,
            info=lambda *_args, **_kwargs: None,
            expander=lambda *_args, **_kwargs: _Expander(),
            data_editor=lambda rows, **_kwargs: rows,
            button=lambda label, **kwargs: button_calls.append((label, kwargs)) or False,
        )

        with patch.object(app, "st", fake_st):
            app._render_confirmation_editor(confirmation)

        self.assertEqual(len(button_calls), 1)
        self.assertEqual(button_calls[0][0], "確認目前成績列")
        self.assertTrue(button_calls[0][1]["disabled"])

    def test_parser_confirmation_cache_is_scoped_to_selected_admission_cohort(self):
        row = NormalizedCourseRow(
            course_code="AG102",
            course_name="普通課程",
            credits=2.0,
            earned_credits=2.0,
            status="COMPLETED",
            term="114-1",
        )
        parsed = CourseConfirmation(
            rows=(row,),
            fingerprint="fingerprint",
            state=ConfirmationState.PARSED,
        )
        fake_st = SimpleNamespace(
            session_state={"transcript_pdf_bytes": b"synthetic transcript"},
            warning=lambda *_args, **_kwargs: None,
            checkbox=lambda *_args, **_kwargs: False,
        )
        parser_result = (
            {"name": "王小明", "student_id": "A12345678", "parse_diagnostics": {"detected_admission_cohort": "114"}},
            (),
        )
        with patch.object(app, "st", fake_st), patch.object(
            app, "parse_transcript_pdf", return_value=parser_result
        ) as parse_pdf, patch.object(
            app, "adapt_legacy_result", return_value=SimpleNamespace(confirmation=parsed, diagnostics=())
        ):
            first = app._parser_confirmation({"admission_cohort": "114", "source_label": "synthetic"})
            fake_st.session_state["_parsed_confirmation"] = confirm_confirmation(first, first.fingerprint)

            mismatched = app._parser_confirmation({"admission_cohort": "115", "source_label": "synthetic"})
            returned_to_original = app._parser_confirmation(
                {"admission_cohort": "114", "source_label": "synthetic"}
            )

        self.assertEqual(parse_pdf.call_count, 3)
        self.assertEqual(mismatched.state, ConfirmationState.UNCONFIRMED)
        self.assertTrue(any(item.code == "COHORT_MISMATCH" for item in mismatched.diagnostics))
        self.assertEqual(returned_to_original.state, ConfirmationState.PARSED)

    def test_old_cohort_mismatch_acknowledgement_cannot_confirm_a_new_context(self):
        row = NormalizedCourseRow(
            course_code="AG102",
            course_name="普通課程",
            credits=2.0,
            earned_credits=2.0,
            status="COMPLETED",
            term="114-1",
        )
        parsed = CourseConfirmation(
            rows=(row,),
            fingerprint="fingerprint",
            state=ConfirmationState.PARSED,
        )
        checkbox_keys = []

        def checkbox(_label, *, value=False, key=None):
            checkbox_keys.append(key)
            return fake_st.session_state.get(key, value)

        fake_st = SimpleNamespace(
            session_state={
                "transcript_pdf_bytes": b"synthetic transcript",
                # Simulate the old fixed-key widget retaining a prior answer.
                "cohort_mismatch_confirmation": True,
            },
            warning=lambda *_args, **_kwargs: None,
            checkbox=checkbox,
        )
        parser_result = (
            {"name": "王小明", "student_id": "A12345678", "parse_diagnostics": {"detected_admission_cohort": "114"}},
            (),
        )
        with patch.object(app, "st", fake_st), patch.object(
            app, "parse_transcript_pdf", return_value=parser_result
        ), patch.object(
            app, "adapt_legacy_result", return_value=SimpleNamespace(confirmation=parsed, diagnostics=())
        ):
            app._parser_confirmation({"admission_cohort": "114", "source_label": "synthetic"})
            mismatched = app._parser_confirmation(
                {"admission_cohort": "115", "source_label": "synthetic", "cohort_mismatch_confirmed": False}
            )

        self.assertEqual(len(checkbox_keys), 1)
        self.assertNotEqual(checkbox_keys[0], "cohort_mismatch_confirmation")
        self.assertTrue(any(item.code == "COHORT_MISMATCH" for item in mismatched.diagnostics))
        self.assertEqual(mismatched.state, ConfirmationState.UNCONFIRMED)


if __name__ == "__main__":
    unittest.main()
