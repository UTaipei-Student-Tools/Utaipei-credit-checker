"""
Sidebar control panel for the UTaipei graduation credit check app.
"""

import os
import tempfile
from html import escape

import streamlit as st

from handbook_rules import get_available_admission_cohorts, get_default_handbook_year, get_rules_meta
from policy_audit import get_target_program_options, get_primary_program_options, normalize_primary_program
from schedule_parser import parse_schedule_html
from scraper import (
    crawl_course_schedule,
    crawl_transcript_pdf,
    discover_portal_features,
)


def _init_session_state():
    if "transcript_pdf_path" not in st.session_state:
        st.session_state["transcript_pdf_path"] = None
    if "schedule_html" not in st.session_state:
        st.session_state["schedule_html"] = None
    if "transcript_pdf_bytes" not in st.session_state:
        st.session_state["transcript_pdf_bytes"] = None
    if "source_label" not in st.session_state:
        st.session_state["source_label"] = "尚未載入"
    if "upload_key_version" not in st.session_state:
        st.session_state["upload_key_version"] = 0
    if "handbook_year" not in st.session_state:
        st.session_state["handbook_year"] = get_default_handbook_year()
    if "admission_cohort" not in st.session_state:
        st.session_state["admission_cohort"] = st.session_state["handbook_year"]
    if "cohort_mismatch_confirmed" not in st.session_state:
        st.session_state["cohort_mismatch_confirmed"] = False


def render_sidebar():
    _init_session_state()

    st.sidebar.markdown("### 🎓 北市大校務整合")
    with st.sidebar.container():
        rules_meta = _render_handbook_selector()
        _render_rules_meta_card(rules_meta)
        _render_major_settings(st.session_state["handbook_year"])
        st.sidebar.markdown("---")
        _render_upload_section()
        st.sidebar.markdown("---")
        _render_login_section()
        st.sidebar.markdown("---")
        _render_portal_discovery_section()

    return {
        "handbook_year": st.session_state["handbook_year"],
        "admission_cohort": st.session_state.get("admission_cohort", st.session_state["handbook_year"]),
        "rules_meta": rules_meta,
        "major_domain": st.session_state.get("major_domain", "地球環境"),
        "program_type": st.session_state.get("program_type", "單主修"),
        "target_dept": st.session_state.get("target_dept", "物化系化學組"),
        "primary_program": st.session_state.get("primary_program", "地生"),
        "primary_track": st.session_state.get("primary_track", "地球環境"),
        "primary_program_label": st.session_state.get("primary_program_label", "地生（地球環境）"),
        "target_program": st.session_state.get("target_program"),
        "target_track": st.session_state.get("target_track"),
        "application_year": st.session_state.get("application_year"),
        "application_semester": st.session_state.get("application_semester"),
        "application_status": st.session_state.get("application_status"),
        "shared_credits": st.session_state.get("shared_credits"),
        "shared_approved": st.session_state.get("shared_approved"),
        "shared_evidence_state": st.session_state.get("shared_evidence_state"),
        "interrupted": bool(st.session_state.get("interrupted", False)),
        "cohort_mismatch_confirmed": bool(st.session_state.get("cohort_mismatch_confirmed", False)),
        "cs_project_evidence": st.session_state.get("cs_project_evidence"),
        "cs_certification_a": st.session_state.get("cs_certification_a"),
        "cs_certification_b": st.session_state.get("cs_certification_b"),
        "cs_alternative_course": st.session_state.get("cs_alternative_course"),
        "transcript_source": st.session_state.get("transcript_pdf_bytes") or st.session_state["transcript_pdf_path"],
        "source_label": st.session_state.get("source_label", "尚未載入"),
        "student_id": st.session_state.get("student_id", ""),
        "student_pwd": st.session_state.get("student_pwd", ""),
        "portal_features": st.session_state.get("portal_features", None),
    }


