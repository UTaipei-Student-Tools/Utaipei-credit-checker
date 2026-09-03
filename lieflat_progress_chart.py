"""Accessible, dependency-free Lieflat F5 Tick Rows progress renderer.

The renderer is intentionally independent from Streamlit.  It returns one
HTML fragment containing an SVG and a visually-hidden table so the same
component can be embedded in the report UI or exported as HTML.
"""

from __future__ import annotations

import html
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

SLOT_COUNT = 20
"""The F5 queue has exactly twenty threshold slots (one slot = five percent)."""

_DEFAULT_SOURCE = "畢業門檻與成績單分析"
_VIEWBOX_WIDTH = 760
_ROW_TOP = 58
_ROW_GAP = 44
_TRACK_X = 224
_SLOT_WIDTH = 16
_SLOT_GAP = 5
_TRACK_WIDTH = SLOT_COUNT * _SLOT_WIDTH + (SLOT_COUNT - 1) * _SLOT_GAP
_VALUE_X = _TRACK_X + _TRACK_WIDTH + 28


@dataclass(frozen=True)
class _Number:
    """A finite number plus the display-safe representation of its input."""

    value: float | None
    display: str


@dataclass(frozen=True)
class _ProgressRow:
    label: str
    completed: _Number
    required: _Number
    unit: str
    ratio: float
    gap: float | None
    status: str = ""


def _escape(value: Any) -> str:
    """Escape text and attribute values in the returned HTML fragment."""

    return html.escape(str(value), quote=True)


def _display_number(value: Decimal) -> str:
    """Render a finite Decimal without exposing arbitrary input text.

    Fifteen significant digits retain useful student-record precision while
    avoiding unbounded markup for hostile or accidental giant numbers.
    """

    rendered = format(value, ".15g")
    if rendered in {"-0", "-0.0", "0.0"}:
        return "0"
    if "e" not in rendered.lower() and "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _coerce_number(raw: Any) -> _Number:
    """Coerce a user value to a finite float and safe display text.

    Invalid, NaN, and infinite inputs are represented as ``無效``.  They never
    become SVG attributes, CSS values, or unescaped markup.
    """

    if isinstance(raw, bool) or raw is None:
        return _Number(None, "無效")
    try:
        decimal = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return _Number(None, "無效")
    if not decimal.is_finite():
        return _Number(None, "無效")
    try:
        numeric = float(decimal)
    except (OverflowError, ValueError):
        return _Number(None, "無效")
    if not math.isfinite(numeric):
        return _Number(None, "無效")
    return _Number(numeric, _display_number(decimal))


def _text_value(raw: Any) -> str:
    """Convert optional row text to a predictable string."""

    return "" if raw is None else str(raw)


_F5_STATUS_LABELS = {"PASS": "已通過", "FAIL": "未通過", "UNKNOWN": "待確認"}


def _f5_status(raw: Any) -> str:
    normalized = _text_value(raw).strip().upper().replace("-", "_").replace(" ", "_")
    if normalized in {"COMPLETED", "COMPLETE", "RESOLVED"}:
        normalized = "PASS"
    elif normalized in {"MISSING", "NOT_ATTEMPTED"}:
        normalized = "FAIL"
    return normalized if normalized in _F5_STATUS_LABELS else "UNKNOWN"


def _normalise_rows(rows: Iterable[Mapping[str, Any]]) -> list[_ProgressRow]:
    try:
        source_rows = list(rows)
    except TypeError as exc:
        raise TypeError("rows 必須是由 mapping 組成的可疊代資料") from exc
    if len(source_rows) > 8:
        raise ValueError("progress renderer 一次最多接受 8 筆資料")

    normalised: list[_ProgressRow] = []
    for index, raw_row in enumerate(source_rows):
        if not isinstance(raw_row, Mapping):
            raise TypeError(f"rows[{index}] 必須是 mapping")
        completed = _coerce_number(raw_row.get("completed"))
        required = _coerce_number(raw_row.get("required"))
        ratio = 0.0
        gap: float | None = None
        if completed.value is not None and required.value is not None and required.value > 0:
            ratio = max(0.0, min(1.0, completed.value / required.value))
            gap = abs(required.value - completed.value)
        normalised.append(
            _ProgressRow(
                label=_text_value(raw_row.get("label")),
                completed=completed,
                required=required,
                unit=_text_value(raw_row.get("unit")),
                ratio=ratio,
                gap=gap,
            )
        )
    return normalised


def _conclusion(rows: list[_ProgressRow]) -> tuple[str, int | None]:
    candidates = [(index, row) for index, row in enumerate(rows) if row.gap is not None]
    if not candidates:
        if rows:
            return "目前沒有可計算的畢業門檻進度", None
        return "目前尚未有可比較的畢業門檻", None

    focus_index, focus_row = max(candidates, key=lambda item: item[1].gap or 0.0)
    if (focus_row.gap or 0.0) == 0:
        return "各項畢業門檻目前都已達成", None
    label = focus_row.label or "該項目"
    return f"目前差距最大的是「{label}」", focus_index


def _row_value(row: _ProgressRow) -> str:
    values = f"{row.completed.display} / {row.required.display}"
    return f"{values} {row.unit}".rstrip() if row.unit else values


def _progress_percent(row: _ProgressRow) -> str:
    if row.gap is None:
        return "無法計算"
    return f"{row.ratio * 100:.1f}%"


def _render_ticks(row: _ProgressRow, row_index: int) -> str:
    """Render the F5 queue: guide track followed by twenty countable ticks."""

    y = _ROW_TOP + row_index * _ROW_GAP
    track_y = y + 9
    parts = [
        f'<line class="lf-guide-track" x1="{_TRACK_X}" y1="{track_y}" '
        f'x2="{_TRACK_X + _TRACK_WIDTH}" y2="{track_y}" aria-hidden="true" />'
    ]
    for slot in range(SLOT_COUNT):
        x = _TRACK_X + slot * (_SLOT_WIDTH + _SLOT_GAP) + _SLOT_WIDTH / 2
        slot_start = slot / SLOT_COUNT
        slot_fill = max(0.0, min(1.0, (row.ratio - slot_start) * SLOT_COUNT))
        fill_x2 = x - _SLOT_WIDTH / 2 + _SLOT_WIDTH * slot_fill
        # data-slot is deliberately attached to one group per slot: tests and
        # assistive tooling can count the same twenty units as the reader.
        fill_line = ""
        if slot_fill > 0:
            fill_line = (
                f'<line class="lf-tick-fill" x1="{x - _SLOT_WIDTH / 2:.1f}" y1="{track_y}" '
                f'x2="{fill_x2:.1f}" y2="{track_y}" />'
            )
        parts.append(
            f'<g class="lf-tick" data-slot="{slot}" data-fill="{slot_fill:.6f}" '
            f'aria-hidden="true"><line class="lf-tick-track" x1="{x - _SLOT_WIDTH / 2:.1f}" '
            f'y1="{track_y}" x2="{x + _SLOT_WIDTH / 2:.1f}" y2="{track_y}" />{fill_line}</g>'
        )
    return "".join(parts)


