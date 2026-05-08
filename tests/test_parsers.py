from app.models import CourseStatus
from app.parsers.selection import parse_selection_html
from app.parsers.transcript import parse_transcript_text


def test_parse_transcript_text_statuses():
    text = """
    113 學年度 第 一 學期
    計算機概論 3 88
    C 程式設計 3 59
    Java 程式設計 3 80 先修未過
    資料結構 3 退選
    """
    courses = parse_transcript_text(text)
    by_name = {course.name: course for course in courses}
    assert by_name["計算機概論"].credits == 3
    assert by_name["Java 程式設計"].status == CourseStatus.NEEDS_REVIEW
    assert by_name["資料結構"].status == CourseStatus.INVALID


def test_parse_selection_html_marks_in_progress():
    html = """
    <table>
      <tr><th>科目</th><th>學分數</th><th>必選修</th></tr>
      <tr><td>演算法</td><td>3</td><td>必修</td></tr>
    </table>
    """
    courses = parse_selection_html(html)
    assert courses[0].name == "演算法"
    assert courses[0].status == CourseStatus.IN_PROGRESS

