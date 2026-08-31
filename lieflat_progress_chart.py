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
            track_y = y + 9
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


__all__ = ["SLOT_COUNT", "render_lieflat_progress_chart", "render_progress_chart"]