def render_progress_chart(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = _DEFAULT_SOURCE,
) -> str:
    """Return an accessible F5-style progress/gap HTML fragment.

    Parameters
    ----------
    rows:
        Up to eight mappings with ``label``, ``completed``, ``required``, and
        ``unit`` fields.  Invalid numeric values render as ``無效`` and have
        no visual fill.  A non-positive requirement has a zero visual fill
        and a ``無法計算`` percentage in the text fallback.
    source:
        Source text shown below the visualization; it is HTML-escaped.
    """

    data = _normalise_rows(rows)
    title, focus_index = _conclusion(data)
    escaped_title = _escape(title)
    escaped_source = _escape(source or _DEFAULT_SOURCE)
    chart_height = max(152, _ROW_TOP + max(len(data), 1) * _ROW_GAP + 48)
    aria_label = _escape(f"{title}；共 {len(data)} 項門檻，每格代表 5% 的門檻進度")

    svg_parts = [
        f'<svg class="lf-progress-svg" viewBox="0 0 {_VIEWBOX_WIDTH} {chart_height}" '
        f'preserveAspectRatio="xMinYMin meet" role="img" aria-label="{aria_label}">',
        f"<title>{escaped_title}</title>",
        '<desc>每一列有二十個等距刻度；每個刻度代表該列門檻的百分之五。</desc>',
    ]
    if data:
        for index, row in enumerate(data):
            y = _ROW_TOP + index * _ROW_GAP
            row_class = "lf-row lf-row--focus" if index == focus_index else "lf-row"
            delay = index * 60
            escaped_label = _escape(row.label or "未命名項目")
            escaped_value = _escape(_row_value(row))
            label_length = len(row.label)
            label_sizing = (
                ' textLength="190" lengthAdjust="spacingAndGlyphs"' if label_length > 13 else ""
            )
            value_sizing = (
                ' textLength="118" lengthAdjust="spacingAndGlyphs"' if len(_row_value(row)) > 16 else ""
            )
            svg_parts.append(
                f'<g class="{row_class}" style="--lf-delay:{delay}ms" data-progress="{row.ratio:.6f}">'
                f'<title>{escaped_label}：{escaped_value}，目前 {_escape(_progress_percent(row))}</title>'
                f'<text class="lf-row-label" x="14" y="{y + 13}"{label_sizing}>{escaped_label}</text>'
                f'{_render_ticks(row, index)}'
                f'<text class="lf-row-value" x="{_VALUE_X}" y="{y + 13}"{value_sizing}>{escaped_value}</text>'
                "</g>"
            )
        axis_y = _ROW_TOP + len(data) * _ROW_GAP + 8
        for percent, slot in ((0, 0), (25, 5), (50, 10), (75, 15), (100, 20)):
            x = _TRACK_X + slot * (_SLOT_WIDTH + _SLOT_GAP) - (_SLOT_GAP / 2 if slot else 0)
            anchor = "middle"
            svg_parts.append(
                f'<text class="lf-axis-label" x="{x:.1f}" y="{axis_y}" text-anchor="{anchor}">{percent}%</text>'
            )
    else:
        empty_y = chart_height / 2
        svg_parts.append(
            f'<text class="lf-empty" x="{_VIEWBOX_WIDTH / 2}" y="{empty_y:.1f}" '
            f'text-anchor="middle">尚未提供門檻資料</text>'
        )
    svg_parts.append("</svg>")

    table_rows: list[str] = []
    if data:
        for row in data:
            table_rows.append(
                "<tr>"
                f'<th scope="row">{_escape(row.label or "未命名項目")}</th>'
                f"<td>{_escape(row.completed.display)}</td>"
                f"<td>{_escape(row.required.display)}</td>"
                f'<td>{_escape(row.unit or "—")}</td>'
                f"<td>{_escape(_progress_percent(row))}</td>"
                "</tr>"
            )
    else:
        table_rows.append('<tr><td colspan="5">沒有資料</td></tr>')

    css = """
    .lieflat-progress-chart {
      --lf-surface: #F7F2EB;
      --lf-text: #081F5C;
      --lf-muted: #334EAC;
      --lf-track: #D0E3FF;
      --lf-grid: #BAD6EB;
      --lf-blue: #334EAC;
      --lf-blue-soft: #7096D1;
      --lf-blue-strong: #081F5C;
      --lf-accent: #9A5B00;
      --lf-focus-ring: #081F5C;
      background: var(--lf-surface, #F7F2EB);
      color: var(--lf-text, #081F5C);
      color-scheme: light dark;
      width: 100%;
      max-width: 100%;
      min-width: 0;
      padding: 1.25rem 1rem 1rem;
      box-sizing: border-box;
      font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
      overflow-wrap: anywhere;
    }
    @media (prefers-color-scheme: dark) {
      .lieflat-progress-chart {
        --lf-surface: #081F5C;
        --lf-text: #F7F2EB;
        --lf-muted: #D0E3FF;
        --lf-track: #334EAC;
        --lf-grid: #7096D1;
        --lf-blue: #BAD6EB;
        --lf-blue-soft: #7096D1;
        --lf-blue-strong: #F7F2EB;
        --lf-accent: #F5C276;
        --lf-focus-ring: #F7F2EB;
      }
    }
    html[data-theme="dark"] .lieflat-progress-chart,
    body[data-theme="dark"] .lieflat-progress-chart,
    .stApp[data-theme="dark"] .lieflat-progress-chart,
    [data-testid="stAppViewContainer"][data-theme="dark"] .lieflat-progress-chart,
    [data-streamlit-theme="dark"] .lieflat-progress-chart,
    html:has(body[data-theme="dark"]) .lieflat-progress-chart,
    html:has(.stApp[data-theme="dark"]) .lieflat-progress-chart,
    html:has([data-streamlit-theme="dark"]) .lieflat-progress-chart {
      --lf-surface: #081F5C;
      --lf-text: #F7F2EB;
      --lf-muted: #D0E3FF;
      --lf-track: #334EAC;
      --lf-grid: #7096D1;
      --lf-blue: #BAD6EB;
      --lf-blue-soft: #7096D1;
      --lf-blue-strong: #F7F2EB;
      --lf-accent: #F5C276;
      --lf-focus-ring: #F7F2EB;
    }
    html[data-utaipei-theme="light"] .lieflat-progress-chart {
      --lf-surface: #FFFFFF;
      --lf-text: #0F172A;
      --lf-muted: #475569;
      --lf-track: #E2E8F0;
      --lf-grid: #CBD5E1;
      --lf-blue: #1E3A5F;
      --lf-blue-soft: #2563EB;
      --lf-blue-strong: #1E3A5F;
      --lf-accent: #2563EB;
      --lf-focus-ring: #2563EB;
    }
    html[data-utaipei-theme="dark"] .lieflat-progress-chart {
      --lf-surface: #111827;
      --lf-text: #F8FAFC;
      --lf-muted: #CBD5E1;
      --lf-track: #172033;
      --lf-grid: #334155;
      --lf-blue: #60A5FA;
      --lf-blue-soft: #60A5FA;
      --lf-blue-strong: #60A5FA;
      --lf-accent: #60A5FA;
      --lf-focus-ring: #60A5FA;
    }
    .lieflat-progress-chart *, .lieflat-progress-chart *::before, .lieflat-progress-chart *::after {
      box-sizing: border-box;
    }
    .lf-title {
      color: var(--lf-text, #081F5C);
      font-size: clamp(1rem, 2.3vw, 1.25rem);
      line-height: 1.45;
      margin: 0;
      font-weight: 800;
    }
    .lf-subtitle, .lf-source {
      color: var(--lf-muted, #334EAC);
      font-size: .82rem;
      line-height: 1.65;
      margin: .3rem 0 0;
    }
    .lf-legend {
      align-items: center;
      display: flex;
      flex-wrap: wrap;
      gap: .7rem 1rem;
      margin: .8rem 0 .3rem;
      color: var(--lf-muted, #334EAC);
      font-size: .75rem;
    }
    .lf-legend-item { align-items: center; display: inline-flex; gap: .35rem; }
    .lf-swatch { border-radius: 999px; display: inline-block; height: .7rem; width: 1.25rem; }
    .lf-swatch--blue { background: var(--lf-blue, #334EAC); }
    .lf-swatch--accent { background: var(--lf-accent, #9A5B00); }
    .lf-chart-scroll {
      max-width: 100%;
      min-width: 0;
      overflow-x: auto;
      overscroll-behavior-inline: contain;
      padding: .25rem 0 .15rem;
      scrollbar-width: thin;
    }
    .lf-progress-svg { display: block; height: auto; min-width: 700px; width: 100%; }
    .lf-row { animation: lf-row-in .48s ease-out both; animation-delay: var(--lf-delay, 0ms); }
    .lf-row-label, .lf-row-value { fill: var(--lf-text, #081F5C); font-size: 12px; font-weight: 700; }
    .lf-row-value { font-variant-numeric: tabular-nums; font-weight: 800; }
    .lf-row--focus .lf-row-label, .lf-row--focus .lf-row-value { fill: var(--lf-accent, #9A5B00); }
    .lf-guide-track { stroke: var(--lf-track, #D0E3FF); stroke-linecap: round; stroke-width: 5; }
    .lf-tick-track { stroke: var(--lf-grid, #BAD6EB); stroke-linecap: round; stroke-width: 6; }
    .lf-tick-fill { stroke: var(--lf-blue, #334EAC); stroke-linecap: round; stroke-width: 6; }
    .lf-row--focus .lf-tick-fill { stroke: var(--lf-accent, #9A5B00); }
    .lf-axis-label { fill: var(--lf-muted, #334EAC); font-size: 10px; font-variant-numeric: tabular-nums; }
    .lf-empty { fill: var(--lf-muted, #334EAC); font-size: 13px; font-weight: 700; }
    .lf-source { border-top: 1px solid var(--lf-grid, #BAD6EB); margin-top: .45rem; padding-top: .55rem; }
    .lf-sr-only {
      border: 0; clip: rect(0 0 0 0); height: 1px; margin: -1px; overflow: hidden;
      padding: 0; position: absolute; white-space: nowrap; width: 1px;
    }
    @keyframes lf-row-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) {
      .lf-row { animation: none; }
    }
    @media (max-width: 600px) {
      .lieflat-progress-chart { padding-inline: .65rem; }
      .lf-subtitle, .lf-source { font-size: .78rem; }
      .lf-legend { font-size: .72rem; }
      .lf-chart-scroll { margin-inline: -.2rem; }
    }
    """

    return (
        f'<section class="lieflat-progress-chart" aria-label="{aria_label}">'
        f"<style>{css}</style>"
        f'<h2 class="lf-title">{escaped_title}</h2>'
        '<p class="lf-subtitle">每一格代表該項門檻的 5% · 藍色格 = 已完成 · 琥珀色 = 最大差距</p>'
        '<div class="lf-legend" aria-label="圖例">'
        '<span class="lf-legend-item"><span class="lf-swatch lf-swatch--blue" aria-hidden="true"></span>已完成進度</span>'
        '<span class="lf-legend-item"><span class="lf-swatch lf-swatch--accent" aria-hidden="true"></span>最大差距</span>'
        "</div>"
        f'<div class="lf-chart-scroll" tabindex="0" aria-label="進度明細，可左右滑動閱讀">{"".join(svg_parts)}</div>'
        f'<p class="lf-source">資料來源：{escaped_source}</p>'
        '<div class="lf-sr-only">'
        '<table class="lf-data-table" aria-label="畢業門檻進度文字版">'
        '<caption>畢業門檻進度明細</caption>'
        "<thead><tr><th scope=\"col\">項目</th><th scope=\"col\">已完成</th>"
        "<th scope=\"col\">門檻</th><th scope=\"col\">單位</th><th scope=\"col\">視覺進度</th></tr></thead>"
        f'<tbody>{"".join(table_rows)}</tbody></table>'
        "</div>"
        "</section>"
    )


