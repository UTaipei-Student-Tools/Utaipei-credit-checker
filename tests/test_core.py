import unittest

from credit_engine import evaluate_graduation
from handbook_rules import get_credit_requirements, normalize_course_name
from pdf_parser import build_course_dict, parse_transcript_pdf
from schedule_parser import merge_schedule_courses, parse_schedule_html


def course(name, credit=2, score="80", course_type="選"):
    return build_course_dict(name, course_type, str(credit), score, "", "", "114")


class RuleTests(unittest.TestCase):
    def test_name_normalization_handles_full_width_punctuation(self):
        self.assertEqual(normalize_course_name(" 英文（III）：職場商旅 "), "英文(三)")

    def test_requirements_follow_config(self):
        single = get_credit_requirements("單主修", "資科系")
        double = get_credit_requirements("雙主修", "資科系")
        self.assertEqual(single["total"], 128)
        self.assertEqual(single["target_total"], 0)
        self.assertEqual(double["target_total"], 40)


class ParserTests(unittest.TestCase):
    def test_completed_and_in_progress_status(self):
        completed = course("測試課程", 2, "60")
        in_progress = course("另一門課", 3, "未")
        self.assertEqual(completed["completed_credit"], 2)
        self.assertTrue(completed["is_completed"])
        self.assertEqual(in_progress["completed_credit"], 0)
        self.assertTrue(in_progress["is_in_progress"])

    def test_rejects_non_pdf_bytes(self):
        with self.assertRaises(ValueError):
            parse_transcript_pdf(b"not a pdf")

    def test_schedule_parser_respects_second_semester(self):
        html = """
        <table>
          <tr><th>科目名稱</th><th>學分</th><th>選別</th></tr>
          <tr><td>資料結構</td><td>3</td><td>必</td></tr>
        </table>
        """
        parsed = parse_schedule_html(html, academic_year="115", semester="2")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["sem1_credit"], "")
        self.assertEqual(parsed[0]["sem2_credit"], "3.0")
        self.assertEqual(parsed[0]["semester"], "2")
        self.assertEqual(parsed[0]["source"], "schedule")

    def test_schedule_parser_rejects_print_date_noise(self):
        html = """
        <table>
          <tr><td>列印日期:2026/7/29 10:34</td></tr>
        </table>
        """
        self.assertEqual(parse_schedule_html(html, academic_year="115", semester="1"), [])

    def test_schedule_parser_skips_rows_without_valid_credit(self):
        html = """
        <table>
          <tr><th>科目名稱</th><th>學分</th><th>選別</th></tr>
          <tr><td>資料結構</td><td>--</td><td>必</td></tr>
          <tr><td>列印日期:2026/7/29 10:34</td><td>2</td><td>選</td></tr>
        </table>
        """
        self.assertEqual(parse_schedule_html(html), [])

    def test_schedule_grid_requires_course_link_and_explicit_credit(self):
        html = """
        <table>
          <tr>
            <td><a href="ag064_print.jsp?course=123">資料結構</a><span>3 學分</span></td>
            <td>列印日期:2026/7/29 10:34</td>
          </tr>
        </table>
        """
        parsed = parse_schedule_html(html, academic_year="115", semester="1")
        self.assertEqual([course["name"] for course in parsed], ["資料結構"])
        self.assertEqual(parsed[0]["total_credit"], 3.0)

    def test_schedule_courses_merge_as_in_progress_without_duplicates(self):
        transcript = [course("英文(一)", 2)]
        schedule = parse_schedule_html(
            """
            <table>
              <tr><th>科目名稱</th><th>學分</th><th>選別</th></tr>
              <tr><td>英文(一)</td><td>2</td><td>必</td></tr>
              <tr><td>資料結構</td><td>3</td><td>必</td></tr>
            </table>
            """,
            academic_year="115",
            semester="1",
        )
        merged, added = merge_schedule_courses(transcript, schedule)
        self.assertEqual(len(merged), 2)
        self.assertEqual([item["name"] for item in added], ["資料結構"])
        self.assertTrue(added[0]["is_in_progress"])
        report = evaluate_graduation(
            merged,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系"},
        )
        self.assertEqual(report["summary"]["total_ip"], 3)


class EngineTests(unittest.TestCase):
    def test_total_is_preserved_across_classification(self):
        courses = [
            course("英文(一)", 2),
            course("地質學", 3),
            course("資料結構", 3, "未"),
        ]
        report = evaluate_graduation(
            courses,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系"},
        )
        self.assertEqual(report["summary"]["total_completed"], 5)
        self.assertEqual(report["summary"]["total_ip"], 3)
        self.assertEqual(report["summary"]["total_with_ip"], 8)

    def test_invalid_domain_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_graduation([], {"domain": "不存在", "program": "單主修"})


if __name__ == "__main__":
    unittest.main()
import unittest

from credit_engine import evaluate_graduation
from handbook_rules import get_credit_requirements, normalize_course_name
from pdf_parser import build_course_dict, parse_transcript_pdf
from schedule_parser import parse_schedule_html


def course(name, credit=2, score="80", course_type="選"):
    return build_course_dict(name, course_type, str(credit), score, "", "", "114")


class RuleTests(unittest.TestCase):
    def test_name_normalization_handles_full_width_punctuation(self):
        self.assertEqual(normalize_course_name(" 英文（III）：職場商旅 "), "英文(三)")

    def test_requirements_follow_config(self):
        single = get_credit_requirements("單主修", "資科系")
        double = get_credit_requirements("雙主修", "資科系")
        self.assertEqual(single["total"], 128)
        self.assertEqual(single["target_total"], 0)
        self.assertEqual(double["target_total"], 40)


class ParserTests(unittest.TestCase):
    def test_completed_and_in_progress_status(self):
        completed = course("測試課程", 2, "60")
        in_progress = course("另一門課", 3, "未")
        self.assertEqual(completed["completed_credit"], 2)
        self.assertTrue(completed["is_completed"])
        self.assertEqual(in_progress["completed_credit"], 0)
        self.assertTrue(in_progress["is_in_progress"])

    def test_rejects_non_pdf_bytes(self):
        with self.assertRaises(ValueError):
            parse_transcript_pdf(b"not a pdf")

    def test_schedule_parser_respects_second_semester(self):
        html = """
        <table>
          <tr><th>科目名稱</th><th>學分</th><th>選別</th></tr>
          <tr><td>資料結構</td><td>3</td><td>必</td></tr>
        </table>
        """
        parsed = parse_schedule_html(html, academic_year="115", semester="2")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["sem1_credit"], "")
        self.assertEqual(parsed[0]["sem2_credit"], "3.0")
        self.assertEqual(parsed[0]["semester"], "2")


class EngineTests(unittest.TestCase):
    def test_total_is_preserved_across_classification(self):
        courses = [
            course("英文(一)", 2),
            course("地質學", 3),
            course("資料結構", 3, "未"),
        ]
        report = evaluate_graduation(
            courses,
            {"domain": "地球環境", "program": "輔系", "target_dept": "資科系"},
        )
        self.assertEqual(report["summary"]["total_completed"], 5)
        self.assertEqual(report["summary"]["total_ip"], 3)
        self.assertEqual(report["summary"]["total_with_ip"], 8)

    def test_invalid_domain_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_graduation([], {"domain": "不存在", "program": "單主修"})


if __name__ == "__main__":
    unittest.main()
