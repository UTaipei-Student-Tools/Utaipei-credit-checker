from app.models import CourseStatus, DataQuality
from app.parsers.selection import parse_selection_html_with_diagnostics
from app.parsers.transcript import parse_transcript_text_with_diagnostics


def test_parse_transcript_text_statuses_and_semesters():
    text = """
    113 學年度 第 一 學期
    計算機概論 3 88
    C 程式設計 3 F
    Java 程式設計 3 80 先修未過
    資料結構 3 退選
    """
    parsed = parse_transcript_text_with_diagnostics(text)
    by_name = {course.name: course for course in parsed.courses}
    assert parsed.diagnostic.quality == DataQuality.COMPLETE
    assert by_name["計算機概論"].semester == "113-一"
    assert by_name["C 程式設計"].grade == "F"
    assert by_name["Java 程式設計"].status == CourseStatus.NEEDS_REVIEW
    assert by_name["資料結構"].status == CourseStatus.INVALID


def test_transcript_parser_fails_closed_when_no_courses():
    parsed = parse_transcript_text_with_diagnostics("這不是成績單")
    assert parsed.courses == []
    assert parsed.diagnostic.quality == DataQuality.FAILED


def test_selection_parser_uses_header_not_first_number():
    html = """
    <table>
      <tr><th>選課代號</th><th>課程名稱</th><th>學分數</th><th>必選修</th><th>開課系所</th></tr>
      <tr><td>12345</td><td>演算法</td><td>3</td><td>必修</td><td>資訊科學系</td></tr>
    </table>
    """
    parsed = parse_selection_html_with_diagnostics(html)
    assert parsed.diagnostic.quality == DataQuality.COMPLETE
    assert parsed.courses[0].name == "演算法"
    assert parsed.courses[0].credits == 3
    assert parsed.courses[0].status == CourseStatus.IN_PROGRESS
    assert parsed.courses[0].department == "資訊科學系"


def test_selection_parser_rejects_table_without_required_headers():
    html = "<table><tr><th>代碼</th><th>老師</th></tr><tr><td>123</td><td>王老師</td></tr></table>"
    parsed = parse_selection_html_with_diagnostics(html)
    assert parsed.courses == []
    assert parsed.diagnostic.quality == DataQuality.FAILED


def test_selection_parser_marks_invalid_row_partial():
    html = """
    <table>
      <tr><th>課程名稱</th><th>學分</th></tr>
      <tr><td>演算法</td><td>3</td></tr>
      <tr><td>資料結構</td><td>三</td></tr>
    </table>
    """
    parsed = parse_selection_html_with_diagnostics(html)
    assert len(parsed.courses) == 1
    assert parsed.diagnostic.quality == DataQuality.PARTIAL
    assert parsed.diagnostic.unparsed_count == 1


def test_selection_parser_accepts_combined_credit_hour_cell():
    html = """
    <table>
      <tr><th>課程名稱</th><th>學分數/時數</th></tr>
      <tr><td>資料處理與分析</td><td>3/3</td></tr>
    </table>
    """
    parsed = parse_selection_html_with_diagnostics(html)
    assert parsed.diagnostic.quality == DataQuality.COMPLETE
    assert parsed.courses[0].credits == 3
