"""Independent acceptance cases for cumulative transcript credit reconciliation."""

from __future__ import annotations

import fitz
import pytest

from course_input_adapter import adapt_legacy_result
from pdf_parser import build_course_dict, parse_transcript_pdf
from tests.synthetic_transcript_fixture import build_synthetic_transcript_pdf


def transcript_with_summary(attempted=12, earned=9, *, duplicate=False, conflict=False):
    """Only synthetic courses and identities; no live transcript material."""
    with fitz.open(stream=build_synthetic_transcript_pdf(), filetype="pdf") as document:
        # This is a term total, deliberately different from the lifetime total.
        document[0].insert_text((20, 730), "修習學分：3", fontname="china-t", fontsize=10)
        if duplicate:
            with fitz.open(stream=build_synthetic_transcript_pdf(), filetype="pdf") as extra:
                document.insert_pdf(extra)
        summaries = [(attempted, earned)]
        if conflict:
            summaries.append((99, 99))
        for attempted_value, earned_value in summaries:
            page = document.new_page(width=600, height=800)
            for x, label, english, value in (
                (30, "修習總學分數", "Attempted credits", attempted_value),
                (170, "實得總學分數", "Earned credits", earned_value),
            ):
                page.insert_text((x, 180), label, fontname="china-t", fontsize=11)
                page.insert_text((x, 194), english, fontsize=8)
                page.insert_text((x + 25, 213), str(value), fontsize=11)
        return document.tobytes()


def test_global_bilingual_summary_excludes_in_progress_and_ignores_term_total():
    student, courses = parse_transcript_pdf(transcript_with_summary())
    diagnostic = student["parse_diagnostics"]
    normalized = adapt_legacy_result(courses, source_kind="transcript")

    assert diagnostic["reported_total"] == 12
    assert diagnostic["total_reconciled"] is True
    assert diagnostic["complete"] is True
    assert len(normalized.rows) == 5
    assert sum(float(row["earned_credits"]) for row in normalized.rows) == 9


@pytest.mark.parametrize(("attempted", "earned"), [(11, 9), (13, 9), (12, 8), (12, 10)])
def test_both_over_and_under_counts_block_completion(attempted, earned):
    student, _ = parse_transcript_pdf(transcript_with_summary(attempted, earned))
    diagnostic = student["parse_diagnostics"]
    assert diagnostic["total_reconciled"] is False
    assert diagnostic["complete"] is False
    assert diagnostic["fatal_warnings"]


def test_missing_global_summary_does_not_claim_a_completed_reconciliation():
    student, _ = parse_transcript_pdf(build_synthetic_transcript_pdf())
    diagnostic = student["parse_diagnostics"]
    assert diagnostic["reported_total"] is None
    assert diagnostic["total_reconciled"] is False
    assert diagnostic["complete"] is True


@pytest.mark.parametrize("option", ["duplicate", "conflict"])
def test_duplicate_courses_or_conflicting_summary_are_not_silently_accepted(option):
    student, _ = parse_transcript_pdf(transcript_with_summary(**{option: True}))
    diagnostic = student["parse_diagnostics"]
    assert diagnostic["total_reconciled"] is False
    assert diagnostic["complete"] is False


@pytest.mark.parametrize("score", ["F", "W", "停", "55", "未", "--"])
def test_zero_credit_failure_or_pending_does_not_complete_a_required_activity(score):
    course = build_course_dict("大學生活學習與輔導", "必", "0", score, "", "", "114")
    assert course["is_completed"] is False
    assert course["completed_credit"] == 0


@pytest.mark.parametrize("score", ["P", "60", "100", "免"])
def test_passed_zero_credit_activity_does_not_create_earned_credit(score):
    course = build_course_dict("大學生活學習與輔導", "必", "0", score, "", "", "114")
    assert course["is_completed"] is True
    assert course["completed_credit"] == 0