def render_lieflat_progress_chart(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = _DEFAULT_SOURCE,
) -> str:
    """Descriptive alias for callers that prefer the renderer's full name."""

    return render_progress_chart(rows, source=source)


def _chart_ratio(completed: _Number, required: _Number) -> float | None:
    if completed.value is None or required.value is None or required.value <= 0:
        return None
    return max(0.0, min(1.0, completed.value / required.value))


def _chart_source(source: Any) -> str:
    return _escape(source or _DEFAULT_SOURCE)


def _chart_css(prefix: str) -> str:
    """Return responsive Lieflat CSS for snapshot-owned charts.

    The legacy F5 renderer above intentionally keeps its historical scrolling
    contract for existing callers.  Snapshot consumers use these responsive
    variants so the page never acquires a chart-level fixed width or a second
    horizontal scrolling surface.
    """


    safe_prefix = _escape(prefix)
    return f"""
    .{safe_prefix} {{
      --lf-surface: #FFFFFF;
      --lf-text: #0F172A;
      --lf-muted: #475569;
      --lf-grid: #CBD5E1;
      --lf-data: #1E3A5F;
      --lf-accent: #2563EB;
      background: var(--lf-surface);
      color: var(--lf-text);
      display: block;
      font-family: \"Noto Sans TC\", \"PingFang TC\", \"Microsoft JhengHei\", sans-serif;
      max-width: 100%;
      overflow-wrap: anywhere;
      padding: 1rem 0;
    }}
    .{safe_prefix} *, .{safe_prefix} *::before, .{safe_prefix} *::after {{ box-sizing: border-box; }}
    .{safe_prefix} .lf-chart-svg {{ display: block; max-width: 100%; width: 100%; }}
    .{safe_prefix} .lf-chart-title {{ color: var(--lf-text); font-size: 1rem; font-weight: 800; line-height: 1.45; margin: 0; }}
    .{safe_prefix} .lf-chart-subtitle, .{safe_prefix} .lf-chart-source {{ color: var(--lf-muted); font-size: .8rem; line-height: 1.65; margin: .3rem 0 0; }}
    .{safe_prefix} .lf-chart-source {{ border-top: 1px solid var(--lf-grid); padding-top: .55rem; }}
    .{safe_prefix} .lf-legend {{ color: var(--lf-muted); display: flex; flex-wrap: wrap; font-size: .75rem; gap: .75rem 1rem; list-style: none; margin: .75rem 0 .25rem; padding: 0; }}
    .{safe_prefix} .lf-legend-item {{ align-items: center; display: inline-flex; gap: .35rem; }}
    .{safe_prefix} .lf-swatch {{ aspect-ratio: 1.86; border-radius: 999px; display: inline-block; inline-size: 1.3rem; }}
    .{safe_prefix} .lf-swatch--data {{ background: var(--lf-data); }}
    .{safe_prefix} .lf-swatch--accent {{ background: var(--lf-accent); }}
    .{safe_prefix} .lf-swatch--muted {{ background: var(--lf-grid); }}
    .{safe_prefix} .lf-data-table {{ border-collapse: collapse; color: var(--lf-text); font-size: .82rem; margin-top: .65rem; width: 100%; }}
    .{safe_prefix} .lf-data-table th, .{safe_prefix} .lf-data-table td {{ border-bottom: 1px solid var(--lf-grid); padding: .45rem .35rem; text-align: start; vertical-align: top; }}
    .{safe_prefix} .lf-data-table th {{ font-weight: 800; }}
    .{safe_prefix} .lf-details {{ border-top: 1px solid var(--lf-grid); margin-top: .65rem; }}
    .{safe_prefix} .lf-details summary {{ color: var(--lf-data); cursor: pointer; font-weight: 750; padding: .7rem 0; }}
    .{safe_prefix} .lf-sr-only {{ border: 0; clip-path: inset(50%); margin: -1px; overflow: hidden; padding: 0; position: absolute; white-space: nowrap; }}
    @media (prefers-reduced-motion: reduce) {{ .{safe_prefix} * {{ animation: none !important; transition: none !important; }} }}
    @media (prefers-color-scheme: dark) {{
      .{safe_prefix} {{ --lf-surface: #111827; --lf-text: #F8FAFC; --lf-muted: #CBD5E1; --lf-grid: #334155; --lf-data: #60A5FA; --lf-accent: #93C5FD; }}
    }}
    html[data-theme=\"light\"] .{safe_prefix}, body[data-theme=\"light\"] .{safe_prefix} {{ --lf-surface: #FFFFFF; --lf-text: #0F172A; --lf-muted: #475569; --lf-grid: #CBD5E1; --lf-data: #1E3A5F; --lf-accent: #2563EB; }}
    html[data-theme=\"dark\"] .{safe_prefix}, body[data-theme=\"dark\"] .{safe_prefix} {{ --lf-surface: #111827; --lf-text: #F8FAFC; --lf-muted: #CBD5E1; --lf-grid: #334155; --lf-data: #60A5FA; --lf-accent: #93C5FD; }}
    html[data-utaipei-theme=\"light\"] .{safe_prefix} {{ --lf-surface: #FFFFFF; --lf-text: #0F172A; --lf-muted: #475569; --lf-grid: #CBD5E1; --lf-data: #1E3A5F; --lf-accent: #2563EB; }}
    html[data-utaipei-theme=\"dark\"] .{safe_prefix} {{ --lf-surface: #111827; --lf-text: #F8FAFC; --lf-muted: #CBD5E1; --lf-grid: #334155; --lf-data: #60A5FA; --lf-accent: #60A5FA; }}
    """


