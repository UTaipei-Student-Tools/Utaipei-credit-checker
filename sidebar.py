"""
Sidebar control panel for the UTaipei graduation credit check app.
"""

import os
import tempfile

import streamlit as st

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


def render_sidebar(rules_meta):
    _init_session_state()

    st.sidebar.markdown("### 🎓 北市大校務整合")
    with st.sidebar.container():
        _render_rules_meta_card(rules_meta)
        _render_major_settings()
        st.sidebar.markdown("---")
        _render_upload_section()
        st.sidebar.markdown("---")
        _render_login_section()
        st.sidebar.markdown("---")
        _render_portal_discovery_section()

    return {
        "major_domain": st.session_state.get("major_domain", "地球環境"),
        "program_type": st.session_state.get("program_type", "雙主修"),
        "target_dept": st.session_state.get("target_dept", "物化系化學組"),
        "transcript_source": st.session_state.get("transcript_pdf_bytes") or st.session_state["transcript_pdf_path"],
        "source_label": st.session_state.get("source_label", "尚未載入"),
        "student_id": st.session_state.get("student_id", ""),
        "student_pwd": st.session_state.get("student_pwd", ""),
        "portal_features": st.session_state.get("portal_features", None),
    }


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
    }.items():
        st.session_state[key] = default


def _render_rules_meta_card(rules_meta):
    rules_version = rules_meta.get("version", "N/A")
    rules_updated = rules_meta.get("last_updated", "N/A")
    st.sidebar.markdown(
        f"""
        <div style="background: rgba(79,172,254,0.12); border:1px solid rgba(79,172,254,0.3); border-radius:10px; padding:10px 14px; margin-bottom:8px;">
            <div style="font-size:11px; color: var(--text-color, #94a3b8); opacity: 0.8; margin-bottom:2px;">📋 目前規則版本</div>
            <div style="font-size:15px; font-weight:700; color:#4facfe;">{rules_version} 學年度手冊</div>
            <div style="font-size:11px; color: var(--text-color, #64748b); opacity: 0.7;">最後更新：{rules_updated}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_major_settings():
    st.sidebar.markdown("### 🛠️ 學業模組設定")
    st.session_state["major_domain"] = st.sidebar.selectbox(
        "主修專業領域",
        options=["地球環境", "生命科學"],
        index=0,
        help="地生系分為『地球環境』與『生命科學』專業領域，必修14學分、選修至少20學分。",
    )
    st.session_state["program_type"] = st.sidebar.selectbox(
        "修課身分設定", options=["單主修", "雙主修", "輔系"], index=1, help="依據114學年度理學院手冊進行跨系學分核算。"
    )
    st.session_state["target_dept"] = st.sidebar.selectbox(
        "雙主修 / 輔系 目標學系",
        options=[
            "物化系化學組",
            "物化系物理組",
            "資科系",
        ],
        index=0,
        disabled=(st.session_state["program_type"] == "單主修"),
        help="目前僅提供已建置規則的物化系與資科系；其他學系不會顯示未經驗證的試算結果。",
    )


def _render_login_section():
    st.sidebar.markdown("### 🔐 學生入口登入")
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
            "學年度",
            options=["113", "114", "115", "116"],
            index=2,  # Default to 115
            help="選擇要抓取的課表學年度",
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


def _attempt_live_scrape():
    if not st.session_state["student_id"].strip() or not st.session_state["student_pwd"]:
        st.sidebar.error(
            "⚠️ 請先輸入您的學號與校務系統密碼！在輸入完畢後，請按 Enter 鍵確認或點選輸入框外，然後再點擊「實時抓取」。"
        )
        return
    try:
        scr_dir = tempfile.gettempdir()
        # 1. 抓取歷年成績單
        pdf_path = crawl_transcript_pdf(
            st.session_state["student_id"].strip(),
            st.session_state["student_pwd"],
            scr_dir,
        )
        st.session_state["transcript_pdf_path"] = pdf_path
        st.session_state["transcript_pdf_bytes"] = None
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
        st.sidebar.error(f"抓取失敗: {exc!s}")


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
        st.sidebar.error(f"課表抓取失敗: {exc!s}")
