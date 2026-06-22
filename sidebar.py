# -*- coding: utf-8 -*-
"""
Sidebar control panel for the UTaipei graduation credit check app.
"""

import os
import streamlit as st
from scraper import crawl_transcript_pdf, discover_portal_features, crawl_course_schedule


def _init_session_state():
    if "transcript_pdf_path" not in st.session_state:
        st.session_state["transcript_pdf_path"] = None
    if "offline_demo" not in st.session_state:
        st.session_state["offline_demo"] = False
    if "schedule_html" not in st.session_state:
        st.session_state["schedule_html"] = None


def render_sidebar(rules_meta):
    _init_session_state()

    st.sidebar.markdown("### 🎓 北市大校務整合")
    with st.sidebar.container():
        _render_rules_meta_card(rules_meta)
        _render_major_settings()
        st.sidebar.markdown("---")
        _render_login_section()
        st.sidebar.markdown("---")
        _render_portal_discovery_section()

    return {
        "major_domain": st.session_state.get("major_domain", "地球環境"),
        "program_type": st.session_state.get("program_type", "雙主修"),
        "target_dept": st.session_state.get("target_dept", "物化系化學組"),
        "transcript_pdf_path": st.session_state["transcript_pdf_path"],
        "offline_demo": st.session_state["offline_demo"],
        "student_id": st.session_state.get("student_id", ""),
        "student_pwd": st.session_state.get("student_pwd", ""),
        "portal_features": st.session_state.get("portal_features", None)
    }


def _render_rules_meta_card(rules_meta):
    rules_version = rules_meta.get("version", "N/A")
    rules_updated = rules_meta.get("last_updated", "N/A")
    st.sidebar.markdown(
        f"""
        <div style="background: rgba(79,172,254,0.08); border:1px solid rgba(79,172,254,0.2); border-radius:10px; padding:10px 14px; margin-bottom:8px;">
            <div style="font-size:11px; color:#94a3b8; margin-bottom:2px;">📋 目前規則版本</div>
            <div style="font-size:15px; font-weight:700; color:#4facfe;">{rules_version} 學年度手冊</div>
            <div style="font-size:11px; color:#64748b;">最後更新：{rules_updated}</div>
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
        help="地生系分為『地球環境』與『生命科學』專業領域，必修14學分、選修至少20學分。"
    )
    st.session_state["program_type"] = st.sidebar.selectbox(
        "修課身分設定",
        options=["單主修", "雙主修", "輔系"],
        index=1,
        help="依據114學年度理學院手冊進行跨系學分核算。"
    )
    st.session_state["target_dept"] = st.sidebar.selectbox(
        "雙主修 / 輔系 目標學系",
        options=[
            "物化系化學組",
            "物化系物理組",
            "資科系",
            "資工系",
            "數學系",
            "統計系",
            "地理系",
            "地球科學系",
        ],
        index=0,
        disabled=(st.session_state["program_type"] == "單主修"),
        help="請選擇您修讀的輔雙主修學系組別。註：系統目前自動支援物化系與資科系規則，其餘學系為參考顯示。"
    )


def _render_login_section():
    st.sidebar.markdown("### 🔐 學生入口登入")
    st.session_state["student_id"] = st.sidebar.text_input(
        "學號 / Account",
        value=st.session_state.get("student_id", ""),
        placeholder="請輸入您的學號"
    )
    st.session_state["student_pwd"] = st.sidebar.text_input(
        "密碼 / Password",
        value="",
        type="password",
        placeholder="請輸入校務系統密碼"
    )

    col_scrape, col_demo = st.sidebar.columns(2)
    with col_scrape:
        if st.button("🚀 實時抓取", use_container_width=True, help="直接登入校務系統抓取歷年成績單PDF"):
            _attempt_live_scrape()
    with col_demo:
        if st.button("📂 載入 Demo", use_container_width=True, help="一鍵載入本機快取之歷年成績單PDF進行展示"):
            _load_demo_pdf()

    if st.sidebar.button("🧾 測試抓修課紀錄", use_container_width=True, help="登入校務系統並抓取修課紀錄頁面，供測試用"):
        _attempt_schedule_crawl()
    if st.session_state.get("schedule_html"):
        st.sidebar.markdown("### 🗂️ 修課紀錄測試結果")
        st.sidebar.text_area("抓取到的修課紀錄頁面 HTML", value=st.session_state["schedule_html"], height=240)


def _render_portal_discovery_section():
    st.sidebar.markdown("### 🔎 校務系統功能探勘")
    if st.sidebar.button("🔧 發現可用校務功能", use_container_width=True, help="檢查您的帳號可存取哪些校務系統額外查詢功能"):
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
        st.sidebar.error(f"功能探勘失敗：{str(exc)}")


def _attempt_live_scrape():
    if not st.session_state["student_id"].strip() or not st.session_state["student_pwd"]:
        st.sidebar.error("⚠️ 請先輸入您的學號與校務系統密碼！在輸入完畢後，請按 Enter 鍵確認或點選輸入框外，然後再點擊「實時抓取」。")
        return
    try:
        scr_dir = os.path.dirname(os.path.abspath(__file__))
        pdf_path = crawl_transcript_pdf(
            st.session_state["student_id"].strip(),
            st.session_state["student_pwd"],
            scr_dir,
        )
        st.session_state["transcript_pdf_path"] = pdf_path
        st.session_state["offline_demo"] = False
        st.session_state["collapse_sidebar_flag"] = True
        st.sidebar.success("動態歷年成績抓取成功！")
    except Exception as exc:
        st.sidebar.error(f"抓取失敗: {str(exc)}")


def _attempt_schedule_crawl():
    if not st.session_state["student_id"].strip() or not st.session_state["student_pwd"]:
        st.sidebar.error("⚠️ 請先輸入您的學號與校務系統密碼！")
        return
    try:
        schedule_html = crawl_course_schedule(
            st.session_state["student_id"].strip(),
            st.session_state["student_pwd"],
        )
        st.session_state["schedule_html"] = schedule_html
        st.sidebar.success("修課紀錄頁面抓取成功！")
    except Exception as exc:
        st.session_state["schedule_html"] = None
        st.sidebar.error(f"測試抓取失敗: {str(exc)}")


def _load_demo_pdf():
    scr_dir = os.path.dirname(os.path.abspath(__file__))
    demo_pdf = os.path.join(scr_dir, "student_transcript.pdf")
    if os.path.exists(demo_pdf):
        st.session_state["transcript_pdf_path"] = demo_pdf
        st.session_state["offline_demo"] = True
        st.session_state["collapse_sidebar_flag"] = True
        st.sidebar.success("已載入離線展示成績單！")
    else:
        st.sidebar.error("找不到本機快取的 student_transcript.pdf 檔案！")
