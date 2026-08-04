"""
UI helper functions for the UTaipei graduation credit check Streamlit app.
"""

import math
from html import escape

import streamlit as st
import streamlit.components.v1 as components


def format_credit(value):
    """Format a credit value consistently without changing its numeric data."""
    if value in (None, ""):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return str(value)
    return f"{numeric:.1f}"


def setup_page():
    st.set_page_config(
        page_title="北市大畢業學分審查系統 | UTaipei Credit Checker",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="auto",
    )
    inject_theme_css()


def collapse_sidebar_if_needed():
    if st.session_state.get("collapse_sidebar_flag"):
        components.html(
            """
            <script>
                setTimeout(function() {
                    const parent = window.parent;
                    let closed = false;
                    parent.document.querySelectorAll('button').forEach(b => {
                        const label = b.getAttribute('aria-label');
                        if (label === 'Close sidebar' || label === 'Close') {
                            b.click();
                            closed = true;
                        }
                    });
                    if (!closed) {
                        const btn = parent.document.querySelector('[data-testid="stSidebarCollapseButton"]');
                        if (btn) btn.click();
                    }
                    // Fallback to trigger escape key
                    parent.document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true }));
                }, 300);
            </script>
            """,
            height=0,
            width=0,
        )
        st.session_state["collapse_sidebar_flag"] = False