def _render_handbook_selector():
    st.sidebar.markdown("### 📚 適用學生手冊")
    years = get_available_admission_cohorts()
    if not years:
        raise RuntimeError("目前沒有可用的學生手冊規則。")
    current = st.session_state.get("handbook_year", get_default_handbook_year())
    if current not in years:
        current = get_default_handbook_year()
    selected = st.sidebar.selectbox(
        "入學 cohort／主要手冊",
        options=years,
        index=years.index(current),
        format_func=lambda year: f"{year} 學年度手冊",
        key="handbook_year_selector",
        help="入學 cohort 決定主要手冊；這與下方『課表抓取學年度』及雙主修申請年度是三件不同的事。",
    )
    st.session_state["handbook_year"] = selected
    st.session_state["admission_cohort"] = selected
    return get_rules_meta(selected)


def _render_upload_section():
    st.sidebar.markdown("### 📄 上傳成績單")
    uploaded_pdf = st.sidebar.file_uploader(
        "歷年成績單 PDF",
        type=["pdf"],
        key=f"transcript_upload_{st.session_state['upload_key_version']}",
        help="檔案只用於本次瀏覽器工作階段的學分分析，大小上限 20 MB。",
    )
    if uploaded_pdf is not None:
        data = uploaded_pdf.getvalue()
        if len(data) > 20 * 1024 * 1024:
            st.sidebar.error("PDF 超過 20 MB，請先壓縮後再上傳。")
        elif not data.startswith(b"%PDF-"):
            st.sidebar.error("檔案內容不是有效的 PDF。")
        elif data != st.session_state.get("transcript_pdf_bytes"):
            st.session_state["transcript_pdf_bytes"] = data
            st.session_state["transcript_pdf_path"] = None
            st.session_state["source_label"] = "自行上傳 PDF"
            st.sidebar.success("成績單已載入，可以開始審查。")

    if st.sidebar.button("🧹 清除目前資料", use_container_width=True):
        _clear_loaded_data()
        st.session_state["upload_key_version"] += 1
        st.rerun()


def _clear_loaded_data():
    temp_path = st.session_state.get("transcript_pdf_path")
    if temp_path and os.path.basename(temp_path).startswith("utaipei-transcript-"):
        try:
            os.remove(temp_path)
        except OSError:
            pass
    for key, default in {
        "transcript_pdf_path": None,
        "transcript_pdf_bytes": None,
        "source_label": "尚未載入",
        "schedule_html": None,
        "schedule_courses": [],
        "cohort_mismatch_confirmed": False,
    }.items():
        st.session_state[key] = default
    st.session_state.pop("cohort_mismatch_confirmation", None)


