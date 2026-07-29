"""
Report rendering utilities for the UTaipei graduation credit dashboard.
"""

from html import escape

import pandas as pd
import streamlit as st

from schedule_planner import render_schedule_planner
from ui_components import draw_premium_progress, render_header_card


def render_report(student_info, courses, report, major_domain, program_type, target_dept, source_label):
    summary = report["summary"]
    requirements = report["requirements"]
    safe_source = escape(str(source_label or "未知來源"))
    mode_tag = f"<span class='source-badge'>{safe_source}</span>"

    render_header_card(
        title="🎓 臺北市立大學 歷年畢業學分自我審查系統",
        subtitle=f"{major_domain}領域 / {program_type}{f' ({target_dept})' if program_type != '單主修' else ''}",
    )

    st.markdown(
        f"""
        <div class="info-flex">
            <div class="info-card">
                <div style="font-size:14px; color:#64748b; font-weight:700;">學生資訊</div>
                <div style="margin-top:10px; font-size:15px; color:#0f172a; line-height:1.7;">
                    姓名：<strong>{escape(str(student_info.get("name") or "未辨識"))}</strong><br>
                    學號：<strong>{escape(str(student_info.get("student_id") or "未辨識"))}</strong><br>
                    系所：<strong>{escape(str(student_info.get("department") or "未辨識"))}</strong><br>
                    列印日期：<strong>{escape(str(student_info.get("print_date") or "未辨識"))}</strong>
                </div>
            </div>
            <div class="info-card info-card-highlight">
                <div style="font-size:14px; color:#0f172a; font-weight:700; margin-bottom:8px;">系統模式</div>
                <div style="font-size:18px; color:#0f172a; font-weight:800;">{mode_tag}</div>
                <div style="margin-top:10px; font-size:13px; color:#475569;">已分析 {len(courses)} 筆修課紀錄，並自動分類成畢業必修、選修與跨系學分。</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_parsed_course_totals(courses, report["summary"], program_type)
    _render_metric_cards(summary, report, major_domain, program_type, target_dept, requirements)
    st.markdown("<br><br>", unsafe_allow_html=True)
    _render_tabs(courses, report, summary, major_domain, program_type, target_dept, requirements)


def _render_metric_cards(summary, report, major_domain, program_type, target_dept, requirements):
    colors = ["#00cd98", "#4facfe", "#ffaa00", "#94a3b8", "#a855f7", "#f97316"]
    labels = [
        ("🎓 實得總學分", summary["total_completed"], requirements["total"], summary["total_ip"], colors[0]),
        ("🏫 校共同+通識", summary["common_completed"], requirements["common_total"], summary["common_ip"], colors[1]),
        ("🔬 主修系專門學分", summary["major_completed"], requirements["major_total"], summary["major_ip"], colors[2]),
        ("🔓 自由選修學分", summary["free_completed"], requirements["free_elective"], summary["free_ip"], colors[3]),
        ("✨ 跨系所學分", summary["target_completed"], requirements["target_total"], summary["target_ip"], colors[4]),
        (
            "🎽 體育修課",
            report["pe"]["semesters_completed"],
            report["pe"]["semesters_required"],
            report["pe"]["semesters_ip"],
            colors[5],
        ),
    ]

    html_str = ["<div style='width:100%;'>", "<div class='metric-grid'>"]

    for idx, (label, completed, target, ip, color) in enumerate(labels):
        if label == "✨ 跨系所學分" and program_type == "單主修":
            html_str.append(
                "<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:18px; display:flex; flex-direction:column; justify-content:space-between;'>"
                "<div style='font-size:14px; font-weight:700; color:#475569; margin-bottom:12px;'>🚫 無跨系修讀</div>"
                "<div style='font-size:28px; font-weight:800; color:#94a3b8; margin-bottom:6px;'>N/A</div>"
                "<div style='font-size:12px; color:#94a3b8;'>目前為單主修身份</div>"
                "</div>"
            )
            continue

        total_with_ip = summary.get("total_with_ip", completed + ip) if idx == 0 else completed
        bottom_text = (
            f"已得 {completed:g} / 修讀中 {ip:g} / 應修 {target:g}" if idx == 0 else f"應修 {target:g} / 修讀中 {ip:g}"
        )

        html_str.append(
            f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:18px; display:flex; flex-direction:column; justify-content:space-between;'>"
            f"<div style='font-size:14px; font-weight:700; color:#475569; margin-bottom:12px;'>{label}</div>"
            f"<div style='font-size:28px; font-weight:800; color:{color}; margin-bottom:6px;'>{total_with_ip:g}</div>"
            f"<div style='font-size:12px; color:#64748b;'>{bottom_text}</div>"
            f"</div>"
        )

    # 審查結果卡片 (原來的最後一欄)
    grad_text = "🎉 已達畢業標準" if summary["graduation_ready"] else "⚠️ 未達畢業標準"
    grad_color = "#00cd98" if summary["graduation_ready"] else "#ff3860"
    grad_bg = "rgba(0, 205, 152, 0.08)" if summary["graduation_ready"] else "rgba(255, 56, 96, 0.08)"

    html_str.append(
        f"<div style='background:{grad_bg}; border:1px solid {grad_color}; border-radius:12px; padding:18px; display:flex; flex-direction:column; justify-content:space-between;'>"
        f"<div style='font-size:14px; font-weight:700; color:{grad_color}; margin-bottom:12px;'>✨ 審查結果</div>"
        f"<div style='font-size:20px; font-weight:800; color:{grad_color}; margin-bottom:6px;'>{grad_text}</div>"
        f"<div style='font-size:12px; color:{grad_color}; opacity:0.8;'>含通識/體育/系專/輔雙</div>"
        f"</div>"
    )

    html_str.append("</div></div>")
    st.markdown("".join(html_str), unsafe_allow_html=True)


def _render_tabs(courses, report, summary, major_domain, program_type, target_dept, requirements):
    st.markdown("### 🎯 畢業進度總覽")

    major_target = requirements["total"]
    target_req = requirements["target_total"]
    target_completed = summary["target_completed"]
    target_ip = summary["target_ip"]

    total_completed_all = summary["total_completed"]
    total_ip_all = summary["total_ip"]

    draw_premium_progress("🏆 畢業總學分進度", total_completed_all, major_target, ip=total_ip_all)

    if program_type != "單主修":
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        draw_premium_progress(f"🧪 {program_type} ({target_dept})", target_completed, target_req, ip=target_ip)

    st.markdown("---")

    tabs = st.tabs(
        [
            "📊 學分進度概覽",
            "一、校共同課程",
            "二、系共同必修",
            "三、專業必修",
            "四、專業選修",
            "五、其他本系課程",
            "六、自由選修",
            "🧪 雙主修",
            "📦 全部匯出",
            "🗓️ 模擬排課",
        ]
    )

    with tabs[0]:
        _render_overview_tab(courses, summary, report, major_domain, program_type, target_dept, requirements)

    with tabs[1]:
        _render_common_section(report["common"], report["pe"], requirements)

    with tabs[2]:
        _render_dept_compulsory_section(report["major"], requirements)

    with tabs[3]:
        _render_domain_compulsory_section(report["major"], major_domain, requirements)

    with tabs[4]:
        _render_domain_elective_section(report["major"], major_domain, requirements)

    with tabs[5]:
        _render_other_elective_section(report["major"], requirements)

    with tabs[6]:
        _render_free_elective_section(report["free"], requirements)

    with tabs[7]:
        _render_target_tab(report, program_type, target_dept, summary)

    with tabs[8]:
        _render_export_tab(courses, report, summary, requirements)

    with tabs[9]:
        render_schedule_planner()


def _render_overview_tab(courses, summary, report, major_domain, program_type, target_dept, requirements):
    st.markdown("### 📊 畢業學分進度總覽")
    _render_overview_progress_cards(courses, summary, report, program_type, target_dept, requirements)
    st.markdown("---")

    missing = []
    for item in report["common"]["compulsory_missing"]:
        missing.append({"類別": "校共同必修", "科目名稱": item["name"], "學分": item["credit"]})
    for item in report["major"]["dept_compulsory_missing"]:
        missing.append({"類別": "地生系共同必修", "科目名稱": item["name"], "學分": item["credit"]})
    for item in report["major"]["domain_compulsory_missing"]:
        missing.append({"類別": f"{major_domain}領域必修", "科目名稱": item["name"], "學分": item["credit"]})

    if missing:
        st.warning("⚠️ 您目前尚有以下核心必修科目未修畢：")
        st.dataframe(pd.DataFrame(missing), use_container_width=True)
    else:
        st.success("🎓 您已完成所有主修及共同必修科目。")


def _get_course_category(c, report):
    c_idx = id(c)
    for rc in report.get("common", {}).get("compulsory_courses", []):
        if id(rc) == c_idx:
            return "校共同必修"
    for rc in report.get("common", {}).get("common_elective_courses", []):
        if id(rc) == c_idx:
            return "通識共同選修"
    for cat_name, cat_data in report.get("common", {}).get("categories", {}).items():
        for rc in cat_data.get("courses", []):
            if id(rc) == c_idx:
                return f"通識分類({cat_name})"
    for rc in report.get("major", {}).get("dept_compulsory_courses", []):
        if id(rc) == c_idx:
            return "系共同必修"
    for rc in report.get("major", {}).get("domain_compulsory_courses", []):
        if id(rc) == c_idx:
            return "專業必修"
    for rc in report.get("major", {}).get("domain_elective_courses", []):
        if id(rc) == c_idx:
            return "專業選修"
    for rc in report.get("major", {}).get("other_elective_courses", []):
        if id(rc) == c_idx:
            return "其他本系課程"
    for rc in report.get("target", {}).get("basic_core_courses", []):
        if id(rc) == c_idx:
            return "跨系基礎必修"
    for rc in report.get("target", {}).get("compulsory_courses", []):
        if id(rc) == c_idx:
            return "跨系專業必修"
    for rc in report.get("target", {}).get("elective_courses", []):
        if id(rc) == c_idx:
            return "跨系選修"
    for rc in report.get("pe", {}).get("courses", []):
        if id(rc) == c_idx:
            return "體育"
    for rc in report.get("free", {}).get("courses", []):
        if id(rc) == c_idx:
            return "自由選修"
    return "未歸類"


def _render_overview_progress_cards(courses, summary, report, program_type, target_dept, requirements):
    cards = [
        {
            "title": "一、校共同課程",
            "completed": summary["common_completed"],
            "ip": summary["common_ip"],
            "target": requirements["common_total"],
        },
        {
            "title": "二、系共同必修",
            "completed": report["major"]["dept_compulsory_completed"],
            "ip": report["major"]["dept_compulsory_ip"],
            "target": requirements["major_common_compulsory"],
        },
        {
            "title": "三、專業必修",
            "completed": report["major"]["domain_compulsory_completed"],
            "ip": report["major"]["domain_compulsory_ip"],
            "target": requirements["domain_compulsory"],
        },
        {
            "title": "四、專業選修",
            "completed": report["major"]["domain_elective_completed"],
            "ip": report["major"]["domain_elective_ip"],
            "target": requirements["domain_elective"],
        },
        {
            "title": "五、其他本系課程",
            "completed": report["major"]["other_elective_completed"],
            "ip": report["major"]["other_elective_ip"],
            "target": requirements["major_other_elective"],
        },
        {
            "title": "六、自由選修",
            "completed": summary["free_completed"],
            "ip": summary["free_ip"],
            "target": requirements["free_elective"],
        },
    ]

    df_full = pd.DataFrame(courses)[["name", "type", "academic_year", "total_credit", "is_completed", "is_in_progress"]]
    categories = [_get_course_category(c, report) for c in courses]
    df_full.insert(1, "category", categories)
    df_full.columns = ["科目名稱", "系統分類", "科目屬性", "修課學年", "學分數", "是否完成", "修讀中"]
    csv_bytes = df_full.to_csv(index=False).encode("utf-8")

    html_str = [
        "<div style='display:flex; justify-content:center; width:100%; margin-bottom:18px;'>",
        "<div style='width:100%;'>",
        "<div class='overview-grid'>",
    ]

    for card in cards:
        if card.get("visible", True):
            html_str.append(
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:20px; display:flex; flex-direction:column; justify-content:space-between;'>"
                f"<div style='font-size:15px; font-weight:700; color:#475569; margin-bottom:12px; line-height:1.4;'>{card['title']}</div>"
                f"<div style='font-size:32px; font-weight:800; color:#0f172a; margin-bottom:8px;'>{card['completed']:g} / {card['target']:g}</div>"
                f"<div style='font-size:13px; color:#64748b;'>已得 {card['completed']:g} / 修讀中 {card['ip']:g}</div>"
                f"</div>"
            )

    html_str.append("</div></div></div>")
    st.markdown("".join(html_str), unsafe_allow_html=True)
    st.markdown("<div style='display:flex; justify-content:center; margin-top:16px;'>", unsafe_allow_html=True)
    st.download_button(
        label="📦 全部匯出 CSV",
        data=csv_bytes,
        file_name="UTaipei_Credit_Audit_Overview.csv",
        mime="text/csv",
        use_container_width=False,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_common_and_major_tab(report, major_domain):
    st.markdown("<div class='card-panel'>", unsafe_allow_html=True)
    _render_pe_section(report["pe"])
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='card-panel'>", unsafe_allow_html=True)
    _render_common_compulsory_section(report["common"])
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='card-panel'>", unsafe_allow_html=True)
    _render_major_section_detailed(report["major"], major_domain)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_pe_section(pe_report):
    completed = pe_report["semesters_completed"]
    required = pe_report["semesters_required"]
    status = "✅ 已修滿" if completed >= required else f"已修 {completed} / {required} 學期"
    st.markdown(f"### 🏃 體育課修課追蹤 ({status})")
    course_rows = []
    for c in pe_report["courses"]:
        for sem_label, score in [("第一學期", c["sem1_score"]), ("第二學期", c["sem2_score"])]:
            if score and score != "--":
                status, _ = _status_label(score)
                course_rows.append({"課程": c["name"], "學期": sem_label, "成績": score, "狀態": status})
    if course_rows:
        st.write(
            f"<div class='table-container'>{pd.DataFrame(course_rows).to_html(escape=True, index=False)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.warning("⚠️ 目前無體育課程修課紀錄。")


def _render_common_compulsory_section(common_report):
    st.markdown(
        f"### 📖 一、校共同課程 (已取得 {common_report['compulsory_completed'] + common_report['category_completed'] + common_report['common_elective_completed']:g}/28 學分)"
    )
    st.markdown(
        f"校共同必修 {common_report['compulsory_completed']:g}/10，通識分類選修 {common_report['category_completed']:g}/16，通識共同選修 {common_report['common_elective_completed']:g}/2"
    )
    rows = []
    for c in common_report["compulsory_courses"]:
        rows.append(_course_row(c))
    for missing in common_report["compulsory_missing"]:
        rows.append(
            {
                "科目名稱": missing["name"],
                "修課學年": "--",
                "學分": missing["credit"],
                "成績": "--",
                "狀態": "缺漏",
                "狀態類別": "missing",
            }
        )
    _render_course_cards(rows)
    _render_ge_categories(common_report)
    _render_common_elective_section(common_report)


def _render_ge_categories(common_report, per_category_required=4):
    st.markdown("### 🎨 通識分類選修領域")
    cols = st.columns(2)
    idx = 0
    for category_name, category_data in common_report["categories"].items():
        with cols[idx % 2]:
            status = (
                "✅ 達標"
                if category_data["completed"] >= per_category_required
                else "🔵 修讀中"
                if category_data["completed"] + category_data["ip"] >= per_category_required
                else "⚠️ 未達標"
            )
            color = (
                "#00cd98"
                if category_data["completed"] >= per_category_required
                else "#4facfe"
                if category_data["completed"] + category_data["ip"] >= per_category_required
                else "#ff3860"
            )
            st.markdown(
                f"""
                <div style='background: rgba(30, 41, 85, 0.2); border:1px solid rgba(255,255,255,0.05); border-radius:12px; padding:15px; margin-bottom:15px;'>
                    <div style='display:flex; justify-content:space-between; margin-bottom:10px; font-weight:600;'>
                        <span>{escape(str(category_name))}</span>
                        <span style='color:{color}; white-space:nowrap;'>{status}</span>
                    </div>
                    <div style='font-size:13px; color:#475569; margin-bottom:10px;'>已得: {category_data["completed"]:g} / 修讀中: {category_data["ip"]:g} / 目標: {per_category_required:g} 學分</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        idx += 1


def _render_major_section_detailed(major_report, major_domain):
    st.markdown(f"### 🔬 地生系主修分析 ({major_domain})")
    st.markdown(f"**二、系共同必修 (已取得 {major_report['dept_compulsory_completed']:g}/24 學分)**")
    _render_course_table_with_missing(major_report["dept_compulsory_courses"], major_report["dept_compulsory_missing"])
    st.markdown(f"**三、專業必修 (已取得 {major_report['domain_compulsory_completed']:g}/14 學分)**")
    _render_course_table_with_missing(
        major_report["domain_compulsory_courses"], major_report["domain_compulsory_missing"]
    )
    st.markdown(
        f"**四、專業選修 (已取得 {major_report['domain_elective_completed']:g}/20 學分，修讀中 {major_report['domain_elective_ip']:g} 學分)**"
    )
    _render_course_table(major_report["domain_elective_courses"])
    st.markdown(
        f"**五、其他本系課程 (已取得 {major_report['other_elective_completed']:g}/27 學分，修讀中 {major_report['other_elective_ip']:g} 學分)**"
    )
    _render_course_table(major_report["other_elective_courses"])


def _render_common_section(common_report, pe_report, requirements):
    """展示校共同課程分類詳細"""
    st.markdown("### 一、校共同課程")
    total_completed = (
        common_report["compulsory_completed"]
        + common_report["category_completed"]
        + common_report["common_elective_completed"]
    )
    total_ip = (
        common_report.get("compulsory_ip", 0.0)
        + common_report.get("category_ip", 0.0)
        + common_report.get("common_elective_ip", 0.0)
    )
    draw_premium_progress("校共同課程 (總計)", total_completed, requirements["common_total"], ip=total_ip)
    st.markdown(
        f"校共同必修 {common_report['compulsory_completed']:g}/{requirements['common_compulsory']:g}，"
        f"通識分類選修 {common_report['category_completed']:g}/{requirements['ge_categories_total']:g}，"
        f"通識共同選修 {common_report['common_elective_completed']:g}/{requirements['ge_common_elective']:g}"
    )
    st.markdown("---")

    # 體育課
    st.markdown(f"#### 🏃 體育課 ({requirements['pe_semesters']} 學期)")
    completed = pe_report["semesters_completed"]
    required = pe_report["semesters_required"]
    status = "✅ 已修滿" if completed >= required else f"已修 {completed} / {required} 學期"
    st.markdown(f"**{status}**")

    course_rows = []
    for c in pe_report["courses"]:
        for sem_label, score in [("第一學期", c["sem1_score"]), ("第二學期", c["sem2_score"])]:
            if score and score != "--":
                status_text, _ = _status_label(score)
                course_rows.append({"課程": c["name"], "學期": sem_label, "成績": score, "狀態": status_text})
    if course_rows:
        st.write(
            f"<div class='table-container'>{pd.DataFrame(course_rows).to_html(escape=True, index=False)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.warning("⚠️ 目前無體育課程修課紀錄。")

    # 校共同必修
    st.markdown("#### 📖 校共同必修課程")
    rows = []
    for c in common_report["compulsory_courses"]:
        rows.append(_course_row(c))
    for missing in common_report["compulsory_missing"]:
        rows.append(
            {
                "科目名稱": missing["name"],
                "修課學年": "--",
                "學分": missing["credit"],
                "成績": "--",
                "狀態": "缺漏",
                "狀態類別": "missing",
            }
        )
    if rows:
        _render_course_cards(rows)
    else:
        st.warning("⚠️ 目前無相關修課紀錄。")

    # 通識
    st.markdown(f"#### 🎨 通識分類選修（各領域至少 {requirements['ge_per_category']:g} 學分）")
    _render_ge_categories(common_report, requirements["ge_per_category"])
    _render_common_elective_section(common_report, requirements["ge_common_elective"])


def _render_common_elective_section(common_report, required=2):
    st.markdown(f"#### 🧩 通識共同選修 ({required:g} 學分)")
    st.markdown(
        f"已取得 **{common_report['common_elective_completed']:g} / {required:g}** 學分（修讀中 {common_report['common_elective_ip']:g}）"
    )
    st.markdown("---")
    if common_report["common_elective_courses"]:
        rows = [_course_row(c) for c in common_report["common_elective_courses"]]
        _render_course_cards(rows)
    else:
        st.info("💡 目前無通識共同選修紀錄。")


def _render_dept_compulsory_section(major_report, requirements):
    """展示系共同必修"""
    st.markdown("### 二、系共同必修")
    draw_premium_progress(
        "二、系共同必修",
        major_report["dept_compulsory_completed"],
        requirements["major_common_compulsory"],
        ip=major_report["dept_compulsory_ip"],
    )
    st.markdown("---")

    rows = []
    for c in major_report["dept_compulsory_courses"]:
        rows.append(_course_row(c))
    for missing in major_report["dept_compulsory_missing"]:
        rows.append(
            {
                "科目名稱": missing["name"],
                "修課學年": "--",
                "學分": missing["credit"],
                "成績": "--",
                "狀態": "缺漏",
                "狀態類別": "missing",
            }
        )

    if rows:
        _render_course_cards(rows)
    else:
        st.warning("⚠️ 目前無相關修課紀錄。")

    missing_count = len(major_report["dept_compulsory_missing"])
    if missing_count > 0:
        st.warning(f"⚠️ 您尚有 {missing_count} 門必修課程未修習")


def _render_domain_compulsory_section(major_report, major_domain, requirements):
    """展示專業必修"""
    st.markdown(f"### 三、專業必修 ({major_domain}領域)")
    draw_premium_progress(
        "三、專業必修",
        major_report["domain_compulsory_completed"],
        requirements["domain_compulsory"],
        ip=major_report["domain_compulsory_ip"],
    )
    st.markdown("---")

    rows = []
    for c in major_report["domain_compulsory_courses"]:
        rows.append(_course_row(c))
    for missing in major_report["domain_compulsory_missing"]:
        rows.append(
            {
                "科目名稱": missing["name"],
                "修課學年": "--",
                "學分": missing["credit"],
                "成績": "--",
                "狀態": "缺漏",
                "狀態類別": "missing",
            }
        )

    if rows:
        _render_course_cards(rows)
    else:
        st.warning("⚠️ 目前無相關修課紀錄。")

    missing_count = len(major_report["domain_compulsory_missing"])
    if missing_count > 0:
        st.warning(f"⚠️ 您尚有 {missing_count} 門必修課程未修習")


def _render_domain_elective_section(major_report, major_domain, requirements):
    """展示專業選修"""
    st.markdown(f"### 四、專業選修 ({major_domain}領域)")
    draw_premium_progress(
        "四、專業選修",
        major_report["domain_elective_completed"],
        requirements["domain_elective"],
        ip=major_report["domain_elective_ip"],
    )
    st.markdown("---")

    if major_report["domain_elective_courses"]:
        rows = [_course_row(c) for c in major_report["domain_elective_courses"]]
        _render_course_cards(rows)
    else:
        st.info("💡 目前無相關修課紀錄。")


def _render_other_elective_section(major_report, requirements):
    """展示其他本系課程"""
    st.markdown("### 五、其他本系課程")
    draw_premium_progress(
        "五、其他本系課程",
        major_report["other_elective_completed"],
        requirements["major_other_elective"],
        ip=major_report["other_elective_ip"],
    )
    st.markdown("---")

    if major_report["other_elective_courses"]:
        rows = [_course_row(c) for c in major_report["other_elective_courses"]]
        _render_course_cards(rows)
    else:
        st.info("💡 目前無相關修課紀錄。")


def _render_free_elective_section(free_report, requirements):
    """展示自由選修"""
    st.markdown("### 六、自由選修")
    draw_premium_progress("六、自由選修", free_report["completed"], requirements["free_elective"], ip=free_report["ip"])
    st.markdown("---")

    if free_report["courses"]:
        rows = [_course_row(c) for c in free_report["courses"]]
        _render_course_cards(rows)
    else:
        st.info("💡 目前無相關修課紀錄。")


def _render_target_tab(report, program_type, target_dept, summary):
    if program_type == "單主修":
        st.info("💡 目前為「單主修」身分，無輔系/雙主修學分計算。")
        return

    st.markdown(f"### 🧪 雙主修：{target_dept} ({program_type})")
    target_req = report["requirements"]["target_total"]
    draw_premium_progress(
        f"🧪 {program_type} ({target_dept})", summary["target_completed"], target_req, ip=summary["target_ip"]
    )
    st.markdown("---")

    if "物化系" in target_dept:
        st.markdown("#### 🅰️ 物化系共同基礎必修")
        _render_course_table_with_missing(
            report["target"]["basic_core_courses"], report["target"]["basic_core_missing"]
        )
        st.markdown("#### 🅱️ 物化系分組專業必修")
        _render_course_table(report["target"]["compulsory_courses"])
        st.markdown("#### 🅲 物化系其他選修")
        _render_course_table(report["target"]["elective_courses"])
    else:
        st.markdown("#### 🅰️ 資科系指定必修")
        _render_course_table_with_missing(
            report["target"]["compulsory_courses"], report["target"]["compulsory_missing"]
        )
        st.markdown("#### 🅱️ 資科系其他選修")
        _render_course_table(report["target"]["elective_courses"])


def _render_export_tab(courses, report, summary, requirements):
    st.markdown(
        f"### 📦 六、自由選修 與 全部匯出 (已取得 {report['free']['completed']:g}/{requirements['free_elective']:g} 學分)"
    )
    st.info("下方為歷年修課總表，您可匯出 CSV 供備查或核對。")
    df_full = pd.DataFrame(courses)[["name", "type", "academic_year", "total_credit", "is_completed", "is_in_progress"]]
    categories = [_get_course_category(c, report) for c in courses]
    df_full.insert(1, "category", categories)
    df_full.columns = ["科目名稱", "系統分類", "科目屬性", "修課學年", "學分數", "是否完成", "修讀中"]
    st.dataframe(df_full, use_container_width=True)
    csv_bytes = df_full.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 匯出學分審查試算表 (CSV)",
        data=csv_bytes,
        file_name="UTaipei_Credit_Audit.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # 額外匯出：通識分類明細與通識超額清單
    # Build GE category detail CSV
    ge_rows = []
    for cat_name, cat in report["common"]["categories"].items():
        for c in cat["courses"]:
            ge_rows.append(
                {
                    "分類": cat_name,
                    "科目名稱": c.get("name"),
                    "原始名稱": c.get("raw_name"),
                    "學分": c.get("total_credit", 0.0),
                    "已得學分": c.get("completed_credit", 0.0),
                    "修讀中": c.get("is_in_progress", False),
                }
            )
    ge_df = pd.DataFrame(ge_rows)
    ge_csv = ge_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 匯出：通識分類明細 (CSV)",
        data=ge_csv,
        file_name="UTaipei_GE_Category_Details.csv",
        mime="text/csv",
        use_container_width=False,
    )

    # Overflow CSV
    overflow_rows = []
    overflow = report["common"].get("category_overflow", {})
    for cat_name, items in overflow.items():
        for c in items:
            overflow_rows.append(
                {
                    "分類": cat_name,
                    "科目名稱": c.get("name"),
                    "原始名稱": c.get("raw_name"),
                    "學分": c.get("total_credit", 0.0),
                    "已得學分": c.get("completed_credit", 0.0),
                }
            )
    if overflow_rows:
        overflow_df = pd.DataFrame(overflow_rows)
        overflow_csv = overflow_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 匯出：通識超額清單 (CSV)",
            data=overflow_csv,
            file_name="UTaipei_GE_Overflow.csv",
            mime="text/csv",
            use_container_width=False,
        )