def render_chart_unavailable(
    chart_id: str,
    reason: Any,
    *,
    source: str = _DEFAULT_SOURCE,
    title: str = "圖表暫不可用",
) -> str:
    """Render an explicit non-chart state for unsafe/incomplete datasets."""

    safe_id = _escape(chart_id or "chart")
    safe_title = _escape(title or "圖表暫不可用")
    safe_reason = _escape(reason or "資料不足／需人工確認")
    return (
        f'<section class="lf-chart-unavailable" data-chart-id="{safe_id}" data-available="false" aria-label="{safe_title}">'
        f'<h3 class="lf-chart-title">{safe_title}</h3>'
        f'<p class="lf-chart-unavailable-reason">{safe_reason}</p>'
        f'<p class="lf-chart-source">資料來源：{_chart_source(source)}</p></section>'
    )


def render_tick_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = _DEFAULT_SOURCE,
    title: str = "各項畢業門檻進度",
) -> str:
    """Render a responsive F5 Tick Rows chart for snapshot consumers.

    Unlike :func:`render_progress_chart`, this snapshot-era variant has no
    fixed/minimum width and no horizontal overflow container.  The twenty
    ticks still preserve the F5 unit contract (one tick equals five percent).
    """

    # The legacy F5 helper caps rows at eight to prevent silent truncation in
    # its historical card layout. Snapshot requirements are not truncated:
    # this responsive variant can safely render every threshold row it gets.
    try:
        source_rows = list(rows)
    except TypeError as exc:
        raise TypeError("rows 必須是由 mapping 組成的可疊代資料") from exc
    # F5 is a countable card, not an unbounded report table.  Split larger
    # collections into independently readable datasets so every rendered
    # dataset keeps the gallery's eight-row density limit.  The legacy helper
    # used to render all rows in one SVG; retaining the aggregate HTML output
    # keeps existing callers compatible while making the grouping explicit.
    if len(source_rows) > 8:
        groups = [source_rows[index : index + 8] for index in range(0, len(source_rows), 8)]
        return "".join(
            render_tick_rows(
                group,
                source=source,
                title=f"{title or '各項畢業門檻進度'}（{index + 1}/{len(groups)}）",
            )
            for index, group in enumerate(groups)
        )
    data: list[_ProgressRow] = []
    for index, raw_row in enumerate(source_rows):
        if not isinstance(raw_row, Mapping):
            raise TypeError(f"rows[{index}] 必須是 mapping")
        completed = _coerce_number(raw_row.get("completed"))
        required = _coerce_number(raw_row.get("required"))
        ratio = 0.0
        gap: float | None = None
        if completed.value is not None and required.value is not None and required.value > 0:
            ratio = max(0.0, min(1.0, completed.value / required.value))
            gap = abs(required.value - completed.value)
        data.append(
            _ProgressRow(
                label=_text_value(raw_row.get("label")),
                completed=completed,
                required=required,
                unit=_text_value(raw_row.get("unit")),
                ratio=ratio,
                gap=gap,
                status=_f5_status(raw_row.get("status")),
            )
        )
    escaped_title = _escape(title or "各項畢業門檻進度")
    aria = _escape(f"{title or '各項畢業門檻進度'}；每格代表百分之五")
    chart_height = max(150, 62 + max(len(data), 1) * 40)
    svg: list[str] = [
        f'<svg class="lf-chart-svg lf-f5-svg" viewBox="0 0 760 {chart_height}" preserveAspectRatio="xMinYMin meet" role="img" aria-label="{aria}">',
        f"<title>{escaped_title}</title>",
        "<desc>F5 Tick Rows：每列有二十個等距刻度，每個刻度代表該列門檻的百分之五。</desc>",
    ]
    for row_index, row in enumerate(data):
        y = 46 + row_index * 40
        label = _escape(row.label or "未命名項目")
        value = _escape(_row_value(row))
        percent = _escape(_progress_percent(row))
        svg.append(
            f'<g class="lf-f5-row" data-progress="{row.ratio:.6f}" data-status="{_escape(row.status)}">'
            f'<title>{label}：{value}，目前 {percent}，狀態 {_escape(_F5_STATUS_LABELS[row.status])}</title>'
            f'<text class="lf-f5-label" x="10" y="{y + 4}">{label}</text>'
            f'<text class="lf-f5-status" x="170" y="{y + 4}">{_escape(_F5_STATUS_LABELS[row.status])}</text>'
        )
        track_x = 220
        track_width = 430
        for slot in range(SLOT_COUNT):
            start = slot / SLOT_COUNT
            fill = max(0.0, min(1.0, (row.ratio - start) * SLOT_COUNT))
            x = track_x + slot * (track_width / SLOT_COUNT)
            filled = fill >= 0.5 or (row.ratio * SLOT_COUNT) >= slot + 1
            svg.append(
                f'<line class="lf-f5-tick-track" x1="{x + 2:.1f}" y1="{y}" x2="{x + track_width / SLOT_COUNT - 2:.1f}" y2="{y}" data-slot="{slot}" data-tick="{slot}" data-fill="{fill:.6f}" data-filled="{"true" if filled else "false"}" />'
            )
            if fill > 0:
                svg.append(
                    f'<line class="lf-f5-tick-fill" x1="{x + 2:.1f}" y1="{y}" x2="{x + 2 + (track_width / SLOT_COUNT - 4) * fill:.1f}" y2="{y}" aria-hidden="true" />'
                )
        svg.append(f'<text class="lf-f5-value" x="680" y="{y + 4}">{value}</text></g>')
    if not data:
        svg.append('<text class="lf-f5-empty" x="380" y="90" text-anchor="middle">尚未提供門檻資料</text>')
    svg.append("</svg>")

    table_rows = "".join(
        f"<tr><th scope=\"row\">{_escape(row.label or '未命名項目')}</th>"
        f"<td>{_escape(row.completed.display)}</td><td>{_escape(row.required.display)}</td>"
        f"<td>{_escape(row.unit or '—')}</td><td>{_escape(_progress_percent(row))}</td>"
        f"<td data-status=\"{_escape(row.status)}\">{_escape(_F5_STATUS_LABELS[row.status])}</td></tr>"
        for row in data
    ) or '<tr><td colspan="6">沒有資料</td></tr>'
    css = _chart_css("lf-f5-chart") + """
    .lf-f5-chart .lf-f5-label, .lf-f5-chart .lf-f5-value, .lf-f5-chart .lf-f5-status { fill: var(--lf-text); font-size: 12px; font-weight: 700; }
    .lf-f5-chart .lf-f5-status { font-size: 11px; font-weight: 800; }
    .lf-f5-chart .lf-f5-row[data-status="PASS"] .lf-f5-status { fill: #087f5b; }
    .lf-f5-chart .lf-f5-row[data-status="FAIL"] .lf-f5-status { fill: #dc2626; }
    .lf-f5-chart .lf-f5-row[data-status="UNKNOWN"] .lf-f5-status { fill: #9a5b00; }
    @media (prefers-color-scheme: dark) {
      .lf-f5-chart .lf-f5-row[data-status="PASS"] .lf-f5-status { fill: #65d5ab; }
      .lf-f5-chart .lf-f5-row[data-status="FAIL"] .lf-f5-status { fill: #ff9a92; }
      .lf-f5-chart .lf-f5-row[data-status="UNKNOWN"] .lf-f5-status { fill: #f5c276; }
    }
    html[data-theme="dark"] .lf-f5-chart .lf-f5-row[data-status="PASS"] .lf-f5-status,
    html[data-utaipei-theme="dark"] .lf-f5-chart .lf-f5-row[data-status="PASS"] .lf-f5-status { fill: #65d5ab; }
    html[data-theme="dark"] .lf-f5-chart .lf-f5-row[data-status="FAIL"] .lf-f5-status,
    html[data-utaipei-theme="dark"] .lf-f5-chart .lf-f5-row[data-status="FAIL"] .lf-f5-status { fill: #ff9a92; }
    html[data-theme="dark"] .lf-f5-chart .lf-f5-row[data-status="UNKNOWN"] .lf-f5-status,
    html[data-utaipei-theme="dark"] .lf-f5-chart .lf-f5-row[data-status="UNKNOWN"] .lf-f5-status { fill: #f5c276; }
    .lf-f5-chart .lf-f5-value { font-variant-numeric: tabular-nums; font-weight: 800; }
    .lf-f5-chart .lf-f5-tick-track { stroke: var(--lf-grid); stroke-linecap: round; stroke-width: 7; }
    .lf-f5-chart .lf-f5-tick-fill { stroke: var(--lf-data); stroke-linecap: round; stroke-width: 7; }
    .lf-f5-chart .lf-f5-empty { fill: var(--lf-muted); font-size: 14px; font-weight: 700; }
    """
    return (
        f'<section class="lf-f5-chart" data-row-count="{len(data)}" data-max-row-count="8" aria-label="{aria}"><style>{css}</style>'
        f'<h3 class="lf-chart-title">{escaped_title}</h3>'
        '<p class="lf-chart-subtitle">F5 Tick Rows · 每格 5% · 讀取下方文字表可取得精確數字</p>'
        f'{"".join(svg)}'
        f'<p class="lf-chart-source">資料來源：{_chart_source(source)}</p>'
        '<details class="lf-details"><summary>查看 F5 精確數字</summary>'
        '<table class="lf-data-table" aria-label="F5 畢業門檻進度明細">'
        '<caption>畢業門檻進度明細</caption><thead><tr><th scope="col">項目</th><th scope="col">已完成</th>'
        '<th scope="col">門檻</th><th scope="col">單位</th><th scope="col">進度</th><th scope="col">狀態</th></tr></thead>'
        f'<tbody>{table_rows}</tbody></table></details></section>'
    )


