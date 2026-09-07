import unittest
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

import app

ROOT = Path(__file__).resolve().parents[1]


def _responsive_theme_fixture():
    from ui_components import inject_theme_css

    inject_theme_css()


def _html_values(app):
    """Read st.html bodies from Streamlit's AppTest element tree."""

    return [
        child.proto.body
        for child in app.main.children.values()
        if getattr(child, "type", "") == "html"
    ]


class MobilePwaShellTests(unittest.TestCase):
    def test_mobile_shell_keeps_streamlit_as_the_single_scroll_owner(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        self.assertRegex(
            css,
            r'\[data-testid="stAppViewContainer"\]\s*\{\s*'
            r'padding: var\(--ui-safe-top\) 0 0 0 !important;',
        )
        self.assertNotIn(
            'padding: calc(.85rem + var(--ui-safe-top))',
            css,
        )
        self.assertIn('--ui-header-height: 3.75rem', css)
        mobile_rule = css.split('@media (max-width: 768px)', 1)[1].split(
            '@media (max-width: 480px)', 1
        )[0]
        self.assertIn('var(--ui-safe-top)', mobile_rule)
        self.assertNotIn('overflow-y:', mobile_rule)
        self.assertNotIn('overflow: hidden', mobile_rule)
        self.assertRegex(
            css,
            r'padding: calc\(var\(--ui-header-height\) \+ \.85rem\)\s+'
            r'max\(\.85rem, var\(--ui-safe-right\)\)\s+'
            r'max\(1\.25rem, var\(--ui-safe-bottom\)\)\s+'
            r'max\(\.85rem, var\(--ui-safe-left\)\) !important;',
        )

    def test_narrow_mobile_shell_preserves_horizontal_safe_area_insets(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        self.assertRegex(
            css,
            r'padding-inline:\s*max\(\.65rem, var\(--ui-safe-left\)\)\s+'
            r'max\(\.65rem, var\(--ui-safe-right\)\) !important;',
        )
        self.assertNotIn('padding-inline: .65rem !important;', css)

    def test_update_menu_script_is_accessible_idempotent_and_cache_busted(self):
        from ui_components import _build_update_menu_script

        script = _build_update_menu_script()
        self.assertIn("更新至最新版", script)
        self.assertIn('[data-testid="stMainMenuList"]', script)
        self.assertIn('document.createElement("a")', script)
        self.assertIn('role", "menuitem"', script)
        self.assertIn('setAttribute("target", "_self")', script)
        self.assertIn('setAttribute("href", url.toString())', script)
        self.assertIn('MutationObserver', script)
        self.assertIn('setAttribute("data-testid", ITEM_TEST_ID)', script)
        self.assertIn('_ut_update', script)
        self.assertIn('navigator.serviceWorker', script)
        self.assertIn('getRegistration', script)
        self.assertIn('.update()', script)
        self.assertIn('SKIP_WAITING', script)
        self.assertIn('CLEAR_STATIC_CACHES', script)
        self.assertIn('utaipei-graduation-static-', script)
        self.assertIn("#utaipei-analysis-state[data-analysis-active='true']", script)
        self.assertIn('confirm(', script)
        self.assertIn('caches.keys()', script)
        self.assertIn('caches.delete', script)
        self.assertNotIn('location.replace', script)
        self.assertNotIn('localStorage.clear', script)
        self.assertNotIn('sessionStorage.clear', script)
        self.assertNotIn('document.cookie', script)

        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))
        self.assertRegex(
            css,
            r'\.utaipei-update-menu-item\s*\{[^}]*touch-action:\s*manipulation;',
        )

    def test_update_menu_script_does_not_render_a_page_level_button(self):
        from ui_components import _build_update_menu_script

        script = _build_update_menu_script()
        self.assertIn('menu.insertBefore(item, insertionAnchor)', script)
        self.assertNotIn('st.button', script)
        self.assertNotIn('stButton', script)

    def test_theme_bridge_tracks_streamlit_color_scheme_without_storage_access(self):
        from ui_components import _build_update_menu_script

        script = _build_update_menu_script()
        self.assertIn('__utaipeiGraduationThemeBridge', script)
        self.assertIn('stMainMenuItem-theme-Light', script)
        self.assertIn('stMainMenuItem-theme-Dark', script)
        self.assertIn('stMainMenuItem-theme-System', script)
        self.assertIn('aria-checked', script)
        self.assertIn('preference', script)
        self.assertIn('[data-testid="stHeader"]', script)
        self.assertIn('backgroundColor', script)
        self.assertIn('transparent', script)
        self.assertIn('luminance', script)
        self.assertIn('querySelector(".stApp")', script)
        self.assertIn('getComputedStyle', script)
        self.assertIn('colorScheme', script)
        self.assertIn('getPropertyValue("color-scheme")', script)
        self.assertIn('data-utaipei-theme', script)
        self.assertIn('attributeFilter', script)
        self.assertIn('"class"', script)
        self.assertIn('"aria-checked"', script)
        self.assertIn('"background-color"', script)
        self.assertIn('"data-theme"', script)
        self.assertIn('"data-streamlit-theme"', script)
        self.assertIn('const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)"', script)
        self.assertIn('matchMedia(DARK_MEDIA_QUERY)', script)
        self.assertIn('addEventListener("change"', script)
        self.assertNotIn('localStorage', script)
        self.assertNotIn('sessionStorage', script)

    def test_theme_bridge_prioritizes_menu_header_then_app_and_media_signals(self):
        from ui_components import _build_update_menu_script

        script = _build_update_menu_script()
        menu_index = script.index('stMainMenuItem-theme-Light')
        header_index = script.index('[data-testid="stHeader"]')
        app_index = script.index('querySelector(".stApp")')
        media_index = script.index('matchMedia(DARK_MEDIA_QUERY)')
        self.assertLess(menu_index, header_index)
        self.assertLess(header_index, app_index)
        self.assertLess(app_index, media_index)
        self.assertIn('state.preference = checkedPreference', script)
        self.assertIn('checkedPreference === "system"', script)
        self.assertIn('mediaQuery.matches ? "dark" : "light"', script)
        self.assertIn('record.attributeName !== "aria-checked"', script)
        self.assertIn('state.observer = new parentWindow.MutationObserver', script)

    def test_theme_bridge_palette_is_after_os_and_legacy_theme_rules(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        media_index = css.index("@media (prefers-color-scheme: dark)")
        legacy_light_index = css.index('html[data-theme="light"]')
        bridge_light_index = css.index(':root[data-utaipei-theme="light"]')
        bridge_dark_index = css.index(':root[data-utaipei-theme="dark"]')
        self.assertLess(media_index, legacy_light_index)
        self.assertLess(legacy_light_index, bridge_light_index)
        self.assertLess(media_index, bridge_dark_index)
        for token in (
            "--ui-canvas: #F8FAFC",
            "--ui-surface: #FFFFFF",
            "--ui-text: #0F172A",
            "--ui-success: #087f5b",
            "--ui-canvas: #0B1120",
            "--ui-surface: #111827",
            "--ui-text: #F8FAFC",
            "--ui-success: #65d5ab",
        ):
            self.assertIn(token, css)

    def test_update_menu_cancelled_confirmation_does_not_mutate_or_reload(self):
        from ui_components import _build_update_menu_script

        script = _build_update_menu_script()
        prompt = "#utaipei-analysis-state[data-analysis-active='true']"
        prompt_index = script.index(prompt)
        mutation_index = script.index('CLEAR_STATIC_CACHES')
        reload_index = script.index('location.reload')
        self.assertLess(prompt_index, mutation_index)
        self.assertLess(prompt_index, reload_index)
        self.assertIn('if (!parentWindow.confirm', script)

    def test_ephemeral_student_state_marker_truth_table(self):
        rows = ({"course_code": "MATH", "credits": 3},)
        cases = (
            ({}, False),
            ({"transcript_pdf_bytes": b"%PDF"}, True),
            ({"transcript_pdf_path": "utaipei-transcript-1.pdf"}, True),
            ({"_editor_rows": rows}, True),
            ({"manual_rows": rows}, True),
            ({"_parsed_confirmation": SimpleNamespace(rows=rows, state="PARSED")}, True),
            ({"confirmed_input": {"rows": rows}}, True),
            ({"_decision_snapshot_cache_value": object()}, True),
            ({"_snapshot_artifact_cache": {"snapshot_id": "snapshot:one"}}, True),
            ({"_decision_snapshot_cache_value": object(), "_analysis_exported": True}, False),
        )
        for state, expected in cases:
            with self.subTest(state=tuple(state)):
                self.assertEqual(app._has_ephemeral_student_state(state), expected)


if __name__ == "__main__":
    unittest.main()
