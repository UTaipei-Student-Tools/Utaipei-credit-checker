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
