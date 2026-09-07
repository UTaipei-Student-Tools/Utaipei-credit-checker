"""Moksha-inspired vertical workspace; confirmed data and native forms preserved."""
from pathlib import Path
from html import escape

ASSETS = Path(__file__).parent / 'static' / 'dimension'


def workspace_css(*, report_only=False):
    css = (ASSETS / 'workspace.css').read_text(encoding='utf-8')
    return css[css.index('html .snapshot-report,'):] if report_only else css


def navigation_markup():
    return '<div id="dimension-workspace"></div>'


def backdrop_markup():
    return '''<!-- THESIS: Continuous vertical task flow, no dashboard tabs.
OWN-WORLD: Moksha reference; ink, mint, violet, large chapter headings.
STORY: Lookup, configure, import, confirm, review; native controls remain still.
FIRST VIEWPORT: Product title and open time lookup without ornamental labels.
FORM: User-pinned Moksha reference overrides seed c1771078.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md -->
<div class="moksha-depth" aria-hidden="true"><i></i><i></i></div>'''


def section_markup(anchor, title):
    return f'<header class="moksha-chapter" id="{escape(anchor, quote=True)}"><h2>{escape(title)}</h2></header>'
