# -*- coding: utf-8 -*-
"""
Modular Streamlit app entrypoint for the UTaipei graduation credit checker.
"""

import streamlit as st
from pdf_parser import parse_transcript_pdf
from credit_engine import evaluate_graduation
from handbook_rules import get_rules_meta
from ui_components import setup_page, render_header_card, render_landing_message, collapse_sidebar_if_needed
from sidebar import render_sidebar
from report_renderer import render_report
from pdf_parser import load_courses_from_csv
import os


def main():
    setup_page()
    render_header_card(
        "北市大畢業學分審查系統",
        "🎓 快速檢查你的畢業進度"
    )

    rules_meta = get_rules_meta()
    sidebar_state = render_sidebar(rules_meta)
    collapse_sidebar_if_needed()

    transcript_pdf_path = sidebar_state["transcript_pdf_path"]
    offline_demo = sidebar_state["offline_demo"]
    major_domain = sidebar_state["major_domain"]
    program_type = sidebar_state["program_type"]
    target_dept = sidebar_state["target_dept"]

    if not transcript_pdf_path:
        render_landing_message()
        return

    try:
        student_info, courses = parse_transcript_pdf(transcript_pdf_path)
        # If PDF parsing yields unexpectedly low totals, try to fallback to a nearby CSV export if available.
        parsed_total = sum(c.get('total_credit', 0.0) or 0.0 for c in courses)
        # Candidate CSV locations to check (project root, workspace)
        cwd = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(cwd, '2026-05-23T08-39_export.csv'),
            os.path.join(cwd, '..', '2026-05-23T08-39_export.csv'),
            os.path.join(cwd, '..', '..', '2026-05-23T08-39_export.csv'),
        ]
        csv_used = None
        for p in candidates:
            if os.path.exists(p):
                s_info_csv, courses_csv = load_courses_from_csv(p)
                csv_total = sum(c.get('total_credit', 0.0) or 0.0 for c in courses_csv)
                if csv_total > parsed_total:
                    courses = courses_csv
                    student_info = s_info_csv
                    csv_used = p
                    break
        report = evaluate_graduation(
            courses,
            {
                "domain": major_domain,
                "program": program_type,
                "target_dept": target_dept,
            },
        )
        render_report(student_info, courses, report, major_domain, program_type, target_dept, offline_demo)
        if csv_used:
            st.info(f"已自動採用匯出 CSV 檔案作為課表來源：{os.path.basename(csv_used)}（因 PDF 解析結果較少）")
    except Exception as exc:
        st.error(f"解析或學分計算出錯: {str(exc)}")
        st.exception(exc)

    # 增加底部空白，避免下滑卡住
    st.markdown("<div style='height: 150px;'></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
