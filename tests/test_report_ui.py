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
    "🗓️ 模擬排課",
]


def _navigation_fixture():
    from credit_engine import evaluate_graduation
    from pdf_parser import build_course_dict
    from report_renderer import _render_report_sections

    courses = [build_course_dict("微積分(I)", "選", "3", "80", "", "", "114")]
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


class ReportNavigationTests(unittest.TestCase):
    def test_all_ten_report_sections_are_visible_in_one_selector(self):
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
            "planner": "模擬排課",
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
        self.assertIn("data-label='學分' style='color:#334155;'>2.0</div>", rendered_html)
        self.assertEqual([item.value for item in app.warning], ["您尚有 1 門必修課程未修習"])

    def test_credit_values_keep_one_decimal_place(self):
        from ui_components import format_credit

        self.assertEqual(format_credit(0), "0.0")
        self.assertEqual(format_credit(2), "2.0")
        self.assertEqual(format_credit("2"), "2.0")
        self.assertEqual(format_credit(2.5), "2.5")

        app = AppTest.from_function(_credit_format_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        rendered_html = "\n".join(str(element.value) for element in app.markdown)
        self.assertIn("data-label='學分' style='color:#334155;'>2.0</div>", rendered_html)
        self.assertIn("data-label='學分' style='color:#334155;'>1.5</div>", rendered_html)
        self.assertIn("已得 <b style=\"color:#0f766e;\">2.0</b> 學分", rendered_html)
        self.assertIn("修讀中 <b style=\"color:#2563eb;\">1.0</b>", rendered_html)
        self.assertIn("應修 <b>3.0</b> 學分", rendered_html)
        self.assertIn("解析總學分: <b>3.0</b>", rendered_html)

    def test_responsive_breakpoints_and_touch_targets_are_injected(self):
        app = AppTest.from_function(_responsive_theme_fixture, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        css = "\n".join(str(element.value) for element in app.markdown)
        self.assertIn("@media (max-width: 1100px)", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)
        self.assertIn('[data-testid="stSidebar"][aria-expanded="true"]', css)


if __name__ == "__main__":
    unittest.main()