def render_rung_bars(
    rows: Iterable[Mapping[str, Any]],
    *,
    title: str = "正式配置學分分布",
    source: str = _DEFAULT_SOURCE,
    unit: str = "學分",
    rung_unit: Any = 1,
) -> str:
    """Render Lieflat F1 Rung Bars for additive exclusive credits.

    A rung represents one ``rung_unit`` of *exclusive* credit.  This chart is
    intentionally separate from requirement progress: shared shadow credit,
    requirement overlap, and nominal in-progress credits are not accepted as
    values for this additive ledger chart.  A row can contain a fractional
    final rung, represented by ``data-fraction`` and the exact text table.
    Larger inputs are split into cards of at most eight rows, matching the
    density contract used by F5.
    """

    try:
        source_rows = list(rows)
    except TypeError as exc:
        raise TypeError("rows 必須是由 mapping 組成的可疊代資料") from exc
    if len(source_rows) > 8:
        groups = [source_rows[index : index + 8] for index in range(0, len(source_rows), 8)]
        return "".join(
            render_rung_bars(
                group,
                source=source,
                title=f"{title or '正式配置學分分布'}（{index + 1}/{len(groups)}）",
                unit=unit,
                rung_unit=rung_unit,
            )
            for index, group in enumerate(groups)
        )
    step = _coerce_number(rung_unit)
    step_value = step.value if step.value is not None and step.value > 0 else 1.0
    data: list[tuple[str, _Number, int, float]] = []
    max_rungs = 0
    for index, raw in enumerate(source_rows):
        if not isinstance(raw, Mapping):
            raise TypeError(f"rows[{index}] 必須是 mapping")
        allocation_kind = _text_value(raw.get("allocation_kind")).upper()
        if allocation_kind and allocation_kind != "EXCLUSIVE":
            return render_chart_unavailable(
                "F1",
                "正式配置學分圖表只接受 EXCLUSIVE 配置；共享影子或其他資料不能加總。",
                source=source,
                title=title,
            )
        value = _coerce_number(raw.get("value", raw.get("completed", raw.get("credits"))))
        numeric = max(value.value or 0.0, 0.0) if value.value is not None else None
        count = int(math.ceil(numeric / step_value)) if numeric is not None and numeric > 0 else 0
        fraction = min(1.0, max(0.0, numeric / (count * step_value))) if count and numeric is not None else 0.0
        max_rungs = max(max_rungs, count)
        data.append((_text_value(raw.get("label") or raw.get("category") or "未命名分類"), value, count, fraction))
    if max_rungs > 128:
        return render_chart_unavailable(
            "F1",
            "學分單位過大，無法以可數刻度安全呈現；請改讀精確表格。",
            source=source,
            title=title,
        )
    escaped_title = _escape(title or "正式配置學分分布")
    aria = _escape(f"{title or '正式配置學分分布'}；正式配置學分，每格 {step.display} {unit}")
    row_height = 42
    chart_height = max(145, 58 + max(len(data), 1) * row_height)
    track_x, track_width = 220, 450
    svg: list[str] = [
        f'<svg class="lf-chart-svg lf-f1-svg" viewBox="0 0 760 {chart_height}" preserveAspectRatio="xMinYMin meet" role="img" aria-label="{aria}">',
        f"<title>{escaped_title}</title>",
        f"<desc>F1 Rung Bars：每一格代表 {step.display} {unit} 的正式配置學分；共享影子與修習中學分不列入。</desc>",
    ]
    for index, (label_text, value, count, fraction) in enumerate(data):
        y = 42 + index * row_height
        label = _escape(label_text)
        svg.append(
            f'<g class="lf-f1-row" data-rung-count="{count}" data-scale-rungs="{max(max_rungs, 1)}" data-value="{_escape(value.display)}">'
            f'<title>{label}：{_escape(value.display)} { _escape(unit) }</title>'
            f'<text class="lf-f1-label" x="10" y="{y + 4}">{label}</text>'
        )
        if count:
            for rung in range(count):
                # All rows use one scale so the same rung position means the
                # same absolute amount of exclusive credit across categories.
                x = track_x + (rung + 0.5) * track_width / max(max_rungs, 1)
                rung_fraction = fraction if rung == count - 1 else 1.0
                svg.append(
                    f'<line class="lf-f1-rung" x1="{x:.2f}" y1="{y - 10}" x2="{x:.2f}" y2="{y + 10}" '
                    f'data-rung="{rung}" data-filled="true" data-fraction="{rung_fraction:.6f}" />'
                )
        svg.append(f'<text class="lf-f1-value" x="690" y="{y + 4}">{_escape(value.display)} { _escape(unit) }</text></g>')
    if not data:
        svg.append('<text class="lf-f1-empty" x="380" y="90" text-anchor="middle">尚未提供正式配置學分</text>')
    svg.append("</svg>")
    table_rows = "".join(
        f'<tr><th scope="row">{_escape(label)}</th><td>{_escape(value.display)}</td><td>{count}</td><td>{_escape(unit)}</td></tr>'
        for label, value, count, _fraction in data
    ) or '<tr><td colspan="4">沒有資料</td></tr>'
    css = _chart_css("lf-f1-chart") + """
    .lf-f1-chart .lf-f1-label, .lf-f1-chart .lf-f1-value { fill: var(--lf-text); font-size: 12px; font-weight: 700; }
    .lf-f1-chart .lf-f1-value { font-variant-numeric: tabular-nums; font-weight: 800; }
    .lf-f1-chart .lf-f1-rung { stroke: var(--lf-data); stroke-linecap: round; stroke-width: 8; }
    .lf-f1-chart .lf-f1-empty { fill: var(--lf-muted); font-size: 14px; font-weight: 700; }
    """
    return (
        f'<section class="lf-f1-chart" data-row-count="{len(data)}" data-max-row-count="8" aria-label="{aria}"><style>{css}</style>'
        f'<h3 class="lf-chart-title">{escaped_title}</h3>'
        '<p class="lf-chart-subtitle">F1 Rung Bars · 僅計正式配置學分 · 每格代表一個可數學分單位</p>'
        f'{"".join(svg)}<p class="lf-chart-source">資料來源：{_chart_source(source)}</p>'
        '<details class="lf-details"><summary>查看 Rung Bars 精確數字</summary>'
        '<table class="lf-data-table" aria-label="正式配置學分明細"><caption>正式配置學分明細</caption>'
        '<thead><tr><th scope="col">分類</th><th scope="col">正式配置</th><th scope="col">刻度數</th><th scope="col">單位</th></tr></thead>'
        f'<tbody>{table_rows}</tbody></table></details></section>'
    )


