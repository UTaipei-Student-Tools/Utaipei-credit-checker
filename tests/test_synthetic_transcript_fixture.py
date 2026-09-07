from course_input_adapter import adapt_legacy_result
from pdf_parser import parse_transcript_pdf
from tests.synthetic_transcript_fixture import build_synthetic_transcript_pdf


def test_synthetic_transcript_exercises_repeat_and_confirmation_boundary():
    student, courses = parse_transcript_pdf(build_synthetic_transcript_pdf())

    assert student["admission_cohort"] == "114"
    assert student["parse_diagnostics"]["course_count"] == 4
    assert len(courses) == 4

    confirmation = adapt_legacy_result(courses, source_kind="transcript").confirmation
    assert confirmation.valid is True
    assert confirmation.state.value == "PARSED"
    assert len(confirmation.rows) == 5
    calculus = [row for row in confirmation.rows if row.course_name == "微積分"]
    assert [(row.term, row.status) for row in calculus] == [
        ("114-1", "FAILED"),
        ("114-2", "COMPLETED"),
    ]
