"""
Modular Streamlit app entrypoint for the UTaipei graduation credit checker.
"""

import streamlit as st

from credit_engine import evaluate_graduation
from pdf_parser import parse_transcript_pdf
from pwa_metadata import inject_pwa_metadata
from report_renderer import render_report
from schedule_parser import merge_schedule_courses
from sidebar import render_sidebar
from equivalency_ui import render_equivalency_workflow
from ui_components import (
    collapse_sidebar_if_needed,
    render_header_card,
    render_landing_message,
    setup_page,
)


def _evaluation_config(sidebar_state, courses=None, parser_diagnostics=None):
    """Build one cohort-aware config while retaining legacy engine fields."""

    config = {
        "admission_cohort": sidebar_state.get("admission_cohort") or sidebar_state.get("handbook_year"),
        "primary_program": sidebar_state.get("primary_program") or "地生",
        "primary_track": sidebar_state.get("primary_track"),
        "program_type": sidebar_state.get("program_type", "單主修"),
        "target_program": sidebar_state.get("target_program"),
        "target_track": sidebar_state.get("target_track"),
        "target_dept": sidebar_state.get("target_dept"),
        "application_year": sidebar_state.get("application_year"),
        "application_semester": sidebar_state.get("application_semester"),
        "application_status": sidebar_state.get("application_status"),
        "shared_credits": sidebar_state.get("shared_credits"),
        "shared_approved": sidebar_state.get("shared_approved"),
        "shared_evidence_state": sidebar_state.get("shared_evidence_state"),
        "cohort_mismatch_confirmed": bool(sidebar_state.get("cohort_mismatch_confirmed", False)),
        "interrupted": bool(sidebar_state.get("interrupted", False)),
        "cs_project_evidence": sidebar_state.get("cs_project_evidence"),
        "cs_certification_a": sidebar_state.get("cs_certification_a"),
        "cs_certification_b": sidebar_state.get("cs_certification_b"),
        "cs_alternative_course": sidebar_state.get("cs_alternative_course"),
        "equivalency_decisions": st.session_state.get("equivalency_decisions", []),
        "courses": courses or [],
    }
    if parser_diagnostics is not None:
        config["parser_diagnostics"] = parser_diagnostics
    return config


def main():
    setup_page()
    inject_pwa_metadata()
    render_header_card("北市大畢業學分審查系統", "🎓 快速檢查你的畢業進度", landmark_id="main-content")

    sidebar_state = render_sidebar()
    collapse_sidebar_if_needed()

    transcript_source = sidebar_state["transcript_source"]
    source_label = sidebar_state["source_label"]
    major_domain = sidebar_state["major_domain"]
    program_type = sidebar_state["program_type"]
    target_dept = sidebar_state["target_dept"]

    if not transcript_source:
        render_landing_message()
        try:
            report = evaluate_graduation([], _evaluation_config(sidebar_state))
            render_equivalency_workflow(
                [],
                report,
                _evaluation_config(sidebar_state),
            )
            render_report(
                {"name": "", "student_id": "", "department": "", "admission_year": "", "print_date": ""},
                [],
                report,
                sidebar_state.get("primary_track") or major_domain,
                program_type,
                target_dept,
                source_label,
            )
        except Exception as exc:
            st.info("目前先顯示門檻規劃；上傳成績單或完成校務系統抓取後，才會開始個人學分審查。")
        return

    try:
        student_info, courses = parse_transcript_pdf(transcript_source)
        courses, added_schedule_courses = merge_schedule_courses(
            courses,
            st.session_state.get("schedule_courses", []),
        )
        if added_schedule_courses:
            credits = sum(float(course.get("total_credit") or 0.0) for course in added_schedule_courses)
            st.toast(f"已將課表中的 {len(added_schedule_courses)} 門、{credits:g} 學分納入修讀中進度。")
        parser_diagnostics = student_info.get("parse_diagnostics", {})
        selected_cohort = str(sidebar_state.get("admission_cohort") or "").strip()
        detected_cohort = str(parser_diagnostics.get("detected_admission_cohort") or "").strip()
        if detected_cohort and selected_cohort and detected_cohort != selected_cohort:
            st.warning(
                f"成績單辨識到 {detected_cohort} 學年度入學，但目前選定 {selected_cohort} 學年度手冊；"
                "未確認前，審查結果會保守標示為需人工確認。"
            )
            sidebar_state["cohort_mismatch_confirmed"] = st.checkbox(
                "我已核對適用規定，仍要使用目前選定的手冊",
                value=bool(sidebar_state.get("cohort_mismatch_confirmed", False)),
                key="cohort_mismatch_confirmation",
                help="這是稽核確認，不會自動替換入學 cohort 或學生手冊。",
            )
        else:
            sidebar_state["cohort_mismatch_confirmed"] = False
            st.session_state.pop("cohort_mismatch_confirmation", None)
        report = evaluate_graduation(
            courses,
            _evaluation_config(sidebar_state, courses, parser_diagnostics),
        )
        render_equivalency_workflow(
            courses,
            report,
            _evaluation_config(sidebar_state, courses, parser_diagnostics),
        )
        render_report(
            student_info,
            courses,
            report,
            sidebar_state.get("primary_track") or major_domain,
            program_type,
            target_dept,
            source_label,
        )
    except Exception as exc:
        st.error(f"無法完成學分審查：{exc!s}")
        st.info("請確認檔案為北市大歷年成績單。若校務系統最近更新版面，PDF 解析規則可能也需要同步更新。")

    st.write("")


if __name__ == "__main__":
    main()
