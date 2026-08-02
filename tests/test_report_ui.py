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


if __name__ == "__main__":
    unittest.main()