def _render_parsed_course_totals(courses, summary, program_type):
    # 計算解析出的課程學分總和，協助偵錯
    parsed_total = sum(float(c.get("total_credit", 0.0) or 0.0) for c in courses)
    parsed_completed = sum(float(c.get("completed_credit", 0.0) or 0.0) for c in courses)
    parsed_ip = sum(
        (float(c.get("total_credit", 0.0) or 0.0) - float(c.get("completed_credit", 0.0) or 0.0))
        if c.get("is_in_progress")
        else 0.0
        for c in courses
    )

    st.markdown(
        f"""
        <div style='display:flex; flex-wrap:wrap; gap:12px; margin-bottom:12px;'>
            <div style='flex: 1 1 120px; background:#ffffff; padding:12px; border-radius:10px; border:1px solid rgba(0,0,0,0.06);'>解析總學分: <b>{parsed_total:g}</b></div>
            <div style='flex: 1 1 120px; background:#ffffff; padding:12px; border-radius:10px; border:1px solid rgba(0,0,0,0.06);'>已修得: <b>{parsed_completed:g}</b></div>
            <div style='flex: 1 1 120px; background:#ffffff; padding:12px; border-radius:10px; border:1px solid rgba(0,0,0,0.06);'>修讀中: <b>{parsed_ip:g}</b></div>
            <div style='flex: 1 1 120px; background:#ffffff; padding:12px; border-radius:10px; border:1px solid rgba(0,0,0,0.06);'>總含修讀中: <b>{summary.get("total_with_ip", 0.0):g}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_course_table(courses):
    if not courses:
        st.warning("⚠️ 目前無相關修課紀錄。")
        return
    rows = [_course_row(c) for c in courses]
    _render_course_cards(rows)


def _render_course_table_with_missing(courses, missing_items):
    rows = [_course_row(c) for c in courses]
    rows.extend(
        {
            "科目名稱": item["name"],
            "修課學年": "--",
            "學分": item["credit"],
            "成績": "--",
            "狀態": "缺漏",
            "狀態類別": "missing",
        }
        for item in missing_items
    )
    if rows:
        _render_course_cards(rows)
    else:
        st.warning("⚠️ 目前無相關修課紀錄。")


def _render_course_cards(rows):
    if not rows:
        st.warning("⚠️ 目前無相關修課紀錄。")
        return
    html = [
        "<div style='display:grid; gap:12px;'>",
        "<div class='course-header'>",
        "<div>科目名稱</div>",
        "<div>修課學年</div>",
        "<div>學分</div>",
        "<div>成績</div>",
        "<div>狀態</div>",
        "</div>",
    ]

    for r in rows:
        status = r.get("狀態", "")
        status_type = r.get("狀態類別", "")
        if not status_type:
            if status == "已修畢":
                status_type = "completed"
            elif status == "在修中":
                status_type = "ip"
            elif status in ["缺漏", "未通過"]:
                status_type = "missing"
            else:
                status_type = "completed"
        if status_type == "completed":
            bg = "rgba(16, 185, 129, 0.12)"
            color = "#0f766e"
            border = "rgba(16, 185, 129, 0.24)"
        elif status_type == "ip":
            bg = "rgba(59, 130, 246, 0.12)"
            color = "#1d4ed8"
            border = "rgba(59, 130, 246, 0.24)"
        else:
            bg = "rgba(249, 115, 22, 0.12)"
            color = "#c2410c"
            border = "rgba(249, 115, 22, 0.24)"

        safe_name = escape(str(r.get("科目名稱", "")))
        safe_year = escape(str(r.get("修課學年", "")))
        safe_credit = escape(str(r.get("學分", "")))
        safe_score = escape(str(r.get("成績", "")))
        safe_status = escape(str(status))
        html.append(
            f"<div class='course-row'>"
            f"<div class='course-name-col' data-label='科目名稱'>{safe_name}</div>"
            f"<div data-label='修課學年' style='color:#334155;'>{safe_year}</div>"
            f"<div data-label='學分' style='color:#334155;'>{safe_credit}</div>"
            f"<div data-label='成績' style='color:#334155;'>{safe_score}</div>"
            f"<div class='course-status-col' data-label='狀態'><span style='display:inline-flex; align-items:center; justify-content:center; padding:8px 14px; border-radius:999px; background:{bg}; color:{color}; border:1px solid {border}; font-size:12px; font-weight:700;'>{safe_status}</span></div>"
            f"</div>"
        )

    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _course_row(c):
    score = c["sem1_score"] if c["sem1_score"] not in (None, "", "--") else c["sem2_score"]
    status, status_type = _status_label(score)
    return {
        "科目名稱": c["name"],
        "修課學年": f"{c['academic_year']}學年",
        "學分": c["total_credit"],
        "成績": score,
        "狀態": status,
        "狀態類別": status_type,
    }


def _status_label(score):
    if not score or score == "--":
        return "缺漏", "missing"
    if score == "未":
        return "在修中", "ip"
    if score in ["F", "停", "W"]:
        return "未通過", "missing"
    try:
        val = float(score)
        if val < 60:
            return "未通過", "missing"
    except ValueError:
        pass
    return "已修畢", "completed"
