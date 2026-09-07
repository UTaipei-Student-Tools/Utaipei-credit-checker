import math
import re

from lieflat_progress_chart import (
    SLOT_COUNT,
    render_chart_unavailable,
    render_f1_rung_bars,
    render_f7_stacked_rungs,
    render_progress_chart,
    render_stacked_rungs,
    render_tick_gauge,
    render_tick_rows,
)


def _row(label="共同必修", completed=12, required=20, unit="學分"):
    return {"label": label, "completed": completed, "required": required, "unit": unit}


def test_f5_tick_rows_keep_twenty_slots_per_row_and_numeric_label():
    output = render_progress_chart([_row(), _row("系專業", 20, 20)])

    assert output.count('data-slot="') == SLOT_COUNT * 2
    assert output.count('class="lf-guide-track"') == 2
    assert "12 / 20 學分" in output
    assert "20 / 20 學分" in output
    assert 'data-progress="0.600000"' in output
    assert output.count("<h2") == 1


def test_user_text_is_escaped_in_svg_table_and_source():
    output = render_progress_chart(
        [_row('<img src=x onerror="alert(1)"> & 警告', 1, 2, '學分 <bad>')],
        source='來源 <script>alert("x")</script>',
    )

    assert "<img" not in output
    assert "<script" not in output.lower()
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; 警告" in output
    assert "學分 &lt;bad&gt;" in output
    assert "來源 &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in output


def test_visual_fill_clamps_but_truthful_numbers_remain():
    output = render_progress_chart([_row("超過門檻", 120, 100), _row("負數", -3, 10)])

    assert 'data-progress="1.000000"' in output
    assert 'data-progress="0.000000"' in output
    assert "120 / 100 學分" in output
    assert "-3 / 10 學分" in output
    assert output.count('class="lf-row lf-row--focus"') == 1


def test_zero_negative_and_nonfinite_requirements_are_safe():
    output = render_progress_chart(
        [_row("零門檻", 3, 0), _row("負門檻", 3, -10), _row("無效", math.nan, math.inf)]
    )

    assert "3 / 0 學分" in output
    assert "3 / -10 學分" in output
    assert "無效 / 無效 學分" in output
    assert "無法計算" in output
    assert "nan" not in output.lower()
    assert "inf" not in output.lower()
    assert 'data-progress="0.000000"' in output
    assert output.count('<line class="lf-tick-fill"') == 0


def test_row_limit_is_explicit_to_avoid_silent_data_loss():
    try:
        render_progress_chart([_row(str(index)) for index in range(9)])
    except ValueError as exc:
        assert "最多接受 8" in str(exc)
    else:
        raise AssertionError("九筆資料應明確拒絕，避免圖表靜默遺失門檻")


def test_accessibility_reduced_motion_and_mobile_scrolling_contract():
    output = render_progress_chart([_row()])

    assert 'role="img"' in output
    assert 'aria-label=' in output
    assert 'class="lf-data-table"' in output
    assert "每一格代表該項門檻的 5%" in output
    assert "@media (prefers-reduced-motion: reduce)" in output
    assert "overflow-x: auto" in output
    assert "min-width: 700px" in output
    assert "<script" not in output.lower()
    assert "http://" not in output.lower()
    assert "https://" not in output.lower()


def test_empty_rows_render_a_single_safe_empty_state():
    output = render_progress_chart([])

    assert "目前尚未有可比較的畢業門檻" in output
    assert "尚未提供門檻資料" in output
    assert output.count("<h2") == 1
    assert 'colspan="5"' in output


def test_snapshot_f5_tick_rows_are_responsive_and_keep_all_thresholds():
    rows = [_row(f"門檻 {index}", index, 20) for index in range(10)]
    output = render_tick_rows(rows)

    assert output.count('class="lf-f5-row"') == 10
    assert output.count('data-slot="') == 10 * SLOT_COUNT
    assert "min-width" not in output
    assert "overflow-x" not in output
    assert '<details class="lf-details" open>' in output
    assert "畢業門檻進度明細" in output


def test_snapshot_f5_tick_rows_preserve_visible_pass_fail_unknown_status():
    output = render_tick_rows(
        [
            {**_row("已完成", 3, 3), "status": "PASS"},
            {**_row("未完成", 0, 3), "status": "FAIL"},
            {**_row("證據不足", 3, 3), "status": "UNKNOWN"},
        ]
    )

    assert output.count('data-status="PASS"') >= 1
    assert output.count('data-status="FAIL"') >= 1
    assert output.count('data-status="UNKNOWN"') >= 1
    assert "已通過" in output
    assert "未通過" in output
    assert "待確認" in output
    assert "狀態" in output


def test_snapshot_f1_uses_one_shared_max_rung_scale_for_all_rows():
    output = render_f1_rung_bars(
        [
            {"label": "兩學分", "value": "2", "unit": "學分", "allocation_kind": "EXCLUSIVE"},
            {"label": "四學分", "value": "4", "unit": "學分", "allocation_kind": "EXCLUSIVE"},
        ]
    )

    assert 'data-scale-rungs="4"' in output
    xs = re.findall(r'<line class="lf-f1-rung"[^>]*x1="([^"]+)"[^>]*data-rung="0"', output)
    assert len(xs) == 2
    assert xs[0] == xs[1]


