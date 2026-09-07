"""Dimension-inspired entrance; navigation never clears student session data."""

import base64
from pathlib import Path
import json
import uuid

import streamlit as st

from ui_components import render_html

ASSETS = Path(__file__).resolve().parent / "static" / "dimension"


def _scroll_transition_script(destination, token):
    """One-shot, cancellable scroll; never writes course or confirmation state."""
    selector = '.st-key-dimension_toolbar' if destination == 'workspace' else '.st-key-dimension_cover'
    return '''<script>(() => {
      try {
        const host = window.parent;
        const goingDown = DESTINATION;
        const token = TOKEN;
        if (host.__utaipeiEntranceScroll === token) return;
        const started = host.performance.now();
        const find = () => {
          const target = host.document.querySelector(SELECTOR);
          const scroller = host.document.querySelector('[data-testid="stMain"]');
          if (!target || !scroller) {
            if (host.performance.now() - started < 5000) host.requestAnimationFrame(find);
            return;
          }
          host.__utaipeiEntranceScroll = token;
          const root = host.document.documentElement;
          const toolbar = host.document.querySelector('.st-key-dimension_toolbar');
          if (!goingDown && root.classList.contains('utaipei-cover-away')) {
            const before = toolbar.getBoundingClientRect().top;
            root.classList.remove('utaipei-cover-away');
            scroller.scrollTop += toolbar.getBoundingClientRect().top - before;
          }
          const from = scroller.scrollTop;
          const to = Math.max(0, from + target.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 80);
          const finish = () => {
            if (goingDown && toolbar) {
              const before = toolbar.getBoundingClientRect().top;
              root.classList.add('utaipei-cover-away');
              scroller.scrollTop += toolbar.getBoundingClientRect().top - before;
            }
          };
          if (host.matchMedia('(prefers-reduced-motion: reduce)').matches) { scroller.scrollTop = to; finish(); return; }
          let cancelled = false;
          const cancel = () => { cancelled = true; };
          const events = ['wheel', 'touchstart', 'keydown'];
          events.forEach(name => host.addEventListener(name, cancel, {passive:true, once:true}));
          const begin = host.performance.now();
          const frame = now => {
            const p = Math.min(1, (now - begin) / 850);
            const eased = p < .5 ? 4*p*p*p : 1-Math.pow(-2*p+2,3)/2;
            if (!cancelled) scroller.scrollTop = from + (to-from)*eased;
            if (p < 1 && !cancelled) host.requestAnimationFrame(frame);
            else {
              events.forEach(name => host.removeEventListener(name, cancel));
              if (!cancelled) finish();
            }
          };
          host.requestAnimationFrame(frame);
        };
        host.requestAnimationFrame(find);
      } catch (_) { /* Navigation remains available by ordinary scrolling. */ }
    })();</script>'''.replace('TOKEN', json.dumps(token)).replace('SELECTOR', json.dumps(selector)).replace('DESTINATION', json.dumps(destination == 'workspace'))


def _request_scroll(destination):
    st.session_state['_entrance_scroll'] = (destination, uuid.uuid4().hex)


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
    with st.container(key="dimension_cover"):
        render_html('''<!-- THESIS: a calm entrance before a detailed academic workspace.
OWN-WORLD: Dimension backdrop, thin rules, luminous type, restrained sage controls.
STORY: understand the tool, enter, confirm grades, read the report.
FIRST VIEWPORT: centered name between rules, explanation, two working actions.
FORM: user-supplied Dimension direction overrides seed 94de1b63.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md -->
<section class="dimension-intro" id="cover-content" tabindex="-1" aria-label="北市大畢業通封面">
<div class="dimension-mark" aria-hidden="true">UT</div>
<div class="dimension-title"><h1>北市大畢業通</h1>
<p class="dimension-lead">把修過的課，整理成下一步。</p>
<p class="dimension-description">從一份成績單開始，核對畢業學分，<br>規劃你的主修、輔系與雙主修。</p></div>
</section>''')
        with st.container(key="dimension_actions"):
            start, help_column = st.columns(2)
            if start.button("開始檢查", key="enter_workspace", type="primary", use_container_width=True):
                st.session_state["_workspace_open"] = True
                _request_scroll('workspace')
                st.rerun()
            if help_column.button("使用說明", key="cover_help", use_container_width=True):
                _guide()
        render_html('''<footer class="dimension-footer">
<p>個人規劃與初步核對，正式認定以校方為準。</p>
<p class="dimension-credit">封面改編自 <a href="https://html5up.net/dimension" target="_blank" rel="noopener noreferrer">Dimension / HTML5 UP</a> · <a href="https://creativecommons.org/licenses/by/3.0/" target="_blank" rel="noopener noreferrer">CC BY 3.0</a></p>
</footer>''')
    opened = st.session_state.get("_workspace_open", False)
    if opened:
        with st.container(key="dimension_toolbar"):
            left, right = st.columns([1, 1])
            if left.button("返回封面", key="return_cover", use_container_width=True):
                _request_scroll('cover')
                st.rerun()
            if right.button("使用說明", key="workspace_help", use_container_width=True):
                _guide()
        request = st.session_state.get('_entrance_scroll')
        if request:
            import streamlit.components.v1 as components
            components.html(_scroll_transition_script(*request), height=0, width=0)
    return opened