def _render_rules_meta_card(rules_meta):
    rules_version = escape(str(rules_meta.get("version", "N/A")))
    rules_updated = escape(str(rules_meta.get("last_updated", "N/A")))
    source_file = escape(str(rules_meta.get("evidence_file") or rules_meta.get("source_file", "未標示")))
    verification = escape(str(rules_meta.get("verification", "尚未標示")))
    st.sidebar.markdown(
        f"""
        <section class="sidebar-rules-card" aria-label="目前規則版本">
            <div class="sidebar-eyebrow">📋 目前規則版本</div>
            <div class="sidebar-rules-version">{rules_version} 學年度手冊</div>
            <div class="sidebar-meta">最後更新：{rules_updated}</div>
            <div class="sidebar-meta">來源：{source_file}</div>
            <div class="sidebar-meta">核對：{verification}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_major_settings(handbook_year):
    st.sidebar.markdown("### 🛠️ 學業模組設定")
    cohort = st.session_state.get("admission_cohort", handbook_year)
    options = get_primary_program_options(cohort)
    current_label = st.session_state.get("primary_program_label", options[0])
    if current_label not in options:
        current_label = options[0]
    selected_label = st.sidebar.selectbox(
        "主修系所／組別",
        options=options,
        index=options.index(current_label),
        key="primary_program_selector",
        help="選擇主要主修系所／組別；115 學年度數學標示為『數據科學與數學』。",
    )
    primary_program, primary_track = normalize_primary_program(selected_label, cohort)
    st.session_state["primary_program_label"] = selected_label
    st.session_state["primary_program"] = primary_program
    st.session_state["primary_track"] = primary_track
    st.session_state["major_domain"] = primary_track if primary_program == "地生" else "地球環境"
    program_type = st.session_state.get("program_type", "單主修")
    if program_type not in {"單主修", "雙主修"}:
        program_type = "單主修"
    st.session_state["program_type"] = st.sidebar.selectbox(
        "修課身分設定",
        options=["單主修", "雙主修"],
        index=["單主修", "雙主修"].index(program_type),
        key="program_type_selector",
        help=f"依據 {handbook_year} 學年度理學院手冊進行跨系學分核算。",
    )
    # Exclude the complete primary department, including its other track;
    # double-majoring between two groups of the same department is not a
    # valid cross-department target.
    target_options = get_target_program_options(cohort, selected_label)
    if st.session_state.get("target_program_selector") not in target_options:
        st.session_state["target_program_selector"] = target_options[0]
    target_label = st.sidebar.selectbox(
        "雙主修目標系所／組別",
        options=target_options,
        index=0,
        disabled=(st.session_state["program_type"] == "單主修"),
        key="target_program_selector",
        help="雙主修目標不可與主要選擇相同；課程細項未核對的目標會保持『需人工確認』。",
    )
    target_program, target_track = normalize_primary_program(target_label, cohort)
    st.session_state["target_program"] = target_program if st.session_state["program_type"] == "雙主修" else None
    st.session_state["target_track"] = target_track if st.session_state["program_type"] == "雙主修" else None
    if target_program == "資科":
        st.session_state["target_dept"] = "資科系"
    elif target_program == "物化":
        st.session_state["target_dept"] = "物化系物理組" if target_track == "電子物理" else "物化系化學組"
    elif target_program == "地生":
        st.session_state["target_dept"] = "地生系"
    else:
        st.session_state["target_dept"] = "數學系"

    if st.session_state["program_type"] == "雙主修":
        st.sidebar.markdown("#### 📅 雙主修申請資訊（不由入學 cohort 推定）")
        st.session_state["application_year"] = st.sidebar.selectbox(
            "申請學年",
            options=["未填寫", *[str(int(cohort) + offset) for offset in range(5)]],
            format_func=lambda year: "未填寫" if year == "未填寫" else f"{year} 學年度",
            key="double_application_year",
            help="校級規則為大二起至正常修業最後一年第一學期。",
        )
        st.session_state["application_semester"] = st.sidebar.selectbox(
            "申請學期",
            options=["未填寫", "1", "2"],
            key="double_application_semester",
        )
        st.session_state["application_status"] = st.sidebar.selectbox(
            "申請狀態",
            options=["未申請", "申請中", "已核准", "未通過", "不確定"],
            key="double_application_status",
        )
        shared_state = st.sidebar.selectbox(
            "共同修課證據狀態",
            options=["unanswered", "confirmed_zero", "approved"],
            format_func=lambda value: {
                "unanswered": "未回答／不確定",
                "confirmed_zero": "已確認0學分",
                "approved": "已核准共同修課（1–6）",
            }.get(value, "未回答／不確定"),
            key="shared_evidence_state_input",
            help="未回答不會被當成已確認0學分；核准的1–6學分會以獨立共享額度列入稽核。",
        )
        st.session_state["shared_evidence_state"] = shared_state
        if shared_state == "approved":
            st.session_state["shared_credits"] = st.sidebar.number_input(
                "已核准共同修課學分（1–6）", min_value=1.0, max_value=6.0, value=1.0, step=0.5, key="shared_credit_input"
            )
            st.session_state["shared_approved"] = True
        elif shared_state == "confirmed_zero":
            st.session_state["shared_credits"] = 0.0
            st.session_state["shared_approved"] = True
        else:
            st.session_state["shared_credits"] = None
            st.session_state["shared_approved"] = None
        st.session_state["interrupted"] = st.sidebar.checkbox(
            "曾休學／中斷修業",
            value=bool(st.session_state.get("interrupted", False)),
            key="interrupted_input",
            help="勾選後不由修業年級推導申請資格，時點結果固定保守標示為『需人工確認』。",
        )
    else:
        for key in (
            "application_year",
            "application_semester",
            "application_status",
            "shared_credits",
            "shared_approved",
            "shared_evidence_state",
        ):
            st.session_state[key] = None
        st.session_state["interrupted"] = False

    if primary_program == "資科":
        st.sidebar.markdown("#### 🧾 資科系人工門檻證據")
        st.session_state["cs_project_evidence"] = st.sidebar.selectbox(
            "專題證據",
            options=["unknown", "completed", "incomplete"],
            format_func=lambda value: {
                "unknown": "不確定／需人工確認",
                "completed": "已完成",
                "incomplete": "未完成",
            }.get(value, "不確定／需人工確認"),
            key="cs_project_evidence_input",
        )
        st.session_state["cs_certification_a"] = st.sidebar.number_input("認證 A 件數", min_value=0, max_value=20, value=0, step=1, key="cs_cert_a_input")
        st.session_state["cs_certification_b"] = st.sidebar.number_input("認證 B 件數", min_value=0, max_value=20, value=0, step=1, key="cs_cert_b_input")
        st.session_state["cs_alternative_course"] = st.sidebar.selectbox(
            "替代課程證據",
            options=["unknown", "completed", "incomplete"],
            format_func=lambda value: {
                "unknown": "不確定／需人工確認",
                "completed": "已完成",
                "incomplete": "未完成",
            }.get(value, "不確定／需人工確認"),
            key="cs_alt_course_input",
        )


def _render_login_section():
    st.sidebar.markdown("### 🔐 學生入口登入")
    st.sidebar.caption("校務系統可能封鎖 Hugging Face／雲端出口；抓取失敗時請改用上方 PDF 上傳。")
    st.session_state["student_id"] = st.sidebar.text_input(
        "學號 / Account", value=st.session_state.get("student_id", ""), placeholder="請輸入您的學號"
    )
    st.session_state["student_pwd"] = st.sidebar.text_input(
        "密碼 / Password", value="", type="password", placeholder="請輸入校務系統密碼"
    )

    st.sidebar.markdown("#### 📅 課表抓取學期設定")
    col_y, col_s = st.sidebar.columns(2)
    with col_y:
        st.session_state["crawl_year"] = st.selectbox(
            "課表學年度",
            options=["113", "114", "115", "116"],
            index=2,  # Default to 115
            help="只決定要抓哪一學期的課表；不會改變上方的學生手冊版本。",
        )
    with col_s:
        st.session_state["crawl_semester"] = st.selectbox(
            "學期",
            options=["1", "2"],
            index=0,  # Default to 1
            help="選擇要抓取的課表學期",
        )

    if st.sidebar.button("🚀 實時抓取", use_container_width=True, help="登入並抓取歷年成績與設定學期之課表"):
        _attempt_live_scrape()

    if st.sidebar.button("🗓️ 抓取並更新下學期課表", use_container_width=True, help="僅登入抓取所選學期之選課課表並合併"):
        _attempt_schedule_crawl()
    if st.session_state.get("schedule_courses"):
        schedule_courses = st.session_state["schedule_courses"]
        schedule_credits = sum(float(course.get("total_credit") or 0.0) for course in schedule_courses)
        st.sidebar.caption(
            f"已載入 {len(schedule_courses)} 門課表課程、共 {schedule_credits:g} 學分，將以修讀中納入進度條。"
        )


def _render_portal_discovery_section():
    st.sidebar.markdown("### 🔎 校務系統功能探勘")
    if st.sidebar.button(
        "🔧 發現可用校務功能", use_container_width=True, help="檢查您的帳號可存取哪些校務系統額外查詢功能"
    ):
        _discover_portal_capabilities()
    features = st.session_state.get("portal_features")
    if features:
        st.sidebar.markdown("#### 可用功能清單")
        for item in features:
            st.sidebar.markdown(f"- **{item['fncid']}**：{item['name']}，狀態：`{item['status']}`")


def _discover_portal_capabilities():
    try:
        features = discover_portal_features(
            st.session_state["student_id"].strip(),
            st.session_state["student_pwd"],
        )
        st.session_state["portal_features"] = features
        st.sidebar.success("已完成校務功能探勘，請查看下方清單。")
    except Exception as exc:
        st.sidebar.error(f"功能探勘失敗：{exc!s}")
    finally:
        # Capability discovery is also a portal request; do not retain the
        # password in Streamlit session state after either outcome.
        st.session_state["student_pwd"] = ""


def _attempt_live_scrape():
    if not st.session_state["student_id"].strip() or not st.session_state["student_pwd"]:
        st.sidebar.error(
            "⚠️ 請先輸入您的學號與校務系統密碼！在輸入完畢後，請按 Enter 鍵確認或點選輸入框外，然後再點擊「實時抓取」。"
        )
        return
    try:
        scr_dir = tempfile.gettempdir()
        # 1. 抓取歷年成績單
        pdf_content = crawl_transcript_pdf(
            st.session_state["student_id"].strip(),
            st.session_state["student_pwd"],
            scr_dir,
        )
        # The crawler returns validated bytes and removes its temporary file
        # before returning; keep only in-memory content for this session.
        st.session_state["transcript_pdf_path"] = None
        st.session_state["transcript_pdf_bytes"] = pdf_content
        st.session_state["source_label"] = "校務系統即時抓取"
        st.session_state["collapse_sidebar_flag"] = True

        # 2. 自動嘗試抓取下學期課表
        year = st.session_state.get("crawl_year", "115")
        semester = st.session_state.get("crawl_semester", "1")
        try:
            schedule_html = crawl_course_schedule(
                st.session_state["student_id"].strip(), st.session_state["student_pwd"], year=year, semester=semester
            )
            st.session_state["schedule_html"] = schedule_html
            parsed_courses = parse_schedule_html(schedule_html, academic_year=year, semester=semester)
            st.session_state["schedule_courses"] = parsed_courses
            if parsed_courses:
                credits = sum(float(course.get("total_credit") or 0.0) for course in parsed_courses)
                st.sidebar.success(
                    f"歷年成績抓取成功；另找到 {year}-{semester} 課表 {len(parsed_courses)} 門、{credits:g} 學分。"
                )
            else:
                st.sidebar.info(f"歷年成績抓取成功；{year}-{semester} 課表目前沒有可納入的課程。")
        except Exception as schedule_exc:
            st.session_state["schedule_courses"] = []
            st.sidebar.warning(f"動態歷年成績抓取成功！但自動抓取 {year}-{semester} 課表失敗：{schedule_exc!s}")

    except Exception as exc:
        st.sidebar.error(f"抓取失敗: {exc!s}。若目前是 HF／雲端環境，請改用 PDF 上傳。")
    finally:
        # Never retain the portal password in Streamlit session state after a
        # fetch attempt; the user can re-enter it for a later request.
        st.session_state["student_pwd"] = ""


def _attempt_schedule_crawl():
    if not st.session_state["student_id"].strip() or not st.session_state["student_pwd"]:
        st.sidebar.error("⚠️ 請先輸入您的學號與校務系統密碼！")
        return
    try:
        year = st.session_state.get("crawl_year", "115")
        semester = st.session_state.get("crawl_semester", "1")
        schedule_html = crawl_course_schedule(
            st.session_state["student_id"].strip(), st.session_state["student_pwd"], year=year, semester=semester
        )
        st.session_state["schedule_html"] = schedule_html
        parsed_courses = parse_schedule_html(schedule_html, academic_year=year, semester=semester)
        st.session_state["schedule_courses"] = parsed_courses

        if parsed_courses:
            credits = sum(float(course.get("total_credit") or 0.0) for course in parsed_courses)
            st.sidebar.success(
                f"成功解析 {year}-{semester} 課表 {len(parsed_courses)} 門、{credits:g} 學分，已納入修讀中進度。"
            )
        else:
            st.sidebar.warning(f"已抓取 {year}-{semester} 頁面，但未解析出任何選課。可能是該學期尚無選課紀錄。")
    except Exception as exc:
        st.session_state["schedule_html"] = None
        st.session_state["schedule_courses"] = []
        st.sidebar.error(f"課表抓取失敗: {exc!s}。若目前是 HF／雲端環境，請改用 PDF 上傳。")
    finally:
        st.session_state["student_pwd"] = ""