def inject_theme_css():
    st.markdown(
        """
        <style>
            *, *::before, *::after {
                box-sizing: border-box;
            }
            html, body, [class*="css"] {
                font-family: "Noto Sans TC", "Microsoft JhengHei", system-ui, -apple-system, sans-serif;
                color: var(--text-color, #111827);
                font-size: 16px !important;
            }
            [data-testid="stAppViewContainer"] {
                max-width: 100%;
                overflow-x: clip;
            }
            [data-testid="stMain"],
            [data-testid="stMainBlockContainer"],
            [data-testid="stSidebar"],
            [data-testid="stSidebarContent"] {
                min-width: 0;
            }
            [data-testid="stMainBlockContainer"] {
                width: 100%;
                max-width: 100%;
            }
            .stMarkdown p, .stMarkdown li, .stMarkdown div {
                font-size: 16px !important;
            }
            .stApp {
                background: var(--background-color, linear-gradient(180deg, #F8FAFC 0%, #E2E8F0 100%));
                min-height: 100vh;
            }
            /*
             * Streamlit 1.57 sets color-scheme on the sidebar but does not
             * expose --text-color. CanvasText therefore follows the explicit
             * Light/Dark choice without disturbing native BaseWeb controls.
             */
            [data-testid="stSidebar"] {
                --text-color: CanvasText;
            }
            .stApp, .stApp div, .stApp p, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp a, .stApp label {
                color: var(--text-color, #111827) !important;
            }
            .stMarkdown {
                color: var(--text-color, #111827) !important;
            }
            .header-card {
                background: linear-gradient(135deg, rgba(14, 165, 233, 0.12), rgba(14, 165, 233, 0.03));
                border: 1px solid rgba(14, 165, 233, 0.15);
                border-radius: 24px;
                padding: 32px;
                margin-bottom: 26px;
                box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
                text-align: center;
            }
            .header-title {
                font-size: 40px;
                font-weight: 800;
                background: linear-gradient(90deg, #0ea5e9 0%, #38bdf8 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 6px;
            }
            .header-subtitle {
                font-size: 16px;
                color: var(--text-color, #334155) !important;
                opacity: 0.85;
                letter-spacing: .6px;
                line-height: 1.6;
            }
            .source-badge {
                display: inline-flex;
                align-items: center;
                background: rgba(14, 165, 233, 0.12);
                border: 1px solid rgba(14, 165, 233, 0.25);
                color: #0369a1 !important;
                padding: 5px 10px;
                border-radius: 999px;
                font-size: 13px !important;
                font-weight: 700;
            }
            .metric-card {
                background: var(--secondary-background-color, #ffffff) !important;
                border: 1px solid var(--border-color, rgba(226, 232, 240, 0.8)) !important;
                color: var(--text-color, #111827) !important;
                border-radius: 20px;
                padding: 22px 20px;
                text-align: left;
                box-shadow: 0 14px 30px rgba(15, 23, 42, 0.06);
                transition: transform 0.25s ease, border-color 0.25s ease;
            }
            .metric-card:hover {
                transform: translateY(-3px);
                border-color: rgba(14, 165, 233, 0.35) !important;
            }
            .metric-value {
                font-size: 34px;
                font-weight: 800;
                margin-top: 6px;
            }
            .metric-label {
                font-size: 13px;
                color: var(--text-color, #475569) !important;
                opacity: 0.85;
                font-weight: 600;
            }
            .status-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 5px 14px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
                text-align: center;
                white-space: nowrap;
            }
            .status-completed {
                background-color: rgba(16, 185, 129, 0.15) !important;
                color: #10b981 !important;
                border: 1px solid rgba(16, 185, 129, 0.3) !important;
            }
            .status-ip {
                background-color: rgba(59, 130, 246, 0.15) !important;
                color: #3b82f6 !important;
                border: 1px solid rgba(59, 130, 246, 0.3) !important;
            }
            .status-missing {
                background-color: rgba(249, 115, 22, 0.15) !important;
                color: #f97316 !important;
                border: 1px solid rgba(249, 115, 22, 0.3) !important;
            }
            .progress-container {
                margin-bottom: 16px;
            }
            .progress-label-row {
                display: flex;
                justify-content: space-between;
                font-size: 13px;
                margin-bottom: 8px;
                color: var(--text-color, #334155) !important;
                opacity: 0.85;
            }
            .progress-bar-bg {
                background-color: var(--border-color, rgba(226, 232, 240, 0.95));
                border-radius: 999px;
                height: 14px;
                width: 100%;
                overflow: hidden;
                border: 1px solid var(--border-color, rgba(226, 232, 240, 0.9));
            }
            .progress-bar-fill {
                height: 100%;
                border-radius: 999px;
                transition: width 0.8s ease-in-out;
            }
            .card-panel {
                background: var(--secondary-background-color, #ffffff) !important;
                border: 1px solid var(--border-color, rgba(226, 232, 240, 0.85)) !important;
                color: var(--text-color, #0f172a) !important;
                border-radius: 24px;
                padding: 24px;
                box-shadow: 0 18px 36px rgba(15, 23, 42, 0.05);
            }
            .card-panel * {
                color: var(--text-color, #0f172a) !important;
            }
            .card-panel button, .card-panel button * {
                color: inherit !important;
            }
            .section-heading {
                font-size: 18px;
                font-weight: 700;
                margin-bottom: 14px;
                color: var(--text-color, #0f172a) !important;
            }
            .table-container {
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }
            .table-container table {
                border-collapse: collapse;
                width: 100%;
                min-width: 400px;
            }
            .table-container th, .table-container td {
                padding: 10px 12px;
                border-bottom: 1px solid var(--border-color, rgba(226, 232, 240, 0.9)) !important;
                color: var(--text-color, #0f172a) !important;
                white-space: nowrap;
            }
            .table-container th {
                background: var(--secondary-background-color, rgba(226, 232, 240, 0.7)) !important;
                font-weight: 700;
            }
            .stDownloadButton>button {
                border-radius: 999px;
            }
            .hero-callout {
                background: linear-gradient(90deg, rgba(56, 189, 248, 0.18), rgba(56, 189, 248, 0.03));
                border: 1px solid rgba(56, 189, 248, 0.22);
                border-radius: 18px;
                padding: 18px 22px;
                margin-bottom: 18px;
                color: var(--text-color, #0f172a) !important;
            }
            .hero-callout strong {
                color: var(--text-color, #0c4a6e) !important;
            }
            /* Keep Streamlit's native tab scrolling/arrows; do not override geometry. */
            [data-testid="stTabs"] [role="tab"],
            [data-testid="stTabs"] button[data-baseweb="tab"] {
                font-size: 15px !important;
                font-weight: 700 !important;
            }
            /* Responsive Utilities */
            .info-flex {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-bottom: 22px;
                align-items: center;
                justify-content: space-between;
            }
            .info-card {
                background: var(--secondary-background-color, #ffffff) !important;
                border: 1px solid var(--border-color, rgba(148,163,184,0.16)) !important;
                border-radius: 20px;
                padding: 18px 22px;
                box-shadow: 0 18px 40px rgba(15,23,42,0.05);
                flex: 1;
                min-width: 250px;
                max-width: 100%;
            }
            .info-card * {
                color: var(--text-color, #111827) !important;
            }
            .info-card-highlight {
                background: linear-gradient(135deg, rgba(14,165,233,0.14), rgba(6,182,212,0.05)) !important;
                border: 1px solid rgba(14,165,233,0.18) !important;
            }
            .overview-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 16px;
                align-items: stretch;
            }
            .overview-grid > div {
                background: var(--secondary-background-color, #ffffff) !important;
                border: 1px solid var(--border-color, rgba(226, 232, 240, 0.8)) !important;
            }
            .overview-grid > div > div {
                color: var(--text-color, #111827) !important;
            }
            .overview-grid > div > div:first-child {
                color: var(--text-color, #475569) !important;
                opacity: 0.8;
            }
            .overview-grid > div > div:last-child {
                color: var(--text-color, #64748b) !important;
                opacity: 0.7;
            }
            .metric-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr));
                gap: 16px;
                align-items: stretch;
            }
            .metric-grid > div {
                background: var(--secondary-background-color, #ffffff) !important;
                border: 1px solid var(--border-color, rgba(226, 232, 240, 0.8)) !important;
            }
            .metric-grid > div > div:first-child {
                color: var(--text-color, #475569) !important;
                opacity: 0.8;
            }
            .metric-grid > div > div:last-child {
                color: var(--text-color, #64748b) !important;
                opacity: 0.7;
            }
            .course-row {
                display: grid;
                grid-template-columns: 3fr 1fr 0.8fr 0.8fr 1fr;
                gap: 12px;
                padding: 16px;
                align-items: center;
                background: var(--secondary-background-color, #ffffff) !important;
                border: 1px solid var(--border-color, rgba(226, 232, 240, 0.9)) !important;
                border-radius: 18px;
                min-width: 0;
            }
            .course-row * {
                color: var(--text-color, #111827) !important;
            }
            .course-row > div,
            .course-header > div {
                min-width: 0;
                overflow-wrap: anywhere;
            }
            .course-header {
                display: grid;
                grid-template-columns: 3fr 1fr 0.8fr 0.8fr 1fr;
                gap: 12px;
                padding: 14px 16px;
                color: var(--text-color, #475569) !important;
                opacity: 0.8;
                font-size: 13px;
                font-weight: 700;
                background: var(--secondary-background-color, #f8fafc) !important;
                border-radius: 18px;
            }

            @media (max-width: 1100px) {
                .overview-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
                .metric-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
                .course-row,
                .course-header {
                    grid-template-columns: minmax(0, 2.4fr) minmax(88px, 0.9fr) minmax(64px, 0.7fr) minmax(64px, 0.7fr) minmax(86px, 0.9fr);
                }
            }

            @media (max-width: 768px) {
                [data-testid="stMainBlockContainer"] {
                    padding: 4.5rem 0.75rem 4rem !important;
                }
                [data-testid="stSidebar"][aria-expanded="true"] {
                    width: min(88vw, 22rem) !important;
                    max-width: 88vw !important;
                }
                [data-testid="stSidebarContent"] {
                    padding-top: 0.75rem;
                }
                [data-testid="stHorizontalBlock"] {
                    gap: 0.75rem;
                    flex-wrap: wrap;
                }
                [data-testid="column"] {
                    min-width: min(100%, 14rem);
                    flex: 1 1 14rem !important;
                }
                .stButton > button,
                .stDownloadButton > button,
                [data-baseweb="select"] > div,
                [data-testid="stFileUploaderDropzone"] button {
                    min-height: 44px;
                }
                [data-testid="stMainMenuButton"] {
                    min-width: 44px;
                    min-height: 44px;
                }
                .stButton > button,
                .stDownloadButton > button {
                    width: 100%;
                }
                .header-title {
                    font-size: clamp(24px, 7vw, 28px);
                    line-height: 1.25;
                    overflow-wrap: anywhere;
                }
                .header-card { padding: 22px 18px; border-radius: 20px; }
                .header-subtitle { font-size: 14px; }
                .info-flex { flex-direction: column !important; }
                .info-flex > .info-card { width: 100% !important; min-width: 0 !important; margin-bottom: 8px; }
                .overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
                .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
                .metric-card { padding: 18px 16px; }
                .metric-value { font-size: 28px; }
                .card-panel { padding: 18px; border-radius: 20px; }
                .hero-callout { padding: 16px; }
                .table-container { max-width: 100%; }
                
                .course-header { display: none !important; }
                .course-row {
                    grid-template-columns: 1fr !important;
                    gap: 8px !important;
                    padding: 16px !important;
                }
                .course-row > div {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    word-break: break-word;
                    overflow-wrap: anywhere;
                    text-align: right;
                }
                .course-row > div::before {
                    content: attr(data-label);
                    font-weight: bold;
                    color: var(--text-color, #475569) !important;
                    opacity: 0.8;
                    margin-right: 12px;
                    white-space: nowrap;
                    flex-shrink: 0;
                }
                .course-name-col::before { display: none !important; }
                .course-name-col {
                    font-weight: 700;
                    font-size: 16px !important;
                    justify-content: flex-start !important;
                    color: var(--text-color, #111827) !important;
                    margin-bottom: 4px;
                    text-align: left !important;
                    word-break: break-word;
                }
                .course-status-col { justify-content: flex-start !important; margin-top: 4px; }
                .course-status-col span { white-space: nowrap !important; }
                .course-status-col::before { display: none !important; }
                
                .progress-label-row {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 4px;
                }
            }

            @media (max-width: 480px) {
                [data-testid="stMainBlockContainer"] {
                    padding-inline: 0.625rem !important;
                }
                [data-testid="column"] {
                    min-width: 100%;
                    flex-basis: 100% !important;
                }
                .overview-grid,
                .metric-grid {
                    grid-template-columns: minmax(0, 1fr) !important;
                }
                .info-card,
                .card-panel,
                .course-row {
                    padding: 15px !important;
                    border-radius: 16px;
                }
                .progress-label-row { font-size: 12px; }
            }

            @media (hover: none) {
                .metric-card:hover { transform: none; }
            }

            @media (prefers-reduced-motion: reduce) {
                *, *::before, *::after {
                    scroll-behavior: auto !important;
                    transition-duration: 0.01ms !important;
                    animation-duration: 0.01ms !important;
                    animation-iteration-count: 1 !important;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def draw_premium_progress(label, completed, required, ip=0.0):
    completed = float(completed or 0.0)
    ip = float(ip or 0.0)
    comp_pct = min(100.0, (completed / required) * 100.0) if required > 0 else 100.0
    ip_pct = min(100.0 - comp_pct, (ip / required) * 100.0) if required > 0 else 0.0
    completed_text = format_credit(completed)
    ip_text = format_credit(ip)
    required_text = format_credit(required)

    st.markdown(
        f"""
        <div class="progress-container">
            <div class="progress-label-row">
                <span style="font-weight:600; color:var(--text-color, #121212);">{escape(str(label))}</span>
                <span style="color:var(--text-color, #1f2937);">
                    已得 <b style="color:#0f766e;">{completed_text}</b> 學分 {f'| 修讀中 <b style="color:#2563eb;">{ip_text}</b>' if ip > 0 else ""} / 應修 <b>{required_text}</b> 學分
                </span>
            </div>
            <div class="progress-bar-bg">
                <div style="display:flex; height:100%; width:100%;">
                    <div class="progress-bar-fill" style="width: {comp_pct}%; background: linear-gradient(90deg, #00cd98 0%, #05db9e 100%);"></div>
                    <div class="progress-bar-fill" style="width: {ip_pct}%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);"></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header_card(title, subtitle):
    st.markdown(
        f"""
        <div class="header-card">
            <div class="header-title">{escape(str(title))}</div>
            <div class="header-subtitle">{escape(str(subtitle))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_landing_message():
    st.markdown(
        """
        <div class='hero-callout'>
        <b>📌 三種開始方式</b><br>
        建議直接上傳歷年成績單 PDF；檔案只在目前工作階段中分析。<br>
        也可以登入校務系統即時抓取成績單與指定學期課表。<br><br>
        <small>本工具提供自我檢查，不取代教務處或系所的正式畢業資格審核。</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