def render_tick_gauge(
    completed: Any,
    required: Any,
    *,
    title: str = "總畢業學分完成度",
    unit: str = "學分",
    source: str = _DEFAULT_SOURCE,
) -> str:
    """Render Lieflat F11 Tick Gauge with one countable tick per percent."""

    completed_number = _coerce_number(completed)
    required_number = _coerce_number(required)
    ratio = _chart_ratio(completed_number, required_number)
    progress = ratio if ratio is not None else 0.0
    percent = f"{progress * 100:.1f}%" if ratio is not None else "無法計算"
    escaped_title = _escape(title or "總畢業學分完成度")
    aria = _escape(f"{title or '總畢業學分完成度'}：{_row_value(_ProgressRow('', completed_number, required_number, unit, progress, None))}，{percent}")
    center_x, base_y, radius = 380, 170, 142
    svg: list[str] = [
        f'<svg class="lf-chart-svg lf-f11-svg" viewBox="0 0 760 205" preserveAspectRatio="xMidYMid meet" role="img" aria-label="{aria}">',
        f"<title>{escaped_title}</title>",
        "<desc>F11 Tick Gauge：半圓弧上共一百個刻度，每個刻度代表百分之一。</desc>",
    ]
    for tick in range(100):
        theta = math.pi - (math.pi * tick / 99 if tick else 0)
        inner = radius - (9 if tick % 10 == 0 else 5)
        outer = radius
        x1 = center_x + inner * math.cos(theta)
        y1 = base_y - inner * math.sin(theta)
        x2 = center_x + outer * math.cos(theta)
        y2 = base_y - outer * math.sin(theta)
        filled = tick / 99 <= progress if ratio is not None else False
        svg.append(
            f'<line class="lf-f11-tick {"is-filled" if filled else "is-track"}" data-tick="{tick}" data-filled="{"true" if filled else "false"}" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" />'
        )
    svg.extend(
        [
            f'<text class="lf-f11-percent" x="{center_x}" y="126" text-anchor="middle">{_escape(percent)}</text>',
            f'<text class="lf-f11-value" x="{center_x}" y="153" text-anchor="middle">{_escape(completed_number.display)} / {_escape(required_number.display)} { _escape(unit) }</text>',
            '<text class="lf-f11-axis" x="238" y="197">0%</text><text class="lf-f11-axis" x="522" y="197" text-anchor="end">100%</text>',
            "</svg>",
        ]
    )
    css = _chart_css("lf-f11-chart") + """
    .lf-f11-chart .lf-f11-tick { stroke-linecap: round; stroke-width: 5; }
    .lf-f11-chart .lf-f11-tick.is-track { stroke: var(--lf-grid); }
    .lf-f11-chart .lf-f11-tick.is-filled { stroke: var(--lf-data); }
    .lf-f11-chart .lf-f11-percent { fill: var(--lf-data); font-size: 31px; font-weight: 800; }
    .lf-f11-chart .lf-f11-value { fill: var(--lf-text); font-size: 13px; font-weight: 700; }
    .lf-f11-chart .lf-f11-axis { fill: var(--lf-muted); font-size: 11px; }
    """
    table = (
        "<table class=\"lf-data-table\" aria-label=\"總畢業學分完成度明細\"><caption>總畢業學分完成度</caption>"
        "<thead><tr><th scope=\"col\">已完成</th><th scope=\"col\">門檻</th><th scope=\"col\">進度</th></tr></thead>"
        f"<tbody><tr><td>{_escape(completed_number.display)} { _escape(unit) }</td><td>{_escape(required_number.display)} { _escape(unit) }</td><td>{_escape(percent)}</td></tr></tbody></table>"
    )
    return (
        f'<section class="lf-f11-chart" aria-label="{aria}"><style>{css}</style>'
        f'<h3 class="lf-chart-title">{escaped_title}</h3>'
        '<p class="lf-chart-subtitle">F11 Tick Gauge · 每一格代表 1% · 圖形下方提供精確數字</p>'
        f'{"".join(svg)}<p class="lf-chart-source">資料來源：{_chart_source(source)}</p>'
        f'<details class="lf-details"><summary>查看 Tick Gauge 精確數字</summary>{table}</details></section>'
    )


