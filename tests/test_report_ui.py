import unittest

from streamlit.testing.v1 import AppTest

SECTION_LABELS = [
    "📊 學分進度概覽",
    "一、校共同課程",
    "二、系共同必修",
    "三、專業必修",
    "四、專業選修",
    "五、其他本系課程",
    "六、自由選修",
    "🧪 雙主修",
    "📦 全部匯出",
]


def _navigation_fixture():
    from credit_engine import evaluate_graduation
    from pdf_parser import build_course_dict
    from report_renderer import _render_report_sections

    courses = [build_course_dict("微積分(I)", "選", "3", "80", "", "", "114")]
    courses[0]["allocation_note"] = "雙主修目標採認；超額時轉自由選修"
    report = evaluate_graduation(
        courses,
        {
            "domain": "地球環境",
            "program": "雙主修",
            "target_dept": "資科系",
            "handbook_year": "114",
        },
    )
    _render_report_sections(
        courses,
        report,
        report["summary"],
        "地球環境",
        "雙主修",
        "資科系",
        report["requirements"],
    )


def _domain_in_progress_fixture():
    from pdf_parser import build_course_dict
    from report_renderer import _render_domain_compulsory_section

    oceanography = build_course_dict("海洋學", "必", "2", "未", "", "", "115")
    _render_domain_compulsory_section(
        {
            "domain_compulsory_completed": 0.0,
            "domain_compulsory_ip": 2.0,
            "domain_compulsory_courses": [oceanography],
            "domain_compulsory_missing": [
                {"name": "海洋學", "credit": 2},
                {"name": "地質學", "credit": 3},
            ],
        },
        "地球環境",
        {"domain_compulsory": 14},
    )


def _credit_format_fixture():
    from report_renderer import _render_course_cards, _render_parsed_course_totals
    from ui_components import draw_premium_progress

    _render_course_cards(
        [
            {"科目名稱": "整數學分", "修課學年": "114學年", "學分": 2, "成績": "80", "狀態": "已修畢"},
            {"科目名稱": "小數學分", "修課學年": "114學年", "學分": 1.5, "成績": "80", "狀態": "已修畢"},
        ]
    )
    draw_premium_progress("測試進度", 2, 3, ip=1)
    _render_parsed_course_totals(
        [
            {
                "total_credit": 3.0,
                "completed_credit": 2.0,
                "is_in_progress": True,
            }
        ],
        {"total_with_ip": 3.0},
        "單主修",
    )


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


def _semantic_markup_fixture():
    from report_renderer import _render_course_cards, _render_metric_cards

    _render_course_cards(
        [
            {
                "科目名稱": "語意化課程",
                "修課學年": "114學年",
                "學分": 3,
                "成績": "80",
                "狀態": "已修畢",
                "課程身分": "MANUAL_APPROVED",
                "身分範圍": "物化系化學組",
                "身分理由": "系所核准替代",
                "身分核准單位": "物化系課程委員會",
                "身分證據引用": "核准單-001",
            }
        ]
    )
    _render_metric_cards(
        {
            "total_completed": 3,
            "total_ip": 0,
            "total_with_ip": 3,
            "common_completed": 0,
            "common_ip": 0,
            "major_completed": 3,
            "major_ip": 0,
            "free_completed": 0,
            "free_ip": 0,
            "target_completed": 0,
            "target_ip": 0,
        },
        {"pe": {"semesters_completed": 0, "semesters_required": 4, "semesters_ip": 0}},
        "地生",
        "單主修",
        "",
        {
            "total": 128,
            "common_total": 28,
            "major_total": 80,
            "free_elective": 20,
            "target_total": 0,
        },
    )


def _full_report_fixture():
    """Render the complete report path, including Lieflat and navigation."""

    from credit_engine import evaluate_graduation
    from pdf_parser import build_course_dict
    from report_renderer import render_report

    courses = [build_course_dict("海洋學", "必", "2", "未", "", "", "114")]
    report = evaluate_graduation(
        courses,
        {"domain": "地球環境", "program": "單主修", "target_dept": "", "handbook_year": "114"},
    )
    render_report(
        {"name": "測試學生", "student_id": "u", "department": "地生系", "admission_year": "114", "print_date": "2026"},
        courses,
        report,
        "地球環境",
        "單主修",
        "",
        "測試 PDF",
    )


def _legacy_report_sensitive_identity_fixture():
    """Exercise the compatibility renderer with raw parser identity fields."""

    from credit_engine import evaluate_graduation
    from report_renderer import render_report

    report = evaluate_graduation(
        [],
        {"domain": "地球環境", "program": "單主修", "target_dept": "", "handbook_year": "114"},
    )
    render_report(
        {
            "name": "王小明",
            "student_id": "A123456789",
            "department": "地生系",
            "admission_year": "114",
            "print_date": "2026",
        },
        [],
        report,
        "地球環境",
        "單主修",
        "",
        "測試 PDF",
    )


