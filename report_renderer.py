"""
Report rendering utilities for the UTaipei graduation credit dashboard.
"""

import re
from html import escape

import pandas as pd
import streamlit as st

from audit_export import audit_csv_bytes, audit_json_bytes, dataframe_csv_bytes
from handbook_rules import normalize_course_name
from input_confirmation import mask_person_name, mask_student_id
from lieflat_progress_chart import render_progress_chart
from policy_audit import UNKNOWN
from ui_components import draw_premium_progress, format_credit

_STATUS_LABELS = {
    "SATISFIED": "已滿足",
    "NOT_SATISFIED": "未滿足",
    "UNKNOWN": "需人工確認",
    "NOT_APPLICABLE": "不適用",
    "COMPLETED": "已完成",
    "INCOMPLETE": "未完成",
}

_IDENTITY_STATUS_LABELS = {
    "VERIFIED": "身分已核對",
    "CONFLICTED": "身分衝突",
    "UNKNOWN": "身分待確認（暫列）",
    "MANUAL_APPROVED": "人工核准身分",
}

_SHARED_REUSE_FALLBACK_NOTE = (
    "共同修課核准僅代表合計額度；列出的課名只是規劃用模擬配置，不代表系所已核准該課程身分。"
    "正式共同修課科目身分須由系所證據確認。"
)


def _status_display(status):
    return _STATUS_LABELS.get(str(status or "UNKNOWN"), "需人工確認")


def _shared_reuse_note(shared_reuse):
    """Return the explicit disclaimer for reporting-only shared-credit rows."""

    if isinstance(shared_reuse, dict):
        note = str(shared_reuse.get("official_course_identity_note") or "").strip()
        if note:
            return note
    return _SHARED_REUSE_FALLBACK_NOTE


def render_report(student_info, courses, report, major_domain, program_type, target_dept, source_label):
    summary = report["summary"]
    requirements = report["requirements"]
    rules_meta = report.get("rules_meta", {})
    handbook_year = str(report.get("handbook_year") or rules_meta.get("version") or "未辨識")
    safe_source = escape(str(source_label or "未知來源"))
    safe_name = escape(mask_person_name(student_info.get("name")))
    safe_student_id = escape(mask_student_id(student_info.get("student_id")))
    safe_handbook = escape(handbook_year)
    safe_rule_source = escape(str(rules_meta.get("evidence_file") or rules_meta.get("source_file") or "未標示"))
    mode_tag = f"<span class='source-badge'>{safe_handbook} 學年度手冊</span>"
    evidence_states = report.get("evidence_states") or report.get("primary_plan", {}).get("evidence_states", {})
    evidence_labels = {
        "VERIFIED": "已核對",
        "INCOMPLETE": "尚未完整",
        "CONFLICTED": "有矛盾",
        "MANUAL_REVIEW": "需人工確認",
    }
    evidence_text = "／".join(
        f"{label}：{evidence_labels.get(str(evidence_states.get(key)), str(evidence_states.get(key)))}"
        for key, label in (("threshold", "門檻"), ("course_catalog", "課程表"), ("eligibility", "資格"))
        if evidence_states.get(key)
    )

    st.markdown(
        f"""
        <div class="info-flex">
            <section class="info-card" aria-label="學生資訊">
                <div class="eyebrow">學生資訊</div>
                <div class="meta-value info-value">
                    姓名：<strong>{safe_name}</strong><br>
                    學號：<strong>{safe_student_id}</strong><br>
                    系所：<strong>{escape(str(student_info.get("department") or "未辨識"))}</strong><br>
                    入學年月：<strong>{escape(str(student_info.get("admission_year") or "未辨識"))}</strong><br>
                    列印日期：<strong>{escape(str(student_info.get("print_date") or "未辨識"))}</strong>
                </div>
            </section>
            <section class="info-card info-card-highlight" aria-label="審查依據">
                <div class="eyebrow">審查依據</div>
                <div class="meta-value info-source">{mode_tag}</div>
                <div class="meta-label info-note">手冊來源：{safe_rule_source}<br>成績來源：{safe_source}<br>已分析 {len(courses)} 筆修課紀錄。<br>{escape(evidence_text)}</div>
            </section>
        </div>
        """,
        unsafe_allow_html=True,
    )

    admission_year = str(student_info.get("admission_year") or "")
    admission_match = re.search(r"(?<!\d)(1\d{2})(?!\d)", admission_year)
    if admission_match and admission_match.group(1) != handbook_year:
        st.warning(
            f"成績單辨識到的入學年度為 {admission_match.group(1)}，目前選的是 {handbook_year} 學年度手冊。"
            "請確認校方規定的實際適用版本；系統不會擅自替你切換。"
        )

    for warning in report.get("document_warnings", []):
        st.warning(f"手冊核對提醒：{warning}")
    for warning in report.get("policy_warnings", []):
        st.warning(f"政策／證據提醒：{warning}")

    identity_gate = report.get("identity_gate", {})
    if isinstance(identity_gate, dict) and identity_gate.get("status") in {"UNKNOWN", "CONFLICTED"}:
        reasons = identity_gate.get("reasons", [])
        reason_text = "；".join(str(reason) for reason in reasons if reason)
        st.warning(
            "課程身分稽核提醒："
            + (reason_text or "部分系所課程缺少可核對的開課身分，暫不能作為最終畢業判定。")
        )

    diagnostics = student_info.get("parse_diagnostics", {}) if isinstance(student_info, dict) else {}
    if diagnostics and diagnostics.get("complete") is False:
        for warning in diagnostics.get("warnings", []):
            st.warning(f"解析完整性提醒：{warning}")

    if not report.get("detailed", True):
        _render_policy_plan_report(student_info, report, program_type, target_dept)
        return

    _render_parsed_course_totals(courses, report["summary"], program_type)
    _render_outcome_headline(report["summary"].get("graduation_status"))
    _render_metric_cards(summary, report, major_domain, program_type, target_dept, requirements)
    _render_lieflat_threshold_progress(
        summary,
        program_type,
        requirements,
        rules_meta,
        courses=courses,
        report=report,
    )
    st.markdown("<div class='section-gap section-gap-compact'></div>", unsafe_allow_html=True)
    _render_report_sections(courses, report, summary, major_domain, program_type, target_dept, requirements)


