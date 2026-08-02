"""
Modular Streamlit app entrypoint for the UTaipei graduation credit checker.
"""

import streamlit as st

from credit_engine import evaluate_graduation
from pdf_parser import parse_transcript_pdf
from report_renderer import render_report
from schedule_parser import merge_schedule_courses
from sidebar import render_sidebar
from ui_components import (
    collapse_sidebar_if_needed,
    render_header_card,
    render_landing_message,
    setup_page,
)


def main():
    setup_page()
    render_header_card("北市大畢業學分審查系統", "🎓 快速檢查你的畢業進度")

    sidebar_state = render_sidebar()
    collapse_sidebar_if_needed()

    transcript_source = sidebar_state["transcript_source"]
    source_label = sidebar_state["source_label"]
    major_domain = sidebar_state["major_domain"]
    program_type = sidebar_state["program_type"]
    target_dept = sidebar_state["target_dept"]
    handbook_year = sidebar_state["handbook_year"]

    if not transcript_source:
        render_landing_message()
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
        report = evaluate_graduation(
            courses,
            {
                "domain": major_domain,
                "program": program_type,
                "target_dept": target_dept,
                "handbook_year": handbook_year,
            },
        )
        render_report(student_info, courses, report, major_domain, program_type, target_dept, source_label)
    except Exception as exc:
        st.error(f"無法完成學分審查：{exc!s}")
        st.info("請確認檔案為北市大歷年成績單。若校務系統最近更新版面，PDF 解析規則可能也需要同步更新。")

    st.write("")


if __name__ == "__main__":
    main()