def _first_run_fixture():
    """Run the real app with a fresh session and no transcript."""

    import app as app_module

    app_module.main()


def _apc_navigation_fixture():
    from credit_engine import evaluate_graduation
    from handbook_rules import get_apc_target_requirements
    from report_renderer import _render_report_sections

    target_requirements = get_apc_target_requirements("114", "化學組", "雙主修")
    report = evaluate_graduation(
        [],
        {
            "domain": "地球環境",
            "program": "雙主修",
            "target_dept": "物化系化學組",
            "handbook_year": "114",
            "target_requirements": target_requirements,
        },
    )
    _render_report_sections([], report, report["summary"], "地球環境", "雙主修", "物化系化學組", report["requirements"])


class ReportNavigationTests(unittest.TestCase):
    def test_compatibility_report_masks_raw_name_and_student_id(self):
        app = AppTest.from_function(_legacy_report_sensitive_identity_fixture, default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        rendered = "\n".join(str(element.value) for element in app.markdown)
        self.assertNotIn("王小明", rendered)
        self.assertNotIn("A123456789", rendered)
        self.assertIn("王＊＊", rendered)
        self.assertIn("A1••••89", rendered)

    def test_first_run_controls_are_on_main_page_without_fake_report(self):
        app = AppTest.from_function(_first_run_fixture, default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.file_uploader), 1)
        self.assertEqual(len(app.sidebar.file_uploader), 0)
        self.assertEqual(len(app.text_input), 2)
        self.assertTrue(any("開始設定" in expander.label for expander in app.expander))
        self.assertTrue(any("手冊來源與核對狀態" in expander.label for expander in app.expander))
        self.assertFalse(any("科目與門檻預覽" in expander.label for expander in app.expander))
        rendered_text = "\n".join(
            str(element.value)
            for element_type in (app.markdown, app.info, app.warning, app.caption)
            for element in element_type
        )
        self.assertNotIn("未辨識", rendered_text)
        self.assertNotIn("已分析 0 筆", rendered_text)
        # The compact first-run panel uses the selectbox label as the field
        # heading; redundant captions were removed to keep the four controls
        # in the first viewport.
        self.assertTrue(any(widget.label == "入學年度" for widget in app.selectbox))
        state_keys = set(app.session_state._state._keys())
        self.assertNotIn("student_pwd", state_keys)
        self.assertNotIn("portal_password_input", state_keys)

    def test_full_report_lieflat_continues_to_selector(self):
        app = AppTest.from_function(_full_report_fixture, default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.selectbox), 1)
        options = list(app.selectbox[0].options)
        self.assertEqual(options[:7], SECTION_LABELS[:7])
        self.assertIn("📦 全部匯出", options)
        self.assertNotIn("🗓️ 模擬排課", options)
        self.assertTrue(any("畢業總學分" in str(element.value) for element in app.markdown))

    def test_overview_subtotals_are_expandable_with_course_details_and_allocation_note(self):
        app = AppTest.from_function(_navigation_fixture, default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        labels = [expander.label for expander in app.expander]
        self.assertTrue(any(label.startswith("自由選修｜") for label in labels))
        self.assertTrue(any("資科系指定／專業必修｜已得 0.0／15.0" in label for label in labels))
        self.assertTrue(any("資科系專業選修｜已得 3.0／25.0" in label for label in labels))
        rendered_html = "\n".join(str(element.value) for element in app.markdown)
        self.assertIn("微積分(I)", rendered_html)
        self.assertIn("3.0", rendered_html)
        self.assertIn("已修畢", rendered_html)
        self.assertIn("配置：雙主修目標採認；超額時轉自由選修", rendered_html)

    def test_apc_target_subtotals_use_base_and_other_denominators(self):
        app = AppTest.from_function(_apc_navigation_fixture, default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        labels = [expander.label for expander in app.expander]
        self.assertTrue(any("物化系化學組基礎／共同必修｜已得 0.0／16.0" in label for label in labels))
        self.assertTrue(any("物化系化學組指定／專業必修｜已得 0.0／24.0" in label for label in labels))

    def test_all_report_sections_are_visible_in_one_selector(self):
        app = AppTest.from_function(_navigation_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.selectbox), 1)
        self.assertEqual(list(app.selectbox[0].options), SECTION_LABELS)
        self.assertEqual(app.selectbox[0].value, "overview")

    def test_lower_sections_render_independently(self):
        app = AppTest.from_function(_navigation_fixture, default_timeout=20).run()
        checks = {
            "dept_required": "二、系共同必修",
            "target": "雙主修：資科系",
            "export": "全部匯出",
        }
        for section_id, expected_text in checks.items():
            with self.subTest(section=section_id):
                app.selectbox[0].set_value(section_id).run()
                self.assertEqual(len(app.exception), 0)
                rendered_text = "\n".join(
                    str(element.value)
                    for element_type in (app.markdown, app.info, app.warning, app.caption)
                    for element in element_type
                )
                self.assertIn(expected_text, rendered_text)

    def test_in_progress_required_course_is_not_rendered_again_as_missing(self):
        app = AppTest.from_function(_domain_in_progress_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        rendered_html = "\n".join(str(element.value) for element in app.markdown)
        self.assertEqual(rendered_html.count("data-label='科目名稱'>海洋學</div>"), 1)
        self.assertIn("在修中", rendered_html)
        self.assertIn("data-label='科目名稱'>地質學</div>", rendered_html)
        self.assertIn("data-label='學分'>2.0</div>", rendered_html)
        self.assertEqual([item.value for item in app.warning], ["您尚有 1 門必修課程未修習"])

    def test_credit_values_keep_one_decimal_place(self):
        from ui_components import format_credit

        self.assertEqual(format_credit(0), "0.0")
        self.assertEqual(format_credit(2), "2.0")
        self.assertEqual(format_credit("2"), "2.0")
        self.assertEqual(format_credit(2.5), "2.5")

        app = AppTest.from_function(_credit_format_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        rendered_html = "\n".join(
            [*(str(element.value) for element in app.markdown), *_html_values(app)]
        )
        self.assertIn("data-label='學分'>2.0</div>", rendered_html)
        self.assertIn("data-label='學分'>1.5</div>", rendered_html)
        self.assertIn('已得 <b class="credit-completed">2.0</b> 學分', rendered_html)
        self.assertIn('修讀中 <b class="credit-ip">1.0</b>', rendered_html)
        self.assertIn("應修 <b>3.0</b> 學分", rendered_html)
        self.assertIn("解析總學分</span><b>3.0</b>", rendered_html)

    def test_responsive_breakpoints_and_touch_targets_are_injected(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))
        self.assertIn("@media (max-width: 1100px)", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn("--ui-control-height: 44px", css)
        self.assertIn("min-height: var(--ui-control-height)", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)
        self.assertIn('[data-testid="stSidebar"][aria-expanded="true"]', css)
        self.assertIn("max(1.25rem, var(--ui-safe-bottom))", css)
        self.assertNotIn("max(4rem, env(safe-area-inset-bottom, 0px))", css)

    def test_mobile_opaque_status_bar_owns_top_inset_and_streamlit_owns_scroll(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        self.assertEqual(css.count("env(safe-area-inset-top"), 1)
        self.assertEqual(css.count("env(safe-area-inset-bottom"), 1)
        mobile_css = css.split("@media (max-width: 768px)", 1)[1].split(
            "@media (max-width: 480px)", 1
        )[0]
        compact_css = css.split("@media (max-width: 480px)", 1)[1].split(
            "@media (hover: none)", 1
        )[0]

        self.assertIn('[data-testid="stAppViewContainer"]', mobile_css)
        self.assertIn("padding: var(--ui-safe-top)", mobile_css)
        self.assertNotIn("padding: 0 !important", mobile_css)
        self.assertIn("var(--ui-safe-top)", mobile_css)
        self.assertIn("padding: var(--ui-safe-top)", css)
        self.assertIn("padding: .85rem", mobile_css)
        self.assertIn("max(.85rem, var(--ui-safe-right))", mobile_css)
        self.assertIn("max(1.25rem, var(--ui-safe-bottom))", mobile_css)
        self.assertNotIn("overflow-y: auto", mobile_css)
        self.assertNotIn("overflow-y: hidden", mobile_css)
        self.assertIn("max(.65rem, var(--ui-safe-left))", compact_css)
        self.assertIn("max(.65rem, var(--ui-safe-right))", compact_css)
        self.assertNotIn("100vh", css)
        self.assertNotIn("100dvh", css)

    def test_semantic_tokens_cover_light_and_dark_surfaces(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        for token in (
            "--ui-canvas",
            "--ui-surface",
            "--ui-surface-raised",
            "--ui-text",
            "--ui-text-muted",
            "--ui-border",
            "--ui-accent",
            "--ui-success",
            "--ui-warning",
            "--ui-danger",
            "--ui-focus",
        ):
            with self.subTest(token=token):
                self.assertIn(token, css)
        self.assertIn("color-scheme: light", css)
        self.assertIn("color-scheme: dark", css)
        self.assertIn("@media (prefers-color-scheme: dark)", css)
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn('html[data-theme="light"]', css)
        self.assertLess(
            css.index("@media (prefers-color-scheme: dark)"),
            css.index('html[data-theme="light"]'),
        )
        self.assertLess(
            css.index("@media (prefers-color-scheme: dark)"),
            css.index('html[data-theme="dark"]'),
        )
        for token in (
            "--ui-canvas: #F8FAFC",
            "--ui-surface: #FFFFFF",
            "--ui-text: #0F172A",
            "--ui-text-muted: #475569",
            "--ui-text-faint: #64748B",
            "--ui-border: #E2E8F0",
            "--ui-border-strong: #CBD5E1",
            "--ui-academic-primary: #1E3A5F",
            "--ui-accent: #2563EB",
        ):
            self.assertIn(token, css)
        for token in (
            "--ui-canvas: #0B1120",
            "--ui-surface: #111827",
            "--ui-surface-raised: #172033",
            "--ui-text: #F8FAFC",
            "--ui-text-muted: #CBD5E1",
            "--ui-border: #334155",
            "--ui-accent: #60A5FA",
        ):
            self.assertIn(token, css)
        self.assertIn('html:has(.stApp[data-theme="dark"])', css)

    def test_dark_mode_controls_portals_tables_and_focus_are_explicit(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        for selector in (
            'input, textarea, select',
            '[data-baseweb="popover"]',
            '[role="option"]:hover',
            '[data-testid="stDataFrame"]',
            '[role="columnheader"]',
            '.report-table-wrap',
            '.course-list',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
        self.assertIn(":focus-visible", css)
        self.assertIn("outline: 3px solid var(--ui-focus)", css)
        self.assertIn("font-variant-numeric: tabular-nums", css)
        self.assertIn("position: sticky", css)
        self.assertNotIn("overflow-x: auto", css)
        self.assertIn("overflow-x: clip", css)
        self.assertIn("min-width: 0", css)
        self.assertNotIn("min-width: 32rem", css)
        self.assertNotIn("min-width: 34rem", css)
        self.assertNotIn("min-width: 42rem", css)
        self.assertNotIn("white-space: nowrap", css)
        self.assertNotIn("Noto Serif TC", css)
        self.assertNotIn("gradient(", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertNotIn("transition: all", css)

    def test_select_combobox_focus_ring_is_drawn_on_outer_group_not_text_caret(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(_html_values(app))

        input_selector = '[data-testid="stSelectbox"] input[role="combobox"]:focus-visible'
        group_selector = '[data-testid="stSelectbox"] [role="group"]:focus-within'
        baseweb_selector = '[data-testid="stSelectbox"] [data-baseweb="select"]:focus-within'
        baseweb_inner_selector = '[data-testid="stSelectbox"] [data-baseweb="select"] > div'
        self.assertIn(input_selector, css)
        self.assertIn(group_selector, css)
        self.assertIn(baseweb_selector, css)
        self.assertIn(baseweb_inner_selector, css)

        input_focus_css = css.split(input_selector, 1)[1].split("}", 1)[0]
        group_focus_css = css.split(group_selector, 1)[1].split("}", 1)[0]
        baseweb_focus_css = css.split(baseweb_selector, 1)[1].split("}", 1)[0]
        baseweb_inner_css = css.split(baseweb_inner_selector, 1)[1].split("}", 1)[0]
        self.assertIn("outline: none !important", input_focus_css)
        self.assertIn("box-shadow: none !important", input_focus_css)
        self.assertIn("border-color: var(--ui-focus) !important", group_focus_css)
        self.assertIn("box-shadow:", group_focus_css)
        self.assertIn("border-color: var(--ui-focus) !important", baseweb_focus_css)
        self.assertIn("box-shadow:", baseweb_focus_css)
        self.assertIn("border: 0 !important", baseweb_inner_css)
        self.assertIn("box-shadow: none !important", baseweb_inner_css)
        self.assertIn(
            '[data-testid="stSelectbox"] [role="group"] [data-baseweb="select"]:focus-within',
            css,
        )
        self.assertIn("caret-color: transparent", css)

    def test_report_markup_uses_semantic_classes_without_light_only_inline_colors(self):
        app = AppTest.from_function(_semantic_markup_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        rendered_html = "\n".join(str(element.value) for element in app.markdown)
        self.assertIn("class='course-list'", rendered_html)
        self.assertIn("class='status-badge status-completed'", rendered_html)
        self.assertIn("人工核准身分", rendered_html)
        self.assertIn("系所核准替代", rendered_html)
        self.assertIn("物化系課程委員會", rendered_html)
        self.assertIn("核准單-001", rendered_html)
        self.assertIn("class='metric-grid'", rendered_html)
        self.assertNotIn("background:#ffffff", rendered_html)
        self.assertNotIn("color:#0f172a", rendered_html)


if __name__ == "__main__":
    unittest.main()
