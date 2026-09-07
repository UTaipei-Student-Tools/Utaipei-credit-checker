import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import app
import ui_components
from graduation_service import EvaluationRequest


class HtmlPerformanceBatchTests(unittest.TestCase):
    def test_custom_markup_prefers_st_html_and_rejects_scripts(self):
        calls = []
        fake_ui = SimpleNamespace(
            html=lambda value, **kwargs: calls.append(("html", value, kwargs)),
            markdown=lambda value, **kwargs: calls.append(("markdown", value, kwargs)),
        )

        ui_components.render_html("<style>.x { color: red; }</style><div>內容</div>", ui=fake_ui)

        self.assertEqual([kind for kind, _, _ in calls], ["html"])
        with self.assertRaises(ValueError):
            ui_components.render_html("<script>alert('no')</script>", ui=fake_ui)

    def test_theme_progress_header_and_landing_use_the_html_seam(self):
        calls = []
        fake_st = SimpleNamespace(
            html=lambda value, **kwargs: calls.append(("html", value, kwargs)),
            markdown=lambda value, **kwargs: calls.append(("markdown", value, kwargs)),
        )

        with patch.object(ui_components, "st", fake_st):
            ui_components.inject_theme_css()
            ui_components.draw_premium_progress("測試進度", 1, 3)
            ui_components.render_header_card("標題", "說明", landmark_id="main-content")
            ui_components.render_landing_message()

        self.assertGreaterEqual(len(calls), 4)
        self.assertTrue(all(kind == "html" for kind, _, _ in calls))
        body = "\n".join(value for _, value, _ in calls)
        self.assertIn("<style>", body)
        self.assertIn("<header", body)
        self.assertIn("<section", body)

    def test_analysis_marker_uses_the_html_seam(self):
        calls = []
        fake_st = SimpleNamespace(
            session_state={"_analysis_exported": False},
            html=lambda value, **kwargs: calls.append(("html", value, kwargs)),
            markdown=lambda value, **kwargs: calls.append(("markdown", value, kwargs)),
        )

        with patch.object(app, "st", fake_st):
            app._render_analysis_state_marker(active=True)

        self.assertEqual([kind for kind, _, _ in calls], ["html"])
        self.assertIn("utaipei-analysis-state", calls[0][1])

    def test_main_does_not_evaluate_without_a_transcript_source(self):
        fake_st = SimpleNamespace(
            session_state={},
            html=lambda *args, **kwargs: None,
            markdown=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
        )
        sidebar_state = {"has_transcript": False}
        with patch.object(app, "st", fake_st), patch.object(app, "setup_page"), patch.object(
            app, "render_header_card"
        ), patch.object(app, "render_setup_panel", return_value=sidebar_state), patch.object(
            app, "collapse_sidebar_if_needed"
        ), patch.object(app, "evaluate") as evaluate:
            app.main()

        evaluate.assert_not_called()

    def test_identical_request_reuses_one_snapshot_and_changed_request_replaces_it(self):
        request = EvaluationRequest(admission_cohort="114", primary_curriculum_id="primary:114:cs")
        replacement = replace(request, admission_cohort="115")
        snapshots = [SimpleNamespace(snapshot_id="snapshot:one"), SimpleNamespace(snapshot_id="snapshot:two")]
        fake_st = SimpleNamespace(session_state={})
        with patch.object(app, "st", fake_st), patch.object(app, "evaluate", side_effect=snapshots) as evaluate:
            first = app._evaluate_cached_snapshot(request)
            second = app._evaluate_cached_snapshot(request)
            third = app._evaluate_cached_snapshot(replacement)

        self.assertIs(first, second)
        self.assertIs(third, snapshots[1])
        self.assertEqual(evaluate.call_count, 2)
        self.assertIs(fake_st.session_state["_decision_snapshot_cache_value"], third)
        self.assertEqual(fake_st.session_state["_snapshot_artifact_cache"]["snapshot_id"], "snapshot:two")
        self.assertNotIn("password", repr(fake_st.session_state))
        self.assertNotIn("pdf", repr(fake_st.session_state).lower())

    def test_snapshot_outputs_render_once_and_build_exports_only_after_explicit_action(self):
        snapshot = SimpleNamespace(snapshot_id="snapshot:one")
        seen = []
        rendered = []
        fake_st = SimpleNamespace(
            session_state={"_analysis_exported": False, "_exports_ready": False},
            button=lambda *args, **kwargs: False,
            download_button=lambda *args, **kwargs: False,
            html=lambda value, **kwargs: rendered.append(value),
            caption=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
        )

        def renderer(value):
            seen.append(("render", value))
            return '<main id="snapshot">snapshot</main>'

        def builder(kind):
            def build(value):
                seen.append((kind, value))
                return kind.encode()

            return build

        with patch.object(app, "st", fake_st), patch.object(
            app,
            "_load_presentation_api",
            return_value=(renderer, builder("pdf"), builder("csv"), builder("audit")),
        ):
            app._render_snapshot_outputs(snapshot)
            self.assertEqual([kind for kind, _ in seen], ["render"])
            fake_st.session_state["_exports_ready"] = True
            app._render_snapshot_outputs(snapshot)
            app._render_snapshot_outputs(snapshot)

        self.assertEqual([kind for kind, _ in seen], ["render", "pdf", "csv", "audit"])
        self.assertTrue(all(value is snapshot for _, value in seen))
        self.assertEqual(len(rendered), 3)


if __name__ == "__main__":
    unittest.main()