def _render_outcome_headline(status):
    status = status or UNKNOWN
    label = _status_display(status)
    outcome_class = {
        "SATISFIED": "outcome-satisfied",
        "NOT_SATISFIED": "outcome-not-satisfied",
        "UNKNOWN": "outcome-unknown",
    }.get(status, "outcome-unknown")
    st.markdown(
        f"<div class='outcome-banner {outcome_class}' role='status'>審查結果：{escape(label)}</div>",
        unsafe_allow_html=True,
    )


def _render_policy_plan_report(student_info, report, program_type, target_dept):
    """Render threshold-only planning for programs without safe course tables."""

    status = report.get("summary", {}).get("graduation_status", UNKNOWN)
    _render_outcome_headline(status)
    plan = report.get("primary_plan", {})
    st.markdown("### 📋 已核對的門檻規劃")
    st.info("目前僅顯示官方門檻總額；成績單尚未提供可安全逐課分類的課號／開課系所資料，系統不猜測課程身份。")
    evidence_states = plan.get("evidence_states", plan.get("evidence", {}))
    evidence_labels = {
        "VERIFIED": "已核對",
        "INCOMPLETE": "尚未完整",
        "CONFLICTED": "有矛盾",
        "MANUAL_REVIEW": "需人工確認",
    }
    if evidence_states:
        st.caption(
            "證據狀態："
            + "／".join(
                f"{key}={evidence_labels.get(str(value), value)}" for key, value in evidence_states.items()
            )
        )
    rows = []
    for item in plan.get("breakdown", []):
        required = float(item.get("required", 0.0) or 0.0)
        rows.append({"項目": item.get("label", ""), "官方要求": required, "已核對": 0.0, "差額": required, "狀態": _status_display("UNKNOWN")})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if report.get("target_plan"):
        target = report["target_plan"]
        st.markdown(f"### 🧪 雙主修目標：{target.get('program', '')} {target.get('track') or ''}")
        st.dataframe(
            pd.DataFrame(
                [
                    {"項目": "目標雙主修總額", "官方要求": target.get("total_required", 40), "已核對": 0.0, "差額": target.get("total_required", 40), "狀態": _status_display(UNKNOWN)},
                    {"項目": "基礎／共同結構", "官方要求": target.get("base_required", 0), "已核對": 0.0, "差額": target.get("base_required", 0), "狀態": _status_display(target.get("status", UNKNOWN))},
                    {"項目": "其餘必修／選修結構", "官方要求": target.get("other_required", 0), "已核對": 0.0, "差額": target.get("other_required", 0), "狀態": _status_display(target.get("status", UNKNOWN))},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    eligibility = report.get("double_major_eligibility")
    if eligibility:
        st.markdown("### 🧾 雙主修申請資格")
        st.markdown(f"**{_status_display(eligibility.get('status', UNKNOWN))}**")
        for reason in eligibility.get("reasons", []):
            st.caption(f"• {reason}")
        shared_evidence = eligibility.get("shared_evidence", {})
        if shared_evidence:
            st.caption(f"共同修課證據：{shared_evidence.get('state', '未回答')}（共享額度另列稽核，不增加原始學分）")
            st.warning(_shared_reuse_note(report.get("shared_reuse", {})))
    for warning in report.get("policy_warnings", []):
        st.warning(f"下一步：{warning}")
    st.markdown("### 🔎 來源與人工確認")
    citations = report.get("citations", [])
    if citations:
        for citation in citations:
            if isinstance(citation, dict):
                st.caption(f"{citation.get('label', '來源')}｜{citation.get('file', '')} {citation.get('pages', '')} {citation.get('url', '')}".strip())
            else:
                st.caption(str(citation))
    else:
        st.caption("尚無可列示的來源引用。")
    audit = {
        "cohort": report.get("handbook_year", ""),
        "primary_program": plan.get("primary_program", plan.get("program", "")),
        "track": plan.get("track", ""),
        "program_type": program_type,
        "eligibility": eligibility or {"status": status},
        "status": status,
        "requirements": report.get("requirements", {}),
        "gate_results": report.get("graduation_gates", {}),
        "manual_gates": report.get("manual_gates", {}),
        "warnings": report.get("policy_warnings", []),
        "citations": citations,
        "report": report,
    }
    col_csv, col_json = st.columns(2)
    with col_csv:
        st.download_button("📥 匯出政策稽核 CSV", data=audit_csv_bytes(audit), file_name="UTaipei_policy_audit.csv", mime="text/csv", use_container_width=True)
    with col_json:
        st.download_button("📥 匯出政策稽核 JSON", data=audit_json_bytes(audit), file_name="UTaipei_policy_audit.json", mime="application/json", use_container_width=True)


def _render_metric_cards(summary, report, major_domain, program_type, target_dept, requirements):
    labels = [
        ("🎓 實得總學分", summary["total_completed"], requirements["total"], summary["total_ip"]),
        ("🏫 校共同+通識", summary["common_completed"], requirements["common_total"], summary["common_ip"]),
        ("🔬 主修系專門學分", summary["major_completed"], requirements["major_total"], summary["major_ip"]),
        ("🔓 自由選修學分", summary["free_completed"], requirements["free_elective"], summary["free_ip"]),
        ("✨ 跨系所學分", summary["target_completed"], requirements["target_total"], summary["target_ip"]),
        (
            "🎽 體育修課",
            report["pe"]["semesters_completed"],
            report["pe"]["semesters_required"],
            report["pe"]["semesters_ip"],
        ),
    ]

    html_str = ["<section class='metric-grid' aria-label='學分統計'>"]

    for idx, (label, completed, target, ip) in enumerate(labels):
        if label == "✨ 跨系所學分" and program_type == "單主修":
            html_str.append(
                "<div class='metric-card metric-card--muted'>"
                "<div class='metric-label'>🚫 無跨系修讀</div>"
                "<div class='metric-value'>N/A</div>"
                "<div class='metric-meta'>目前為單主修身份</div>"
                "</div>"
            )
            continue

        total_with_ip = summary.get("total_with_ip", completed + ip) if idx == 0 else completed
        if label == "🎽 體育修課":
            value_text = f"{total_with_ip:g}"
            bottom_text = f"應修 {target:g} 學期 / 修讀中 {ip:g}"
        else:
            value_text = format_credit(total_with_ip)
            bottom_text = (
                f"已得 {format_credit(completed)} / 修讀中 {format_credit(ip)} / 應修 {format_credit(target)}"
                if idx == 0
                else f"應修 {format_credit(target)} / 修讀中 {format_credit(ip)}"
            )

        html_str.append(
            f"<div class='metric-card'>"
            f"<div class='metric-label'>{escape(label)}</div>"
            f"<div class='metric-value'>{escape(value_text)}</div>"
            f"<div class='metric-meta'>{escape(bottom_text)}</div>"
            f"</div>"
        )

    # 審查結果卡片：UNKNOWN 不得顯示成已達標或單純未達標。
    outcome = summary.get("graduation_status", "SATISFIED" if summary.get("graduation_ready") else "NOT_SATISFIED")
    outcome_label = {
        "SATISFIED": "🎉 已滿足",
        "NOT_SATISFIED": "⚠️ 未滿足",
        "UNKNOWN": "❔ 需人工確認",
    }.get(outcome, "❔ 需人工確認")
    outcome_class = {
        "SATISFIED": "outcome-satisfied",
        "NOT_SATISFIED": "outcome-not-satisfied",
        "UNKNOWN": "outcome-unknown",
    }.get(outcome, "outcome-unknown")

    html_str.append(
        f"<div class='metric-card {outcome_class}' role='status'>"
        f"<div class='metric-label'>✨ 審查結果</div>"
        f"<div class='metric-value'>{escape(outcome_label)}</div>"
        f"<div class='metric-meta'>含通識／體育／系專／雙主修</div>"
        f"</div>"
    )

    html_str.append("</section>")
    st.markdown("".join(html_str), unsafe_allow_html=True)


def _render_report_sections(courses, report, summary, major_domain, program_type, target_dept, requirements):
    st.markdown("### 🎯 畢業進度總覽")

    major_target = requirements["total"]
    target_req = requirements["target_total"]
    target_completed = summary["target_completed"]
    target_ip = summary["target_ip"]

    total_completed_all = summary["total_completed"]
    total_ip_all = summary["total_ip"]

    draw_premium_progress("🏆 畢業總學分進度", total_completed_all, major_target, ip=total_ip_all)

    if program_type != "單主修":
        st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
        draw_premium_progress(f"🧪 {program_type} ({target_dept})", target_completed, target_req, ip=target_ip)

    st.markdown("---")

    section_labels = {
        "overview": "📊 學分進度概覽",
        "common": "一、校共同課程",
        "dept_required": "二、系共同必修",
        "domain_required": "三、專業必修",
        "domain_elective": "四、專業選修",
        "other_elective": "五、其他本系課程",
        "free_elective": "六、自由選修",
        "target": f"🧪 {program_type}",
        "export": "📦 全部匯出",
    }
    selected_section = st.selectbox(
        "📂 查看詳細分類與工具",
        options=list(section_labels),
        format_func=section_labels.get,
        key="report_section_selector",
        help="共 9 個區塊。改用下拉導覽可避免較窄的畫面把後段分頁裁掉。",
    )
    st.caption(f"共 {len(section_labels)} 個區塊｜目前顯示：{section_labels[selected_section]}")

    if selected_section == "overview":
        _render_overview_tab(courses, summary, report, major_domain, program_type, target_dept, requirements)
    elif selected_section == "common":
        _render_common_section(report["common"], report["pe"], requirements)
    elif selected_section == "dept_required":
        _render_dept_compulsory_section(report["major"], requirements)
    elif selected_section == "domain_required":
        _render_domain_compulsory_section(report["major"], major_domain, requirements)
    elif selected_section == "domain_elective":
        _render_domain_elective_section(report["major"], major_domain, requirements)
    elif selected_section == "other_elective":
        _render_other_elective_section(report["major"], requirements)
    elif selected_section == "free_elective":
        _render_free_elective_section(report["free"], requirements)
    elif selected_section == "target":
        _render_target_tab(report, program_type, target_dept, summary)
    elif selected_section == "export":
        _render_export_tab(courses, report, summary, requirements)


def _render_overview_tab(courses, summary, report, major_domain, program_type, target_dept, requirements):
    st.markdown("### 📊 畢業學分進度總覽")
    _render_overview_progress_cards(courses, summary, report, program_type, target_dept, requirements)
    _render_subject_detail_expanders(courses, report, summary, requirements, program_type, target_dept)
    st.markdown("---")

    missing = []
    for item in report["common"]["compulsory_missing"]:
        missing.append({"類別": "校共同必修", "科目名稱": item["name"], "學分": item["credit"]})
    for item in report["major"]["dept_compulsory_missing"]:
        missing.append({"類別": "地生系共同必修", "科目名稱": item["name"], "學分": item["credit"]})
    for item in report["major"]["domain_compulsory_missing"]:
        missing.append({"類別": f"{major_domain}領域必修", "科目名稱": item["name"], "學分": item["credit"]})
    if program_type != "單主修":
        for item in report["target"].get("basic_core_missing", []):
            missing.append({"類別": f"{target_dept}{program_type}基礎", "科目名稱": item["name"], "學分": item["credit"]})
        for item in report["target"].get("compulsory_missing", []):
            missing.append({"類別": f"{target_dept}{program_type}", "科目名稱": item["name"], "學分": item["credit"]})
        for item in report["target"].get("elective_missing", []):
            missing.append({"類別": f"{target_dept}{program_type}", "科目名稱": item["name"], "學分": item["credit"]})

    if missing:
        st.warning("⚠️ 您目前尚有以下核心必修科目未修畢：")
        st.dataframe(pd.DataFrame(missing), use_container_width=True)
    else:
        st.success("🎓 您已完成所有主修及共同必修科目。")


def _missing_course_row(item):
    """Convert a requirement placeholder to the shared responsive row shape."""

    return {
        "科目名稱": item.get("name", "待補足課程"),
        "修課學年": "--",
        "學分": item.get("credit", item.get("credits", 0.0)),
        "成績": "--",
        "狀態": "缺漏" if item.get("status") != "in_progress" else "在修中",
        "狀態類別": "missing" if item.get("status") != "in_progress" else "ip",
        "配置備註": item.get("allocation_note", ""),
    }


def _render_subject_detail_expanders(courses, report, summary, requirements, program_type, target_dept):
    """Render touch-friendly drill-downs for every overview credit subtotal.

    The six main buckets (plus each general-education category and any
    double-major buckets) remain compact until opened.  This keeps the mobile
    overview scannable while making the exact completed/in-progress/missing
    course composition directly discoverable.
    """

    common = report.get("common", {})
    major = report.get("major", {})
    target = report.get("target", {})
    free = report.get("free", {})
    groups = [
        (
            "校共同課程",
            common.get("compulsory_courses", [])
            + [course for category in common.get("categories", {}).values() for course in category.get("courses", [])]
            + common.get("common_elective_courses", []),
            common.get("compulsory_missing", []),
            common.get("compulsory_completed", 0.0)
            + common.get("category_completed", 0.0)
            + common.get("common_elective_completed", 0.0),
            common.get("compulsory_ip", 0.0)
            + common.get("category_ip", 0.0)
            + common.get("common_elective_ip", 0.0),
            requirements.get("common_total", 0.0),
        ),
        (
            "系共同必修",
            major.get("dept_compulsory_courses", []),
            major.get("dept_compulsory_missing", []),
            major.get("dept_compulsory_completed", 0.0),
            major.get("dept_compulsory_ip", 0.0),
            requirements.get("major_common_compulsory", 0.0),
        ),
        (
            "專業必修",
            major.get("domain_compulsory_courses", []),
            major.get("domain_compulsory_missing", []),
            major.get("domain_compulsory_completed", 0.0),
            major.get("domain_compulsory_ip", 0.0),
            requirements.get("domain_compulsory", 0.0),
        ),
        (
            "專業選修",
            major.get("domain_elective_courses", []),
            [],
            major.get("domain_elective_completed", 0.0),
            major.get("domain_elective_ip", 0.0),
            requirements.get("domain_elective", 0.0),
        ),
        (
            "其他本系課程",
            major.get("other_elective_courses", []),
            [],
            major.get("other_elective_completed", 0.0),
            major.get("other_elective_ip", 0.0),
            requirements.get("major_other_elective", 0.0),
        ),
        (
            "自由選修",
            free.get("courses", []),
            [],
            free.get("completed", summary.get("free_completed", 0.0)),
            free.get("ip", summary.get("free_ip", 0.0)),
            requirements.get("free_elective", 0.0),
        ),
    ]

    for category_name, category_data in common.get("categories", {}).items():
        required = requirements.get("ge_per_category", 4.0)
        completed = category_data.get("completed", 0.0)
        in_progress = category_data.get("ip", 0.0)
        missing = []
        shortfall = max(float(required) - float(completed) - float(in_progress), 0.0)
        if shortfall > 0:
            missing.append({"name": f"{category_name}分類尚缺學分（請依手冊選課）", "credit": shortfall})
        groups.append((f"通識分類｜{category_name}", category_data.get("courses", []), missing, completed, in_progress, required))

    if program_type != "單主修":
        target_plan = report.get("target_requirements") or {}
        if not target_plan:
            target_plan = (report.get("target_plan") or {}).get("target_requirements") or report.get("target_plan") or {}

        def target_bucket_required(bucket, explicit_key=None):
            explicit = target_plan.get(explicit_key, None) if explicit_key else None
            if explicit is not None:
                return float(explicit or 0.0)
            bucket_completed = float(target.get(f"{bucket}_completed", 0.0) or 0.0)
            bucket_ip = float(target.get(f"{bucket}_ip", 0.0) or 0.0)
            bucket_missing = sum(float(item.get("credit", 0.0) or 0.0) for item in target.get(f"{bucket}_missing", []))
            return bucket_completed + bucket_ip + bucket_missing

        target_is_apc = "物化" in str(target_dept or "")
        if target_is_apc:
            target_base_required = target_bucket_required("basic_core", "base_required")
            # APC places its remaining quota in ``compulsory_courses``.
            target_other_required = target_bucket_required("compulsory", "other_required")
            target_elective_required = target_bucket_required("elective")
        else:
            # The CS/other policy plan calls its 15-credit required block
            # ``base_required`` and its 25-credit pool ``other_required``;
            # those map to the report's compulsory/elective buckets.  There is
            # no separate basic-core row to display for these targets.
            target_base_required = target_bucket_required("basic_core")
            target_other_required = float(target_plan.get("base_required", 0.0) or 0.0) or target_bucket_required("compulsory")
            target_elective_required = float(target_plan.get("other_required", 0.0) or 0.0) or target_bucket_required("elective")
        target_groups = [
            (
                f"{target_dept}基礎／共同必修",
                target.get("basic_core_courses", []),
                target.get("basic_core_missing", []),
                target.get("basic_core_completed", 0.0),
                target.get("basic_core_ip", 0.0),
                target_base_required,
            ),
            (
                f"{target_dept}指定／專業必修",
                target.get("compulsory_courses", []),
                target.get("compulsory_missing", []),
                target.get("compulsory_completed", 0.0),
                target.get("compulsory_ip", 0.0),
                target_other_required,
            ),
            (
                f"{target_dept}專業選修",
                target.get("elective_courses", []),
                target.get("elective_missing", []),
                target.get("elective_completed", 0.0),
                target.get("elective_ip", 0.0),
                target_elective_required,
            ),
        ]
        groups.extend(
            group
            for group in target_groups
            if group[1] or group[2]
        )

    st.markdown("#### 🔎 點開查看每個學分小計的科目組成")
    st.caption("每個區塊會列出已完成、修讀中、缺漏，以及課程被配置到哪個畢業欄位。")
    for index, (label, item_courses, missing_items, completed, in_progress, required) in enumerate(groups):
        title = f"{label}｜已得 {format_credit(completed)}／{format_credit(required)} 學分"
        if in_progress:
            title += f"（修讀中 {format_credit(in_progress)}）"
        with st.expander(title, expanded=False):
            if item_courses:
                st.caption(f"已完成／修讀中課程：{len(item_courses)} 門")
                _render_course_cards([_course_row(course, allocation_context=label) for course in item_courses])
            if missing_items:
                st.caption(f"缺漏／待補足：{len(missing_items)} 項")
                _render_course_cards([_missing_course_row(item) for item in missing_items])
            if not item_courses and not missing_items:
                st.info("目前沒有可列出的課程或缺漏項目。")


def _get_course_category(c, report):
    c_idx = id(c)

    def stable_id(course):
        try:
            total_credit = round(float(course.get("total_credit") or 0.0), 6)
        except (TypeError, ValueError):
            total_credit = 0.0
        return (
            normalize_course_name(course.get("name", "") or ""),
            total_credit,
            str(course.get("academic_year", "") or ""),
            str(course.get("semester", "") or ""),
            str(course.get("sem1_credit", "") or ""),
            str(course.get("sem1_score", "") or ""),
            str(course.get("sem2_credit", "") or ""),
            str(course.get("sem2_score", "") or ""),
        )

    source_stable_id = stable_id(c)

    def is_same_course(report_course):
        return (
            id(report_course) == c_idx
            or report_course.get("_origin_id") == c_idx
            or report_course.get("_origin_id") == source_stable_id
        )

    for rc in report.get("common", {}).get("compulsory_courses", []):
        if is_same_course(rc):
            return "校共同必修"
    for rc in report.get("common", {}).get("common_elective_courses", []):
        if is_same_course(rc):
            return "通識共同選修"
    for cat_name, cat_data in report.get("common", {}).get("categories", {}).items():
        for rc in cat_data.get("courses", []):
            if is_same_course(rc):
                return f"通識分類({cat_name})"
    for rc in report.get("major", {}).get("dept_compulsory_courses", []):
        if is_same_course(rc):
            return "系共同必修"
    for rc in report.get("major", {}).get("domain_compulsory_courses", []):
        if is_same_course(rc):
            return "專業必修"
    for rc in report.get("major", {}).get("domain_elective_courses", []):
        if is_same_course(rc):
            return "專業選修"
    for rc in report.get("major", {}).get("other_elective_courses", []):
        if is_same_course(rc):
            return "其他本系課程"
    for rc in report.get("target", {}).get("basic_core_courses", []):
        if is_same_course(rc):
            return "跨系基礎必修"
    for rc in report.get("target", {}).get("compulsory_courses", []):
        if is_same_course(rc):
            return "跨系專業必修（超額學分另轉自由選修）" if rc.get("allocation_note") else "跨系專業必修"
    for rc in report.get("target", {}).get("elective_courses", []):
        if is_same_course(rc):
            return "跨系選修（超額學分另轉自由選修）" if rc.get("allocation_note") else "跨系選修"
    for rc in report.get("pe", {}).get("courses", []):
        if is_same_course(rc):
            return "體育"
    for rc in report.get("free", {}).get("courses", []):
        if is_same_course(rc):
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

    df_full = pd.DataFrame(courses).reindex(
        columns=["name", "type", "academic_year", "total_credit", "is_completed", "is_in_progress"]
    )
    categories = [_get_course_category(c, report) for c in courses]
    df_full.insert(1, "category", categories)
    df_full.insert(0, "handbook_year", report.get("handbook_year", ""))
    df_full.columns = ["審查手冊學年度", "科目名稱", "系統分類", "科目屬性", "修課學年", "學分數", "是否完成", "修讀中"]

    html_str = ["<section class='overview-grid' aria-label='分類學分統計'>"]

    for card in cards:
        if card.get("visible", True):
            html_str.append(
                f"<div class='metric-card'>"
                f"<div class='metric-label'>{escape(card['title'])}</div>"
                f"<div class='metric-value'>{format_credit(card['completed'])} / {format_credit(card['target'])}</div>"
                f"<div class='metric-meta'>已得 {format_credit(card['completed'])} ／修讀中 {format_credit(card['ip'])}</div>"
                f"</div>"
            )

    html_str.append("</section>")
    st.markdown("".join(html_str), unsafe_allow_html=True)


def _render_lieflat_threshold_progress(summary, program_type, requirements, rules_meta, courses=None, report=None):
    """Render one Lieflat F5 chart for the principal credit thresholds.

    ``courses`` and ``report`` are optional for compatibility with direct
    callers.  The old implementation referenced both ``csv_bytes`` and
    ``report`` without defining them, so the chart raised before the section
    selector could render.  Build a small, valid CSV payload locally when a
    full course list is not supplied.
    """

    rows = [
        {
            "label": "畢業總學分",
            "completed": summary.get("total_completed", 0.0),
            "required": requirements.get("total", 0.0),
            "unit": "學分",
        },
        {
            "label": "校共同＋通識",
            "completed": summary.get("common_completed", 0.0),
            "required": requirements.get("common_total", 0.0),
            "unit": "學分",
        },
        {
            "label": "主修系專門",
            "completed": summary.get("major_completed", 0.0),
            "required": requirements.get("major_total", 0.0),
            "unit": "學分",
        },
        {
            "label": "自由選修",
            "completed": summary.get("free_completed", 0.0),
            "required": requirements.get("free_elective", 0.0),
            "unit": "學分",
        },
    ]
    if program_type != "單主修" and float(requirements.get("target_total", 0.0) or 0.0) > 0:
        rows.append(
            {
                "label": f"{program_type}目標系",
                "completed": summary.get("target_completed", 0.0),
                "required": requirements.get("target_total", 0.0),
                "unit": "學分",
            }
        )

    source = str(rules_meta.get("evidence_file") or rules_meta.get("source_file") or "學生手冊與成績單分析")
    st.markdown(
        render_progress_chart(rows, source=source),
        unsafe_allow_html=True,
    )
    report = report if isinstance(report, dict) else {}
    if courses:
        overview = pd.DataFrame(
            [
                {
                    "科目名稱": course.get("name", ""),
                    "科目屬性": course.get("type", ""),
                    "修課學年": course.get("academic_year", ""),
                    "學分數": course.get("total_credit", 0.0),
                    "是否完成": course.get("is_completed", False),
                    "修讀中": course.get("is_in_progress", False),
                }
                for course in courses
            ]
        )
    else:
        overview = pd.DataFrame(rows)
    csv_bytes = dataframe_csv_bytes(overview)
    st.markdown("<div class='export-group export-group-heading' role='group' aria-label='分類統計匯出'>", unsafe_allow_html=True)
    st.markdown("<div class='export-label'>分類統計匯出</div></div>", unsafe_allow_html=True)
    st.download_button(
        label="📦 全部匯出 CSV",
        data=csv_bytes,
        file_name=f"UTaipei_Credit_Audit_{report.get('handbook_year', rules_meta.get('version', 'unknown'))}_Overview.csv",
        mime="text/csv",
        use_container_width=False,
    )


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
            status_class = (
                "status-completed"
                if category_data["completed"] >= per_category_required
                else "status-ip"
                if category_data["completed"] + category_data["ip"] >= per_category_required
                else "status-missing"
            )
            st.markdown(
                f"""
                <div class='category-card'>
                    <div class='category-heading'>
                        <span class='category-name'>{escape(str(category_name))}</span>
                        <span class='status-badge {status_class}'>{escape(status)}</span>
                    </div>
                    <div class='category-meta'>已得: {category_data["completed"]:g} ／修讀中: {category_data["ip"]:g} ／目標: {per_category_required:g} 學分</div>
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
    _render_course_table_with_missing(
        common_report["compulsory_courses"],
        common_report["compulsory_missing"],
    )

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

    visible_missing = _render_course_table_with_missing(
        major_report["dept_compulsory_courses"],
        major_report["dept_compulsory_missing"],
    )
    missing_count = len(visible_missing)
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

    visible_missing = _render_course_table_with_missing(
        major_report["domain_compulsory_courses"],
        major_report["domain_compulsory_missing"],
    )
    missing_count = len(visible_missing)
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

    st.markdown(f"### 🧪 {program_type}：{target_dept}")
    target_req = report["requirements"]["target_total"]
    draw_premium_progress(
        f"🧪 {program_type} ({target_dept})", summary["target_completed"], target_req, ip=summary["target_ip"]
    )
    shared_reuse = report.get("shared_reuse", {})
    if shared_reuse.get("total", 0.0):
        st.warning(
            f"共同修課共享額度（合計 {shared_reuse.get('total', 0.0):g} 學分）僅作模擬配置；"
            f"{shared_reuse.get('completed', 0.0):g} 已完成、{shared_reuse.get('ip', 0.0):g} 修讀中，"
            f"不加總至原始學分守恆。{_shared_reuse_note(shared_reuse)}"
        )
    st.markdown("---")

    if "物化系" in target_dept:
        st.markdown("#### 🅰️ 物化系共同基礎必修")
        _render_course_table_with_missing(
            report["target"]["basic_core_courses"], report["target"]["basic_core_missing"]
        )
        st.markdown("#### 🅱️ 物化系其餘分組必修（只採手冊列示必修課）")
        _render_course_table_with_missing(
            report["target"]["compulsory_courses"], report["target"]["compulsory_missing"]
        )
    else:
        st.markdown("#### 🅰️ 資科系指定必修")
        _render_course_table_with_missing(
            report["target"]["compulsory_courses"], report["target"]["compulsory_missing"]
        )
        st.markdown("#### 🅱️ 資科系其他開設課程（只採該年度官方課表精確課名）")
        _render_course_table_with_missing(
            report["target"]["elective_courses"], report["target"].get("elective_missing", [])
        )


def _render_export_tab(courses, report, summary, requirements):
    st.markdown(
        f"### 📦 六、自由選修 與 全部匯出 (已取得 {report['free']['completed']:g}/{requirements['free_elective']:g} 學分)"
    )
    st.info("下方為歷年修課總表，您可匯出 CSV 供備查或核對。")
    if report.get("program_type") == "雙主修" or report.get("shared_reuse", {}).get("total", 0.0):
        st.warning(f"匯出提醒：{_shared_reuse_note(report.get('shared_reuse', {}))}")
    df_full = pd.DataFrame(courses).reindex(
        columns=["name", "type", "academic_year", "total_credit", "is_completed", "is_in_progress"]
    )
    categories = [_get_course_category(c, report) for c in courses]
    df_full.insert(1, "category", categories)
    df_full.insert(0, "handbook_year", report.get("handbook_year", ""))
    df_full.columns = ["審查手冊學年度", "科目名稱", "系統分類", "科目屬性", "修課學年", "學分數", "是否完成", "修讀中"]
    st.dataframe(df_full, use_container_width=True)
    csv_bytes = dataframe_csv_bytes(df_full)
    st.download_button(
        label="📥 匯出學分審查試算表 (CSV)",
        data=csv_bytes,
        file_name=f"UTaipei_Credit_Audit_{report.get('handbook_year', 'unknown')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    audit_payload = {
        "cohort": report.get("handbook_year", ""),
        "primary_program": report.get("primary_plan", {}).get("primary_program", "地生"),
        "track": report.get("primary_plan", {}).get("track", ""),
        "program_type": report.get("program_type", ""),
        "eligibility": report.get("double_major_eligibility") or {"status": report.get("summary", {}).get("graduation_status", UNKNOWN)},
        "status": report.get("summary", {}).get("graduation_status", UNKNOWN),
        "requirements": requirements,
        "gate_results": report.get("graduation_gates", {}),
        "manual_gates": report.get("manual_gates", {}),
        "warnings": report.get("policy_warnings", []) + report.get("document_warnings", []),
        "citations": report.get("citations", []),
        "application": report.get("application", {}),
        "report": report,
    }
    export_col_csv, export_col_json = st.columns(2)
    with export_col_csv:
        st.download_button(
            label="📥 匯出完整稽核 CSV",
            data=audit_csv_bytes(audit_payload),
            file_name=f"UTaipei_Credit_Audit_{report.get('handbook_year', 'unknown')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with export_col_json:
        st.download_button(
            label="📥 匯出完整稽核 JSON",
            data=audit_json_bytes(audit_payload),
            file_name=f"UTaipei_Credit_Audit_{report.get('handbook_year', 'unknown')}.json",
            mime="application/json",
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
    ge_csv = dataframe_csv_bytes(ge_df)
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
        overflow_csv = dataframe_csv_bytes(overflow_df)
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
        <section class='parsed-summary' aria-label='解析學分摘要'>
            <div class='parsed-summary-item'><span>解析總學分</span><b>{format_credit(parsed_total)}</b></div>
            <div class='parsed-summary-item'><span>已修得</span><b>{format_credit(parsed_completed)}</b></div>
            <div class='parsed-summary-item'><span>修讀中</span><b>{format_credit(parsed_ip)}</b></div>
            <div class='parsed-summary-item'><span>總含修讀中</span><b>{format_credit(summary.get("total_with_ip", 0.0))}</b></div>
        </section>
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
    visible_missing = _visible_missing_items(courses, missing_items)
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
        for item in visible_missing
    )
    if rows:
        _render_course_cards(rows)
    else:
        st.warning("⚠️ 目前無相關修課紀錄。")
    return visible_missing


def _visible_missing_items(courses, missing_items):
    """Hide a duplicate placeholder when the same requirement is already in progress."""
    in_progress_names = {
        normalize_course_name(course.get("name", ""))
        for course in courses
        if course.get("is_in_progress")
    }
    return [
        item
        for item in missing_items
        if item.get("status") != "in_progress"
        and normalize_course_name(item.get("name", "")) not in in_progress_names
    ]


def _render_course_cards(rows):
    if not rows:
        st.warning("⚠️ 目前無相關修課紀錄。")
        return
    html = [
        "<div class='course-list' role='table' aria-label='課程清單'>",
        "<div class='course-header' role='row'>",
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
        safe_name = escape(str(r.get("科目名稱", "")))
        safe_year = escape(str(r.get("修課學年", "")))
        safe_credit = escape(format_credit(r.get("學分", "")))
        safe_score = escape(str(r.get("成績", "")))
        safe_status = escape(str(status))
        allocation_note = str(r.get("配置備註") or r.get("allocation_note") or "").strip()
        safe_allocation_note = escape(allocation_note)
        allocation_markup = (
            f"<div class='course-allocation-note'>配置：{safe_allocation_note}</div>"
            if allocation_note
            else ""
        )
        identity_status = str(r.get("課程身分") or r.get("identity_status") or "").strip()
        identity_reason = str(r.get("身分理由") or r.get("identity_reason") or "").strip()
        identity_scope = str(r.get("身分範圍") or r.get("identity_scope") or "").strip()
        identity_authority = str(
            r.get("身分核准單位") or r.get("identity_authority") or r.get("authority") or ""
        ).strip()
        identity_evidence = str(
            r.get("身分證據引用")
            or r.get("identity_evidence_reference")
            or r.get("evidence_reference")
            or ""
        ).strip()
        identity_markup = ""
        if identity_status:
            identity_label = _IDENTITY_STATUS_LABELS.get(identity_status, identity_status)
            identity_parts = [identity_label]
            if identity_scope:
                identity_parts.append(f"範圍：{identity_scope}")
            if identity_reason:
                identity_parts.append(identity_reason)
            if identity_authority:
                identity_parts.append(f"核准：{identity_authority}")
            if identity_evidence:
                identity_parts.append(f"證據：{identity_evidence}")
            identity_markup = (
                "<div class='course-identity-note'>"
                + "｜".join(escape(part) for part in identity_parts)
                + "</div>"
            )
        html.append(
            f"<div class='course-row' role='row'>"
            f"<div class='course-name-col' role='cell' data-label='科目名稱'>{safe_name}{allocation_markup}{identity_markup}</div>"
            f"<div role='cell' data-label='修課學年'>{safe_year}</div>"
            f"<div role='cell' data-label='學分'>{safe_credit}</div>"
            f"<div role='cell' data-label='成績'>{safe_score}</div>"
            f"<div class='course-status-col' role='cell' data-label='狀態'><span class='status-badge status-{status_type}'>{safe_status}</span></div>"
            f"</div>"
        )

    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _course_row(c, allocation_context=None):
    score = c.get("sem1_score") if c.get("sem1_score") not in (None, "", "--") else c.get("sem2_score")
    status, status_type = _status_label(score)
    return {
        "科目名稱": c.get("name", ""),
        "修課學年": f"{c.get('academic_year', '')}學年",
        "學分": c.get("total_credit", 0.0),
        "成績": score,
        "狀態": status,
        "狀態類別": status_type,
        "配置備註": c.get("allocation_note") or (f"計入：{allocation_context}" if allocation_context else ""),
        "課程身分": c.get("identity_status", ""),
        "身分範圍": c.get("identity_scope", ""),
        "身分理由": c.get("identity_reason", ""),
        "身分核准單位": c.get("identity_authority") or c.get("authority", ""),
        "身分證據引用": c.get("identity_evidence_reference") or c.get("evidence_reference", ""),
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
