"""Privacy-safe regression coverage for transcript column year assignment."""

from __future__ import annotations

import fitz

from course_input_adapter import adapt_legacy_result
from pdf_parser import parse_transcript_pdf


def _insert_course(page, x, y, name, *, semester=1, credit="2", score="80", course_type="選"):
    """Insert one parser-shaped course row without real student data."""

    page.insert_text((x + 5, y), name, fontname="china-t", fontsize=8)
    page.insert_text((x + 145, y), course_type, fontname="china-t", fontsize=8)
    if semester == 1:
        page.insert_text((x + 175, y), str(credit), fontsize=8)
        page.insert_text((x + 205, y), str(score), fontsize=8)
    else:
        page.insert_text((x + 220, y), str(credit), fontsize=8)
        page.insert_text((x + 250, y), str(score), fontsize=8)


def _insert_identity(page):
    """Add only synthetic metadata needed to reach the parser seam."""

    for y, text in (
        (20, "姓名：匿名測試"),
        (35, "學號：SYNTHETIC"),
        (50, "系所：資訊科學系"),
        (65, "入學年月：114年9月"),
        (80, "列印日期(Date of Issue)：2026/09/06"),
    ):
        page.insert_text((20, y), text, fontname="china-t", fontsize=8)


def _year_layout_pdf(*, include_headers=True, include_second_page=False):
    document = fitz.open()
    page = document.new_page(width=600, height=700)
    _insert_identity(page)

    if include_headers:
        page.insert_text((20, 115), "113學年 (113學年09月至114年06月)", fontname="china-t", fontsize=8)
        page.insert_text((20, 250), "114學年 (114學年09月至115年06月)", fontname="china-t", fontsize=8)
        page.insert_text((320, 200), "115學年 (115學年09月至116年01月)", fontname="china-t", fontsize=8)

    _insert_course(page, 20, 135, "LeftUpper", credit="3", score="80")
    _insert_course(page, 20, 270, "LeftLower", credit="2", score="80")
    _insert_course(page, 300, 135, "MartialArts", semester=2, credit="0", score="P", course_type="必")
    _insert_course(page, 300, 150, "NaturalLife", credit="2", score="80")
    _insert_course(page, 300, 185, "HumanArchitecture", semester=2, credit="2", score="80")
    _insert_course(page, 300, 220, "RightInProgress", credit="1", score="INPROGRESS")

    if include_second_page:
        page = document.new_page(width=600, height=700)
        _insert_course(page, 300, 120, "CrossPage", credit="1", score="80")

    try:
        return document.tobytes()
    finally:
        document.close()


def _no_year_pdf():
    document = fitz.open()
    page = document.new_page(width=600, height=700)
    _insert_identity(page)
    page.insert_text((20, 115), "學年", fontname="china-t", fontsize=8)
    _insert_course(page, 20, 135, "NoYear", credit="2", score="80")
    try:
        return document.tobytes()
    finally:
        document.close()


def test_two_column_year_headers_follow_visual_stream_order():
    student, courses = parse_transcript_pdf(_year_layout_pdf())

    rows = adapt_legacy_result(courses, source_kind="transcript").rows
    by_name = {row["course_name"]: row for row in rows}

    assert len(courses) == 6
    assert student["parse_diagnostics"]["totals"]["all_course_credits"] == 10.0
    assert student["parse_diagnostics"]["totals"]["earned_credits"] == 9.0
    assert student["parse_diagnostics"]["totals"]["in_progress_credits"] == 1.0
    assert by_name["LeftUpper"]["term"] == "113-1"
    assert by_name["LeftLower"]["term"] == "114-1"
    assert by_name["MartialArts"]["term"] == "114-2"
    assert by_name["NaturalLife"]["term"] == "114-1"
    assert by_name["HumanArchitecture"]["term"] == "114-2"
    assert by_name["RightInProgress"]["term"] == "115-1"
    assert by_name["RightInProgress"]["status"] == "IN_PROGRESS"


def test_right_column_year_carry_survives_page_break():
    student, courses = parse_transcript_pdf(
        _year_layout_pdf(include_second_page=True)
    )

    rows = adapt_legacy_result(courses, source_kind="transcript").rows
    carry = [row for row in rows if row["course_name"] == "CrossPage"]

    assert len(carry) == 1
    assert carry[0]["term"] == "115-1"
    assert student["parse_diagnostics"]["course_count"] == 7


def test_course_without_year_header_or_carry_is_fatal():
    student, courses = parse_transcript_pdf(_no_year_pdf())

    diagnostic = student["parse_diagnostics"]

    assert len(courses) == 1
    assert diagnostic["totals"]["earned_credits"] == 2.0
    assert diagnostic["complete"] is False
    assert diagnostic["term_assignment"]["fatal"] is True
    assert diagnostic["term_assignment"]["issues"]