def test_f11_tick_gauge_has_one_countable_tick_per_percent_and_text_table():
    output = render_tick_gauge("64", "128")

    assert output.count('data-tick="') == 100
    assert 'data-filled="true"' in output
    assert "64 / 128" in output
    assert "50.0%" in output
    assert '<details class="lf-details" open>' in output
    assert "min-width" not in output


def test_f7_stacked_rungs_exposes_each_status_segment_and_exact_data():
    output = render_stacked_rungs(
        [
            {"label": "系必修", "completed": 12, "in_progress": 3, "missing": 6, "unknown": 2, "total": 23},
            {"label": "通識", "completed": 8, "in_progress": 0, "missing": 0, "unknown": 1, "total": 9},
        ]
    )

    assert output.count('class="lf-f7-rung"') == 2
    for status in ("completed", "in_progress", "missing", "unknown"):
        assert f'data-status="{status}"' in output
    assert "系必修" in output
    assert '<details class="lf-details" open>' in output
    assert "分類學分狀態明細" in output


def test_snapshot_f1_rung_bars_are_countable_and_exclusive_only():
    output = render_f1_rung_bars(
        [{"label": "系必修", "value": "3", "unit": "學分", "allocation_kind": "EXCLUSIVE"}]
    )

    assert 'data-mode="' not in output or "F1" in output
    assert output.count('class="lf-f1-rung"') == 3
    assert 'data-filled="true"' in output
    assert "正式配置學分" in output
    assert "共享影子" in output


def test_snapshot_f1_rejects_nonexclusive_rows_instead_of_charting_shadow_credit():
    output = render_f1_rung_bars(
        [{"label": "雙主修共享", "value": "3", "allocation_kind": "SHARED_SHADOW"}]
    )

    assert 'data-chart-id="F1"' in output
    assert 'data-available="false"' in output
    assert "EXCLUSIVE" in output
    assert "lf-f1-rung" not in output


def test_snapshot_f7_gate_mode_has_only_pass_fail_unknown_countable_rungs():
    output = render_f7_stacked_rungs(
        [
            {"label": "主修", "PASS": 2, "FAIL": 1, "UNKNOWN": 1, "total": 4},
            {"label": "雙主修", "PASS": 1, "FAIL": 0, "UNKNOWN": 0, "total": 1},
        ],
        mode="gate_counts",
    )

    assert 'data-mode="gate_counts"' in output
    assert 'data-status="PASS"' in output
    assert 'data-status="FAIL"' in output
    assert 'data-status="UNKNOWN"' in output
    assert 'data-status="IN_PROGRESS"' not in output
    assert '<rect class="lf-f7-segment' not in output
    assert output.count('class="lf-f7-rung"') == 2


def test_unavailable_chart_is_explanation_without_decorative_svg():
    output = render_chart_unavailable("F11", "AGGREGATE_GATE_UNAVAILABLE")

    assert 'data-available="false"' in output
    assert "AGGREGATE_GATE_UNAVAILABLE" in output
    assert "<svg" not in output


def test_all_chart_variants_put_explicit_theme_bridge_after_os_and_legacy_rules():
    outputs = (
        render_progress_chart([_row()]),
        render_tick_rows([_row()]),
        render_tick_gauge("64", "128"),
        render_stacked_rungs(
            [{"label": "系必修", "completed": 12, "in_progress": 3, "missing": 6, "unknown": 2, "total": 23}]
        ),
    )

    for output in outputs:
        media_index = output.index("@media (prefers-color-scheme: dark)")
        legacy_indices = [
            output.find(f'html[data-theme="{theme}"]')
            for theme in ("light", "dark")
        ]
        legacy_indices = [index for index in legacy_indices if index >= 0]
        assert legacy_indices
        for theme in ("light", "dark"):
            bridge_index = output.index(f'html[data-utaipei-theme="{theme}"]')
            assert media_index < bridge_index
            assert max(legacy_indices) < bridge_index

        light_bridge = output.split('html[data-utaipei-theme="light"]', 1)[1]
        light_bridge = light_bridge.split('html[data-utaipei-theme="dark"]', 1)[0]
        dark_bridge = output.split('html[data-utaipei-theme="dark"]', 1)[1]
        for token in ("--lf-text: #0F172A", "--lf-muted: #475569", "--lf-grid: #CBD5E1", "--lf-accent: #2563EB"):
            assert token in light_bridge
        assert "--lf-data: #1E3A5F" in light_bridge or "--lf-blue: #1E3A5F" in light_bridge
        for token in (
            "--lf-text: #F8FAFC",
            "--lf-muted: #CBD5E1",
            "--lf-grid: #334155",
            "--lf-accent: #60A5FA",
        ):
            assert token in dark_bridge
        assert "--lf-surface: #111827" in dark_bridge
        assert "--lf-data: #60A5FA" in dark_bridge or "--lf-blue: #60A5FA" in dark_bridge
