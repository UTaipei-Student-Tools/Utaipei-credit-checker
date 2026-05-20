# -*- coding: utf-8 -*-
"""
UTaipei Graduation Credit Checker - Premium Streamlit Web Application
"""

import streamlit as st
import os
import pandas as pd
from scraper import crawl_transcript_pdf
from pdf_parser import parse_transcript_pdf
from credit_engine import evaluate_graduation

# Set page configuration with premium tab title and favicon
st.set_page_config(
    page_title="北市大畢業學分審查系統 | UTaipei Credit Checker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium CSS injection for visual excellence
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
    
    /* Global Styles */
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Noto Sans TC', sans-serif;
    }
    
    /* Main Layout Styling */
    .stApp {
        background: linear-gradient(135deg, #0f1020 0%, #151833 100%);
        color: #e2e8f0;
    }
    
    /* Glassmorphic Sidebar */
    [data-testid="stSidebar"] {
        background-color: rgba(21, 24, 51, 0.9) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
        box-shadow: 5px 0 25px rgba(0, 0, 0, 0.3);
    }
    
    /* Premium Header Card */
    .header-card {
        background: linear-gradient(135deg, rgba(30, 41, 85, 0.8) 0%, rgba(13, 20, 48, 0.8) 100%);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 20px;
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        text-align: center;
    }
    
    .header-title {
        font-size: 32px;
        font-weight: 700;
        background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
    }
    
    .header-subtitle {
        font-size: 16px;
        color: #94a3b8;
        letter-spacing: 1px;
    }
    
    /* Glassmorphic Metrics Card */
    .metric-card {
        background: rgba(30, 41, 85, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: rgba(0, 242, 254, 0.3);
    }
    .metric-value {
        font-size: 38px;
        font-weight: 700;
        margin-top: 5px;
    }
    .metric-label {
        font-size: 14px;
        color: #94a3b8;
        font-weight: 500;
    }
    
    /* Customized Badges and Badged Status */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 50px;
        font-size: 12px;
        font-weight: 600;
        text-align: center;
    }
    .status-completed {
        background-color: rgba(0, 205, 152, 0.15);
        color: #00cd98;
        border: 1px solid rgba(0, 205, 152, 0.3);
    }
    .status-ip {
        background-color: rgba(79, 172, 254, 0.15);
        color: #4facfe;
        border: 1px solid rgba(79, 172, 254, 0.3);
    }
    .status-missing {
        background-color: rgba(255, 56, 96, 0.15);
        color: #ff3860;
        border: 1px solid rgba(255, 56, 96, 0.3);
    }
    
    /* Custom Progress Bar container */
    .progress-container {
        margin-bottom: 15px;
    }
    .progress-label-row {
        display: flex;
        justify-content: space-between;
        font-size: 14px;
        margin-bottom: 6px;
    }
    .progress-bar-bg {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        height: 12px;
        width: 100%;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.03);
    }
    .progress-bar-fill {
        height: 100%;
        border-radius: 10px;
        transition: width 0.8s ease-in-out;
    }
    
    /* Table Enhancements */
    table {
        background-color: rgba(30, 41, 85, 0.2) !important;
        color: #e2e8f0 !important;
        border-radius: 10px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to render a premium progress bar
def draw_premium_progress(label, completed, required, ip=0.0, bar_color="#4facfe"):
    total = completed + ip
    comp_pct = min(100.0, (completed / required) * 100.0) if required > 0 else 100.0
    ip_pct = min(100.0 - comp_pct, (ip / required) * 100.0) if required > 0 else 0.0
    
    st.markdown(f"""
    <div class="progress-container">
        <div class="progress-label-row">
            <span style="font-weight:600; color:#cbd5e1;">{label}</span>
            <span style="color:#94a3b8;">
                已得 <b style="color:#00cd98;">{completed:g}</b> 學分 
                {f'| 修讀中 <b style="color:#4facfe;">{ip:g}</b> ' if ip > 0 else ''}
                / 應修 <b>{required:g}</b> 學分
            </span>
        </div>
        <div class="progress-bar-bg">
            <div style="display:flex; height:100%; width:100%;">
                <div class="progress-bar-fill" style="width: {comp_pct}%; background: linear-gradient(90deg, #00cd98 0%, #05db9e 100%);"></div>
                <div class="progress-bar-fill" style="width: {ip_pct}%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);"></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ----------------- APP SIDEBAR -----------------
with st.sidebar:
    st.markdown("### 🎓 北市大校務整合")
    
    # Selection logic for student major configuration
    st.markdown("---")
    st.markdown("### 🛠️ 學業模組設定")
    major_dept = st.text_input("主修系所", value="地球環境暨生物資源學系", disabled=True)
    
    major_domain = st.selectbox(
        "主修專業領域",
        options=["地球環境", "生命科學"],
        index=0,
        help="地生系分為『地球環境』與『生命科學』專業領域，必修14學分、選修至少20學分。"
    )
    
    program_type = st.selectbox(
        "修課身分設定",
        options=["單主修", "雙主修", "輔系"],
        index=1,
        help="依據114學年度理學院手冊進行跨系學分核算。"
    )
    
    target_dept = st.selectbox(
        "雙主修 / 輔系 目標學系",
        options=["物化系化學組", "物化系物理組", "資科系"],
        index=0,
        disabled=(program_type == "單主修"),
        help="請選擇您修讀的輔雙主修學系組別。"
    )
    
    st.markdown("---")
    st.markdown("### 🔐 學生入口登入")
    student_id = st.text_input("學號 / Account", value="U11310022")
    student_pwd = st.text_input("密碼 / Password", value="jimmy0320", type="password")
    
    col_scrape, col_demo = st.columns(2)
    
    # Keep track of transcript pdf state
    if "transcript_pdf_path" not in st.session_state:
        st.session_state["transcript_pdf_path"] = None
    if "offline_demo" not in st.session_state:
        st.session_state["offline_demo"] = False
        
    with col_scrape:
        if st.button("🚀 實時抓取", use_container_width=True, help="直接登入校務系統抓取歷年成績單PDF"):
            st.session_state["offline_demo"] = False
            with st.spinner("正在登入校務系統並抓取成績單..."):
                try:
                    # Scratch download path inside conversation/scratch structure
                    scr_dir = os.path.dirname(os.path.abspath(__file__))
                    pdf_path = crawl_transcript_pdf(student_id, student_pwd, scr_dir)
                    st.session_state["transcript_pdf_path"] = pdf_path
                    st.success("動態歷年成績抓取成功！")
                except Exception as e:
                    st.error(f"抓取失敗: {str(e)}")
                    
    with col_demo:
        if st.button("📂 載入 Demo", use_container_width=True, help="一鍵載入本機快取之歷年成績單PDF進行展示"):
            scr_dir = os.path.dirname(os.path.abspath(__file__))
            demo_pdf = os.path.join(scr_dir, "student_transcript.pdf")
            if os.path.exists(demo_pdf):
                st.session_state["transcript_pdf_path"] = demo_pdf
                st.session_state["offline_demo"] = True
                st.info("已載入離線展示成績單！")
            else:
                st.error("找不到本機快取的 student_transcript.pdf 檔案！")

# ----------------- MAIN PANEL -----------------
st.markdown("""
<div class="header-card">
    <div class="header-title">🎓 臺北市立大學 歷年畢業學分自我審查系統</div>
    <div class="header-subtitle">114學年度 理學院 大學部學術審查工具 (地生系主修 / 跨系輔雙審查版)</div>
</div>
""", unsafe_allow_html=True)

# Check if transcript PDF is loaded
pdf_path = st.session_state["transcript_pdf_path"]
if not pdf_path:
    # Landing page info before file loading
    st.markdown("""
    ### 🔔 歡迎使用畢業學分審查系統！
    
    本系統專為 **地球環境暨生物資源學系 (地生系)** 學生打造，能夠自動分析您的修課狀態，比對 **114學年度理學院手冊畢業標準**，並支持 **物理組、化學組、資科系** 的輔雙學分精密試算。
    
    > **💡 使用指南:**
    > 1. 在左側側邊欄選擇您的專業領域 (預設為**地球環境**組)，以及是否為**雙主修/輔系**。
    > 2. **實時抓取**: 輸入您的北市大校務系統帳密，點擊「實時抓取」，系統將登入下載最新的成績表並解析。*(系統絕不會儲存您的密碼，所有連線皆為唯讀)*
    > 3. **載入 Demo**: 若您在 Hugging Face Spaces 上體驗，可點擊「載入 Demo」按鈕，直接使用已快取的學生成績表檔案進行一鍵分析展示，無須輸入帳密！
    """)
    
    # Add beautiful placeholder image to wow user
    st.info("👈 請選擇側邊欄的「載入 Demo」或「實時抓取」開始進行您的畢業審查！")
else:
    # 1. Parse and Evaluate Transcript
    try:
        student_info, courses = parse_transcript_pdf(pdf_path)
        
        config = {
            "domain": major_domain,
            "program": program_type,
            "target_dept": target_dept
        }
        
        report = evaluate_graduation(courses, config)
        summary = report["summary"]
        
        # 2. Render Student Header Info Card
        demo_tag = " <span style='font-size:14px; background-color:#5c56e7; padding:2px 8px; border-radius:50px;'>離線 Demo 模式</span>" if st.session_state["offline_demo"] else " <span style='font-size:14px; background-color:#00cd98; padding:2px 8px; border-radius:50px;'>實時抓取模式</span>"
        
        st.markdown(f"""
        <div style="background-color: rgba(30, 41, 85, 0.3); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 15px 25px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div>
                姓名：<b>{student_info['name']}</b> &nbsp;&nbsp;|&nbsp;&nbsp; 
                學號：<b>{student_info['student_id']}</b> &nbsp;&nbsp;|&nbsp;&nbsp; 
                系所：<b>{student_info['department']}</b>
            </div>
            <div>
                身分設定：<b>{program_type}{f' ({target_dept})' if program_type != '單主修' else ''}</b> (<b>{major_domain}領域</b>) &nbsp;&nbsp;
                {demo_tag}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 3. Main Metrics Grid
        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        
        with col_m1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🎓 實得總學分</div>
                <div class="metric-value" style="color: #00cd98;">{summary['total_completed']:g}</div>
                <div style="font-size: 12px; color: #94a3b8; margin-top: 5px;">應修至少 128 / 修讀中 {summary['total_ip']:g}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_m2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🏫 校共同學分</div>
                <div class="metric-value" style="color: #4facfe;">{summary['common_completed']:g}</div>
                <div style="font-size: 12px; color: #94a3b8; margin-top: 5px;">應修至少 28 / 修讀中 {summary['common_ip']:g}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_m3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🔬 主修系專門學分</div>
                <div class="metric-value" style="color: #ffaa00;">{summary['major_completed']:g}</div>
                <div style="font-size: 12px; color: #94a3b8; margin-top: 5px;">應修至少 85 / 修讀中 {summary['major_ip']:g}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_m4:
            target_label = "🌟 輔系學分" if program_type == "輔系" else ("⭐ 雙主修學分" if program_type == "雙主修" else "🚫 無跨系修讀")
            target_color = "#e2e8f0" if program_type == "單主修" else "#a855f7"
            target_req = 20.0 if program_type == "輔系" else (40.0 if program_type == "雙主修" else 0.0)
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{target_label}</div>
                <div class="metric-value" style="color: {target_color};">{summary['target_completed']:g}</div>
                <div style="font-size: 12px; color: #94a3b8; margin-top: 5px;">應修 {target_req:g} / 修讀中 {summary['target_ip']:g}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_m5:
            grad_text = "🎉 已達畢業標準" if summary['graduation_ready'] else "⚠️ 未達畢業標準"
            grad_bg = "rgba(0, 205, 152, 0.15)" if summary['graduation_ready'] else "rgba(255, 56, 96, 0.15)"
            grad_color = "#00cd98" if summary['graduation_ready'] else "#ff3860"
            st.markdown(f"""
            <div class="metric-card" style="background-color: {grad_bg}; border-color: {grad_color};">
                <div class="metric-label" style="color: {grad_color}; font-weight:700;">✨ 審查結果</div>
                <div class="metric-value" style="color: {grad_color}; font-size: 24px; margin-top: 15px;">{grad_text}</div>
                <div style="font-size: 11px; color: #cbd5e1; margin-top: 10px;">含通識/系專必修/輔雙試算</div>
            </div>
            """, unsafe_allow_html=True)
            
        # 4. Tab Navigation for Detailed Reports
        st.markdown("<br>", unsafe_allow_html=True)
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 學業學分概覽", 
            "📚 共同與主修分析", 
            "✨ 輔系/雙主修分析", 
            "📋 歷史課程與匯出"
        ])
        
        # --- TAB 1: OVERVIEW PROGRESS ---
        with tab1:
            st.markdown("### 📊 畢業學分完成進度條")
            
            # Overall credits
            draw_premium_progress("🎓 整體畢業實得總學分", summary["total_completed"], 128.0, summary["total_ip"])
            
            # University Common
            draw_premium_progress("🏫 全校共同課程學分 (英文/國文/通選)", summary["common_completed"], 28.0, summary["common_ip"])
            
            # Major Specialty
            draw_premium_progress("🔬 地生系專門課程學分 (系必修/選修)", summary["major_completed"], 85.0, summary["major_ip"])
            
            # Free Electives
            draw_premium_progress("🔓 自由選修學分 (外系/跨校/輔雙溢流)", summary["free_completed"], 15.0, summary["free_ip"])
            
            if program_type != "單主修":
                target_req = 40.0 if program_type == "雙主修" else 20.0
                draw_premium_progress(f"✨ 跨系所 {target_dept} ({program_type}) 學分", summary["target_completed"], target_req, summary["target_ip"])
                
            st.markdown("---")
            st.markdown("### 🔍 畢業核心必修缺失稽核 (Audits)")
            
            # Compile all missing compulsory courses
            missing_comp = []
            for item in report["common"]["compulsory_missing"]:
                missing_comp.append({"類別": "校共同必修", "科目名稱": item["name"], "學分": item["credit"]})
            for item in report["major"]["dept_compulsory_missing"]:
                missing_comp.append({"類別": "地生系共同必修", "科目名稱": item["name"], "學分": item["credit"]})
            for item in report["major"]["domain_compulsory_missing"]:
                missing_comp.append({"類別": f"{major_domain}領域必修", "科目名稱": item["name"], "學分": item["credit"]})
                
            if missing_comp:
                st.warning("⚠️ 您目前尚有以下核心必修科目未修畢：")
                df_missing = pd.DataFrame(missing_comp)
                st.dataframe(df_missing, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 太棒了！您已修畢/修讀中所有主修及共同必修科目！沒有任何缺漏！")

        # --- TAB 2: COMMON & MAJOR DETAILED ANALYSIS ---
        with tab2:
            st.markdown(f"### 🏫 2.1 全校共同必修課稽核 (已得: {report['common']['compulsory_completed']:g} 學分)")
            
            # Common Compulsory Courses list
            common_comp_list = []
            for c in report["common"]["compulsory_courses"]:
                status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                common_comp_list.append({
                    "科目名稱": c["name"],
                    "修課學年": f"{c['academic_year']}學年",
                    "學分": c["total_credit"],
                    "成績": score,
                    "狀態": status
                })
            for item in report["common"]["compulsory_missing"]:
                common_comp_list.append({
                    "科目名稱": item["name"],
                    "修課學年": "--",
                    "學分": item["credit"],
                    "成績": "--",
                    "狀態": "<span class='status-badge status-missing'>缺漏</span>"
                })
            st.write(pd.DataFrame(common_comp_list).to_html(escape=False, index=False), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 🎨 2.2 通識分類選修域稽核 (16 學分矩陣，四領域各必修至少 4 學分)")
            
            # Render domains in side-by-side columns
            col_ge1, col_ge2 = st.columns(2)
            col_ge3, col_ge4 = st.columns(2)
            
            ge_idx = 0
            for name, data in report["common"]["categories"].items():
                target_col = col_ge1 if ge_idx == 0 else (col_ge2 if ge_idx == 1 else (col_ge3 if ge_idx == 2 else col_ge4))
                ge_idx += 1
                
                with target_col:
                    domain_status = "✅ 達標" if data["completed"] >= 4.0 else ( "🔵 修讀中" if (data["completed"] + data["ip"]) >= 4.0 else "⚠️ 未達標" )
                    status_style = "color:#00cd98;" if data["completed"] >= 4.0 else ("color:#4facfe;" if (data["completed"] + data["ip"]) >= 4.0 else "color:#ff3860;")
                    
                    st.markdown(f"""
                    <div style="background-color: rgba(30, 41, 85, 0.2); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px;">
                        <div style="display:flex; justify-content:space-between; font-weight:600; margin-bottom:10px;">
                            <span>領域: {name}</span>
                            <span style="{status_style}">{domain_status}</span>
                        </div>
                        <div style="font-size:13px; color:#cbd5e1; margin-bottom:8px;">
                            已取得: <b>{data['completed']:g}</b> 學分 / 修讀中: <b>{data['ip']:g}</b> 學分 (應修至少 4 學分)
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if data["courses"]:
                        st.markdown("<div style='font-size:12px; color:#94a3b8; font-weight:600;'>已修課程:</div>", unsafe_allow_html=True)
                        for c in data["courses"]:
                            score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                            status_lbl = "已修" if c["is_completed"] else "修讀中"
                            st.markdown(f"<div style='font-size:11px; margin-left:10px; color:#cbd5e1;'>• {c['name']} ({c['total_credit']:g}學分, 成績:{score}, 狀態:{status_lbl})</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='font-size:11px; color:#ff3860; font-style:italic;'>目前無修課紀錄</div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            st.markdown("---")
            st.markdown(f"### 🔬 2.3 地生系共同必修核算 (已得: {report['major']['dept_compulsory_completed']:g} 學分)")
            
            major_comp_list = []
            for c in report["major"]["dept_compulsory_courses"]:
                status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                major_comp_list.append({
                    "科目名稱": c["name"],
                    "修課學年": f"{c['academic_year']}學年",
                    "學分": c["total_credit"],
                    "成績": score,
                    "狀態": status
                })
            for item in report["major"]["dept_compulsory_missing"]:
                major_comp_list.append({
                    "科目名稱": item["name"],
                    "修課學年": "--",
                    "學分": item["credit"],
                    "成績": "--",
                    "狀態": "<span class='status-badge status-missing'>缺漏</span>"
                })
            st.write(pd.DataFrame(major_comp_list).to_html(escape=False, index=False), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"### 🌍 2.4 主修專業領域必選修稽核 ({major_domain}領域)")
            
            # Domain Compulsory
            st.markdown(f"**A. 領域指定必修 (14 學分，已得: {report['major']['domain_compulsory_completed']:g} 學分)**")
            dom_comp_list = []
            for c in report["major"]["domain_compulsory_courses"]:
                status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                dom_comp_list.append({
                    "科目名稱": c["name"],
                    "修課學年": f"{c['academic_year']}學年",
                    "學分": c["total_credit"],
                    "成績": score,
                    "狀態": status
                })
            for item in report["major"]["domain_compulsory_missing"]:
                dom_comp_list.append({
                    "科目名稱": item["name"],
                    "修課學年": "--",
                    "學分": item["credit"],
                    "成績": "--",
                    "狀態": "<span class='status-badge status-missing'>缺漏</span>"
                })
            st.write(pd.DataFrame(dom_comp_list).to_html(escape=False, index=False), unsafe_allow_html=True)
            
            # Domain Electives
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"**B. 領域選修課程 (應修至少 20 學分，已得: {report['major']['domain_elective_completed']:g} 學分，修讀中: {report['major']['domain_elective_ip']:g} 學分)**")
            if report["major"]["domain_elective_courses"]:
                dom_elec_list = []
                for c in report["major"]["domain_elective_courses"]:
                    status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                    score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                    dom_elec_list.append({
                        "科目名稱": c["name"],
                        "修課學年": f"{c['academic_year']}學年",
                        "學分": c["total_credit"],
                        "成績": score,
                        "狀態": status
                    })
                st.write(pd.DataFrame(dom_elec_list).to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.warning("⚠️ 目前無任何領域選修修讀紀錄。")
                
            # Other Dept Electives
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"**C. 其他本系選修課 (應修 27 學分，包含跨領域/共同選修，已得: {report['major']['other_elective_completed']:g} 學分，修讀中: {report['major']['other_elective_ip']:g} 學分)**")
            if report["major"]["other_elective_courses"]:
                other_elec_list = []
                for c in report["major"]["other_elective_courses"]:
                    status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                    score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                    other_elec_list.append({
                        "科目名稱": c["name"],
                        "修課學年": f"{c['academic_year']}學年",
                        "學分": c["total_credit"],
                        "成績": score,
                        "狀態": status
                    })
                st.write(pd.DataFrame(other_elec_list).to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.warning("⚠️ 目前無其他本系選修修讀紀錄。")

        # --- TAB 3: DOUBLE MAJOR / MINOR DETAILED ANALYSIS ---
        with tab3:
            if program_type == "單主修":
                st.info("💡 您目前的身份設定為「單主修」，因此不需要核算輔系或雙主修學分。若您有雙主修或輔系，請在左側側邊欄更改修課身分設定。")
            else:
                st.markdown(f"### ✨ 3.1 跨系學分審查: {target_dept} ({program_type})")
                
                target_req = 40.0 if program_type == "雙主修" else 20.0
                st.markdown(f"**應修要求: {target_req:g} 學分** (目前已取得: <b style='color:#00cd98;'>{summary['target_completed']:g}</b> 學分，修讀中: <b style='color:#4facfe;'>{summary['target_ip']:g}</b> 學分)")
                
                # Check Basic Core (物化系 16學分必修)
                if "物化系" in target_dept:
                    st.markdown("#### 🅰️ 共同基礎必修學分 (16學分，應用化學/電子物理組皆必修)")
                    basic_list = []
                    for c in report["target"]["basic_core_courses"]:
                        status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                        score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                        basic_list.append({
                            "指定科目名稱": c["name"],
                            "實際修課科目": c["raw_name"],
                            "學分": c["total_credit"],
                            "成績": score,
                            "狀態": status
                        })
                    for item in report["target"]["basic_core_missing"]:
                        basic_list.append({
                            "指定科目名稱": item["name"],
                            "實際修課科目": "--",
                            "學分": item["credit"],
                            "成績": "--",
                            "狀態": "<span class='status-badge status-missing'>缺漏</span>"
                        })
                    st.write(pd.DataFrame(basic_list).to_html(escape=False, index=False), unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"#### 🅱️ 分組專業必修學分 (雙主修應修畢至少 24學分，輔系應修畢至少 4學分)")
                    
                    if report["target"]["compulsory_courses"]:
                        spec_list = []
                        for c in report["target"]["compulsory_courses"]:
                            status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                            score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                            spec_list.append({
                                "實際修課科目": c["name"],
                                "學分": c["total_credit"],
                                "成績": score,
                                "狀態": status
                            })
                        st.write(pd.DataFrame(spec_list).to_html(escape=False, index=False), unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ 目前無任何組別專業必修修課紀錄。")
                        
                elif "資科系" in target_dept:
                    st.markdown("#### 🅰️ 指定專業必修課核算")
                    cs_comp_list = []
                    for c in report["target"]["compulsory_courses"]:
                        status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                        score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                        cs_comp_list.append({
                            "指定科目名稱": c["name"],
                            "實際修課科目": c["raw_name"],
                            "學分": c["total_credit"],
                            "成績": score,
                            "狀態": status
                        })
                    for item in report["target"]["compulsory_missing"]:
                        cs_comp_list.append({
                            "指定科目名稱": item["name"],
                            "實際修課科目": "--",
                            "學分": item["credit"],
                            "成績": "--",
                            "狀態": "<span class='status-badge status-missing'>缺漏</span>"
                        })
                    st.write(pd.DataFrame(cs_comp_list).to_html(escape=False, index=False), unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("#### 🅱️ 其他專門選修課核算")
                    if report["target"]["elective_courses"]:
                        cs_elec_list = []
                        for c in report["target"]["elective_courses"]:
                            status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                            score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                            cs_elec_list.append({
                                "科目名稱": c["name"],
                                "學分": c["total_credit"],
                                "成績": score,
                                "狀態": status
                            })
                        st.write(pd.DataFrame(cs_elec_list).to_html(escape=False, index=False), unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ 目前無其他資科選修課修讀紀錄。")

        # --- TAB 4: FREE ELECTIVES & EXPORT REPORT ---
        with tab4:
            st.markdown(f"### 🔓 4.1 自由選修課程稽核 (已得: {report['free']['completed']:g} 學分)")
            st.markdown("""
            自由選修學分至少 **15 學分**，可包含任何外系、跨校或輔雙溢出之學分。
            *注意:* 依規定，其中至少修畢 **3 學分** 須為理學院內其他學系課程 (院內跨系選修)。
            """)
            
            # Print science college cross-dept summary
            cross_sat = "✅ 達標" if report["free"]["science_college_cross_credits"] >= 3.0 else "⚠️ 未達標"
            cross_color = "#00cd98" if report["free"]["science_college_cross_credits"] >= 3.0 else "#ff3860"
            st.markdown(f"理學院院內跨系課程已修取得：<b style='color:{cross_color}; font-size:16px;'>{report['free']['science_college_cross_credits']:g}</b> 學分 (應修至少 3 學分) — <b style='color:{cross_color};'>{cross_sat}</b>")
            
            if report["free"]["courses"]:
                free_list = []
                for c in report["free"]["courses"]:
                    status = "<span class='status-badge status-completed'>已修畢</span>" if c["is_completed"] else "<span class='status-badge status-ip'>修讀中</span>"
                    score = c["sem1_score"] if c["sem1_score"] != "--" else c["sem2_score"]
                    is_cross = "是" if c in report["free"]["science_college_cross_courses"] else "否"
                    free_list.append({
                        "科目名稱": c["name"],
                        "原始修課名稱": c["raw_name"],
                        "學分": c["total_credit"],
                        "成績": score,
                        "院內跨系": is_cross,
                        "狀態": status
                    })
                st.write(pd.DataFrame(free_list).to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.info("💡 目前無任何自由選修學分紀錄 (或多餘學分尚未溢流至此)。")
                
            st.markdown("---")
            st.markdown("### 📅 4.2 歷年修課按學期精緻整理")
            st.markdown("系統自動將您的所有歷年課程按學年度與學期進行精緻分類整理，便於快速核對每學期的修課狀態與學分數。")
            
            # Group courses by semesters
            semester_groups = {
                "113學年度 第一學期 (大一上)": [],
                "113學年度 第二學期 (大一下)": [],
                "114學年度 第一學期 (大二上)": [],
                "114學年度 第二學期 (大二下)": []
            }
            
            # Helper to check if score represents completed course
            def is_completed_score(score):
                if not score or score == "--" or score == "未":
                    return False
                if score in ["P", "抵", "免"]:
                    return True
                if score in ["F", "停", "W"]:
                    return False
                try:
                    return float(score) >= 60
                except ValueError:
                    return False
                    
            for c in courses:
                # Semester 1 (Upper semester)
                if c["sem1_credit"] or (c["sem1_score"] and c["sem1_score"] != "--"):
                    sem_key = "113學年度 第一學期 (大一上)" if c["academic_year"] == "113" else "114學年度 第一學期 (大二上)"
                    status = "已修畢" if is_completed_score(c["sem1_score"]) else ("在修中" if c["sem1_score"] == "未" else "未完成")
                    semester_groups[sem_key].append({
                        "科目名稱": c["name"],
                        "科目屬性": c["type"],
                        "學分": c["sem1_credit"] if c["sem1_credit"] else "0",
                        "成績/狀態": c["sem1_score"] if c["sem1_score"] else "--",
                        "修課狀態": status
                    })
                # Semester 2 (Lower semester)
                if c["sem2_credit"] or (c["sem2_score"] and c["sem2_score"] != "--"):
                    sem_key = "113學年度 第二學期 (大一下)" if c["academic_year"] == "113" else "114學年度 第二學期 (大二下)"
                    status = "已修畢" if is_completed_score(c["sem2_score"]) else ("在修中" if c["sem2_score"] == "未" else "未完成")
                    semester_groups[sem_key].append({
                        "科目名稱": c["name"],
                        "科目屬性": c["type"],
                        "學分": c["sem2_credit"] if c["sem2_credit"] else "0",
                        "成績/狀態": c["sem2_score"] if c["sem2_score"] else "--",
                        "修課狀態": status
                    })
            
            # Render semester expanders
            for sem_name, sem_courses in semester_groups.items():
                if sem_courses:
                    # Calculate completed academic credits in this specific semester
                    sem_comp_cred = 0.0
                    for sc in sem_courses:
                        if sc["修課狀態"] == "已修畢":
                            try:
                                sem_comp_cred += float(sc["學分"])
                            except ValueError:
                                pass
                                
                    with st.expander(f"📅 {sem_name} &nbsp;&nbsp;|&nbsp;&nbsp; 取得學分：{sem_comp_cred:g} 學分", expanded=(sem_name.startswith("114"))):
                        # Convert to DataFrame and add gorgeous badges
                        df_sem = pd.DataFrame(sem_courses)
                        sem_list_html = []
                        for _, row in df_sem.iterrows():
                            badge_style = "status-completed" if row["修課狀態"] == "已修畢" else ("status-ip" if row["修課狀態"] == "在修中" else "status-missing")
                            status_badge = f"<span class='status-badge {badge_style}'>{row['修課狀態']}</span>"
                            sem_list_html.append({
                                "科目名稱": row["科目名稱"],
                                "科目屬性": row["科目屬性"],
                                "學分": f"{float(row['學分']):g}" if row["學分"] else "0",
                                "成績/狀態": row["成績/狀態"],
                                "修課狀態": status_badge
                            })
                        st.write(pd.DataFrame(sem_list_html).to_html(escape=False, index=False), unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("### 📋 4.3 成績總表匯出與歷史紀錄 (Parsed Courses)")
            
            # Provide full dataframe with search
            df_full = pd.DataFrame(courses)[["name", "type", "academic_year", "total_credit", "is_completed", "is_in_progress"]]
            df_full.columns = ["科目名稱", "科目屬性", "修課學年", "學分數", "是否完成", "修讀中"]
            st.dataframe(df_full, use_container_width=True)
            
            # Excel export logic
            csv = df_full.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 匯出學分審查試算表 (CSV)",
                data=csv,
                file_name=f"UTaipei_Credit_Audit_{student_info['name']}_{student_info['student_id']}.csv",
                mime="text/csv",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"解析或學分計算出錯: {str(e)}")
        st.exception(e)