def _stacked_value(raw: Any) -> _Number:
    return _coerce_number(raw)


def render_stacked_rungs(
    rows: Iterable[Mapping[str, Any]],
    *,
    title: str = "各分類學分狀態分布",
    source: str = _DEFAULT_SOURCE,
    mode: str | None = None,
) -> str:
    """Render Lieflat F7 Stacked Rungs with accessible category details.

    Snapshot statistics use ``mode="gate_counts"``.  That mode is deliberately
    limited to countable PASS/FAIL/UNKNOWN gate states and emits one discrete
    rung per gate; it must not be used to display credits.  The historical
    ``completed``/``in_progress``/``missing``/``unknown`` spelling remains
    available for non-snapshot callers, preserving the old public helper while
    keeping the strict snapshot path fail-closed.
    """

    try:
        source_rows = list(rows)
    except TypeError as exc:
        raise TypeError("rows 必須是由 mapping 組成的可疊代資料") from exc
    gate_mode = _text_value(mode).lower() in {"gate", "gate_counts", "status_counts"} or any(
        isinstance(raw, Mapping) and any(key in raw for key in ("PASS", "FAIL", "pass", "fail"))
        for raw in source_rows
    )
    max_categories = 4 if gate_mode else 8
    if len(source_rows) > max_categories:
        groups = [source_rows[index : index + max_categories] for index in range(0, len(source_rows), max_categories)]
        return "".join(
            render_stacked_rungs(
                group,
                title=f"{title or '各分類狀態分布'}（{index + 1}/{len(groups)}）",
                source=source,
                mode="gate_counts" if gate_mode else mode,
            )
            for index, group in enumerate(groups)
        )
    segments = ("PASS", "FAIL", "UNKNOWN") if gate_mode else ("completed", "in_progress", "missing", "unknown")
    labels = {"PASS": "通過", "FAIL": "未通過", "UNKNOWN": "待確認", "completed": "已完成", "in_progress": "修習中", "missing": "尚缺", "unknown": "待確認"}
    aliases = {
        "PASS": ("PASS", "pass", "completed"),
        "FAIL": ("FAIL", "fail", "missing"),
        "UNKNOWN": ("UNKNOWN", "unknown"),
    }
    normalised: list[dict[str, Any]] = []
    for index, raw in enumerate(source_rows):
        if not isinstance(raw, Mapping):
            raise TypeError(f"rows[{index}] 必須是 mapping")
        if gate_mode:
            values = {
                key: _stacked_value(next((raw.get(alias) for alias in aliases[key] if alias in raw), 0))
                for key in segments
            }
            for key, value in values.items():
                if value.value is not None and abs(value.value - round(value.value)) > 1e-9:
                    return render_chart_unavailable(
                        "F7",
                        "判定閘門數量不是整數，無法以可數刻度安全呈現。",
                        source=source,
                        title=title,
                    )
        else:
            values = {key: _stacked_value(raw.get(key, 0)) for key in segments}
        total = _stacked_value(raw.get("total"))
        if total.value is None or total.value <= 0:
            numeric_total = sum((item.value or 0.0) for item in values.values())
            total = _coerce_number(numeric_total)
        # In gate mode a zero state is omitted from the geometry and legend;
        # an empty category remains an explicit zero-total row in the table.
        normalised.append({"label": _text_value(raw.get("label") or raw.get("category") or "未命名分類"), "values": values, "total": total})
    escaped_title = _escape(title or "各分類學分狀態分布")
    aria = _escape(f"{title or '各分類學分狀態分布'}；共 {len(normalised)} 個分類")
    row_height = 45
    chart_height = max(130, 65 + max(len(normalised), 1) * row_height)
    track_x, track_width = 220, 440
    svg: list[str] = [
        f'<svg class="lf-chart-svg lf-f7-svg" viewBox="0 0 760 {chart_height}" preserveAspectRatio="xMinYMin meet" role="img" aria-label="{aria}">',
        f"<title>{escaped_title}</title>",
        f"<desc>F7 Stacked Rungs：每列是一個分類，依序呈現{'通過、未通過與待確認判定閘門' if gate_mode else '已完成、修習中、尚缺與待確認學分'}。</desc>",
    ]
    for index, item in enumerate(normalised):
        y = 40 + index * row_height
        label = _escape(item["label"])
        total_number: _Number = item["total"]
        total_value = total_number.value or 0.0
        svg.append(f'<g class="lf-f7-rung" data-category="{label}"><title>{label}</title><text class="lf-f7-label" x="10" y="{y + 4}">{label}</text>')
        if gate_mode:
            # Countable geometry: a gate is represented by one vertical rung,
            # not a proportional rectangle that could be mistaken for credit.
            position = 0
            for key in segments:
                value = item["values"][key]
                amount = max(int(round(value.value or 0.0)), 0)
                for rung in range(amount):
                    x = track_x + (position + 0.5) * track_width / max(total_value, 1.0)
                    svg.append(
                        f'<line class="lf-f7-gate-rung lf-f7-{key.lower()}" x1="{x:.2f}" y1="{y - 10}" x2="{x:.2f}" y2="{y + 10}" data-status="{key}" data-rung="{position}" data-count="{amount}"><title>{_escape(labels[key])}：第 {rung + 1} 個閘門</title></line>'
                    )
                    position += 1
        else:
            cursor = track_x
            for key in segments:
                value = item["values"][key]
                amount = max(value.value or 0.0, 0.0)
                width = track_width * amount / total_value if total_value > 0 else 0.0
                svg.append(
                    f'<rect class="lf-f7-segment lf-f7-{key}" x="{cursor:.2f}" y="{y - 9}" width="{max(0.0, width):.2f}" data-status="{key}" data-credits="{_escape(value.display)}"><title>{_escape(labels[key])}：{_escape(value.display)} 學分</title></rect>'
                )
                cursor += width
        total_label = "個閘門" if gate_mode else "學分"
        svg.append(f'<text class="lf-f7-total" x="680" y="{y + 4}">{_escape(total_number.display)} {total_label}</text></g>')
    if not normalised:
        svg.append('<text class="lf-f7-empty" x="380" y="90" text-anchor="middle">尚未提供分類統計</text>')
    svg.append("</svg>")
    table_rows = "".join(
        f'<tr><th scope="row">{_escape(item["label"])}</th>'
        + "".join(f'<td>{_escape(item["values"][key].display)}</td>' for key in segments)
        + f'<td>{_escape(item["total"].display)}</td></tr>'
        for item in normalised
    ) or f'<tr><td colspan="{len(segments) + 2}">沒有資料</td></tr>'
    css = _chart_css("lf-f7-chart") + """
    .lf-f7-chart .lf-f7-label, .lf-f7-chart .lf-f7-total { fill: var(--lf-text); font-size: 12px; font-weight: 700; }
    .lf-f7-chart .lf-f7-total { font-variant-numeric: tabular-nums; font-weight: 800; }
    .lf-f7-chart .lf-f7-segment { stroke: var(--lf-surface); stroke-width: 2; }
    .lf-f7-chart .lf-f7-completed { fill: var(--lf-data); }
    .lf-f7-chart .lf-f7-in_progress { fill: #60A5FA; }
    .lf-f7-chart .lf-f7-missing { fill: #94A3B8; }
    .lf-f7-chart .lf-f7-unknown { fill: var(--lf-accent); }
    .lf-f7-chart .lf-f7-gate-rung { stroke-linecap: round; stroke-width: 8; }
    .lf-f7-chart .lf-f7-pass { stroke: var(--lf-data); }
    .lf-f7-chart .lf-f7-fail { stroke: #B91C1C; }
    .lf-f7-chart .lf-f7-unknown { stroke: var(--lf-accent); }
    .lf-f7-chart .lf-f7-empty { fill: var(--lf-muted); font-size: 14px; font-weight: 700; }
    """
    legend_items = (
        ("PASS", "通過", "lf-swatch--data"),
        ("FAIL", "未通過", "lf-swatch--muted"),
        ("UNKNOWN", "待確認", "lf-swatch--accent"),
    ) if gate_mode else (("completed", "已完成", "lf-swatch--data"), ("missing", "尚缺", "lf-swatch--muted"), ("unknown", "待確認", "lf-swatch--accent"))
    legend_markup = "".join(
        f'<li class="lf-legend-item"><span class="lf-swatch {swatch}" aria-hidden="true"></span>{label}</li>'
        for _key, label, swatch in legend_items
    )
    headings = ("分類", "通過", "未通過", "待確認", "總閘門") if gate_mode else ("分類", "已完成", "修習中", "尚缺", "待確認", "總量")
    heading_markup = "".join(f'<th scope="col">{heading}</th>' for heading in headings)
    return (
        f'<section class="lf-f7-chart" data-mode="{"gate_counts" if gate_mode else "legacy_credits"}" data-category-count="{len(normalised)}" data-max-category-count="{max_categories}" aria-label="{aria}"><style>{css}</style>'
        f'<h3 class="lf-chart-title">{escaped_title}</h3>'
        f'<p class="lf-chart-subtitle">F7 Stacked Rungs · 每列代表一個分類 · {"只統計判定閘門，不代表學分" if gate_mode else "舊版學分狀態，請勿作為正式總量"}</p>'
        f'<ul class="lf-legend" aria-label="圖例">{legend_markup}</ul>'
        f'{"".join(svg)}<p class="lf-chart-source">資料來源：{_chart_source(source)}</p>'
        '<details class="lf-details"><summary>查看 Stacked Rungs 精確數字</summary>'
        '<table class="lf-data-table" aria-label="分類學分狀態明細"><caption>分類學分狀態明細</caption>'
        f'<thead><tr>{heading_markup}</tr></thead>'
        f'<tbody>{table_rows}</tbody></table></details></section>'
    )


# Descriptive aliases make the selected Lieflat gallery patterns explicit to
# callers while preserving the original public functions above.
render_f5_tick_rows = render_tick_rows
render_f1_rung_bars = render_rung_bars
render_f7_stacked_rungs = render_stacked_rungs
render_f11_tick_gauge = render_tick_gauge


__all__ = [
    "SLOT_COUNT",
    "render_lieflat_progress_chart",
    "render_progress_chart",
    "render_tick_rows",
    "render_f5_tick_rows",
    "render_rung_bars",
    "render_f1_rung_bars",
    "render_stacked_rungs",
    "render_f7_stacked_rungs",
    "render_tick_gauge",
    "render_f11_tick_gauge",
    "render_chart_unavailable",
]
