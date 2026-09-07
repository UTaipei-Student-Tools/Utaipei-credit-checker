from copy import deepcopy

import pytest

from course_display import grouped_course_rows, sorted_course_rows
from course_input_adapter import adapt_legacy_result
from input_confirmation import confirm_confirmation, release_formal_attempts
from pdf_parser import transcript_to_markdown, _semester_status, parse_transcript_pdf
from synthetic_transcript_fixture import build_synthetic_transcript_pdf


def test_general_education_first_then_terms_and_required_before_elective():
    rows = [
        dict(course_name="後期選修", term="115-1", course_type="選"),
        dict(course_name="早期選修", term="114-2", course_type="選"),
        dict(course_name="藝術通識", term="115-1", course_type="選", prefix_tag="[通選藝術]"),
        dict(course_name="早期必修", term="114-2", course_type="必"),
        dict(course_name="自然通識", term="114-1", prefix_tag="[通選自然]"),
        dict(course_name="更早必修", term="114-1", course_type="必"),
        dict(course_name="更早必修", term="114-1", course_type="必"),
    ]
    before = deepcopy(rows)
    sorted_rows = sorted_course_rows(rows)
    assert [r["course_name"] for r in sorted_rows] == [
        "自然通識", "藝術通識", "更早必修", "更早必修", "早期必修", "早期選修", "後期選修"
    ]
    assert rows == before  # sorting must not mutate input or discard repeats
    assert [title for title, _ in grouped_course_rows(rows)][2:] == ["114-1 學期", "114-2 學期", "115-1 學期"]


@pytest.mark.parametrize("grade", ["退", "退選", "已退選", " 退 ", "W", "停"])
def test_explicit_withdrawal_is_confirmable_but_never_earns_credit(grade):
    adapted = adapt_legacy_result([
        dict(name="測試課", credits=2, term="114-1", grade=grade, status="UNKNOWN")
    ])
    assert adapted.valid
    row = adapted.confirmation.rows[0]
    assert row.status == "WITHDRAWN"
    assert row.earned_credits == 0
    confirmed = confirm_confirmation(adapted.confirmation, adapted.fingerprint)
    assert len(release_formal_attempts(confirmed, confirmed.fingerprint)) == 1
    assert _semester_status(grade, 2) == "ENDED_NO_EARNED"
    markup = transcript_to_markdown([row.as_dict()], collapsible=False)
    assert "已退選" in markup
    assert "不確定" not in markup


def test_two_semesters_keep_individual_grade_and_withdrawal():
    md = transcript_to_markdown([dict(name="測試課", type="必", academic_year="114",
                                    sem1_credit="2", sem1_score="退", sem2_credit="2", sem2_score="85")],
                                collapsible=False)
    assert "114-1 學期" in md and "114-2 學期" in md
    assert md.count("| 測試課 |") == 2
    assert "| 退 | 已退選／停修 |" in md
    assert "| 85 | 已修畢 |" in md


def test_synthetic_pdf_with_withdrawal_can_reach_confirmation():
    _, courses = parse_transcript_pdf(build_synthetic_transcript_pdf(with_review_cases=True))
    adapted = adapt_legacy_result(courses)
    assert adapted.valid, adapted.diagnostics
    assert len(adapted.rows) == 8
    assert sum(row["earned_credits"] for row in adapted.rows) == 14
    withdrawn = [row for row in adapted.rows if row["grade"] == "退"]
    assert len(withdrawn) == 1 and withdrawn[0]["status"] == "WITHDRAWN"


def _actual_editor_fixture():
    import streamlit as st
    from tests.synthetic_transcript_fixture import build_synthetic_transcript_pdf
    from pdf_parser import parse_transcript_pdf
    from course_input_adapter import adapt_legacy_result
    from app import _render_confirmation_editor, _confirmed_rows, _build_evaluation_request, _render_snapshot_outputs
    from graduation_service import evaluate

    if "test_confirmation" not in st.session_state:
        _, courses = parse_transcript_pdf(build_synthetic_transcript_pdf(with_review_cases=True))
        st.session_state["test_confirmation"] = adapt_legacy_result(courses).confirmation
    current = _render_confirmation_editor(st.session_state["test_confirmation"])
    st.session_state["test_confirmation"] = current
    released = _confirmed_rows(current)
    if released:
        snapshot = evaluate(_build_evaluation_request(
            {"admission_cohort": "114", "primary_curriculum_id": "primary:114:cs"},
            current, released_rows=released,
        ))
        _render_snapshot_outputs(snapshot)


def test_actual_editor_preserves_sparse_metadata_and_can_open_graduation_audit():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_actual_editor_fixture, default_timeout=30).run()
    assert not app.exception
    assert app.session_state["test_confirmation"].valid
    assert not app.button(key="confirm_transcript_rows").disabled
    app.button(key="confirm_transcript_rows").click().run()
    assert not app.exception
    assert app.session_state["test_confirmation"].state.value == "CONFIRMED"
    assert app.button(key="prepare_snapshot_exports")
    # A rerun with no edits must not invalidate the confirmed rows.
    app.run()
    assert app.session_state["test_confirmation"].state.value == "CONFIRMED"


def _invalid_editor_fixture():
    from app import _render_confirmation_editor
    from input_confirmation import start_confirmation
    current = start_confirmation([dict(course_name="測試課", credits=2,
        earned_credits=0, status="UNKNOWN", term="114-1")])
    _render_confirmation_editor(current)


def test_invalid_grade_names_the_problem_without_unlocking_confirmation():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(_invalid_editor_fixture).run()
    assert not app.exception
    assert app.button(key="confirm_transcript_rows").disabled
    assert any("修課狀態" in item.value for item in app.caption)
