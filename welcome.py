"""Dimension-inspired entrance; navigation never clears student session data."""

import base64
from pathlib import Path

import streamlit as st

from ui_components import render_html

ASSETS = Path(__file__).resolve().parent / "static" / "dimension"


def _stylesheet():
    background = base64.b64encode((ASSETS / "bg.jpg").read_bytes()).decode("ascii")
    return (ASSETS / "theme.css").read_text(encoding="utf-8").replace("__BACKGROUND__", background)


@st.dialog("使用前，先了解這些")
def _guide():
    st.markdown("""### 從成績單到學分進度
1. **選擇手冊與主修**：確認入學年度、系所及規劃類型，再套用設定。
2. **載入成績**：上傳歷年成績單 PDF，也可以使用選用的校務系統登入。
3. **核對後查看報告**：確認解析的課程資料，再查看學分進度及匯出結果。

### 資料與判定
請勿在共用電腦留下下載的成績報告。返回封面不會清除本次資料；要移除資料，請使用工作區的「清除目前資料」。

本工具提供個人規劃與初步核對，不取代教務處、系所或學分審查會議的正式認定。缺少依據的項目會保留未確認狀態。
""")


def render_entrance():
    """Return True when the application workspace should render."""
    render_html("<style>" + _stylesheet() + "</style>")
    if st.session_state.get("_workspace_open", False):
        with st.container(key="dimension_toolbar"):
            left, right = st.columns([1, 1])
            if left.button("返回封面", key="return_cover", use_container_width=True):
                st.session_state["_workspace_open"] = False
                st.rerun()
            if right.button("使用說明", key="workspace_help", use_container_width=True):
                _guide()
        return True

    with st.container(key="dimension_cover"):
        render_html('''<!-- THESIS: a calm entrance before a detailed academic workspace.
OWN-WORLD: Dimension backdrop, thin rules, luminous type, restrained sage controls.
STORY: understand the tool, enter, confirm grades, read the report.
FIRST VIEWPORT: centered name between rules, explanation, two working actions.
FORM: user-supplied Dimension direction overrides seed 94de1b63.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md -->
<section class="dimension-intro" id="main-content" tabindex="-1" aria-label="北市大畢業通封面">
<div class="dimension-mark" aria-hidden="true">UT</div>
<div class="dimension-title"><h1>北市大畢業通</h1>
<p class="dimension-lead">把修過的課，整理成下一步。</p>
<p class="dimension-description">從一份成績單開始，核對畢業學分，<br>規劃你的主修、輔系與雙主修。</p></div>
</section>''')
        with st.container(key="dimension_actions"):
            start, help_column = st.columns(2)
            if start.button("開始檢查", key="enter_workspace", type="primary", use_container_width=True):
                st.session_state["_workspace_open"] = True
                st.rerun()
            if help_column.button("使用說明", key="cover_help", use_container_width=True):
                _guide()
        render_html('''<footer class="dimension-footer">
<p>個人規劃與初步核對，正式認定以校方為準。</p>
<p class="dimension-credit">封面改編自 <a href="https://html5up.net/dimension" target="_blank" rel="noopener noreferrer">Dimension / HTML5 UP</a> · <a href="https://creativecommons.org/licenses/by/3.0/" target="_blank" rel="noopener noreferrer">CC BY 3.0</a></p>
</footer>''')
    return False
