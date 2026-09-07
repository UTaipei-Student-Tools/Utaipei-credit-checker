"""Real-browser acceptance checks for the local or deployed Streamlit app.

Run explicitly after starting the app; this file is intentionally not collected
by pytest because Playwright and browser binaries are deployment tooling, not
runtime dependencies.
"""

from __future__ import annotations

import argparse
import csv as csv_module
import io
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

import fitz

try:
    from playwright.sync_api import (
        Browser,
        Page,
        sync_playwright,
    )
    from playwright.sync_api import Error as PlaywrightError
except ModuleNotFoundError:  # pragma: no cover - optional browser tooling
    Browser = Page = object
    sync_playwright = None
    PlaywrightError = Exception

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.synthetic_transcript_fixture import build_synthetic_transcript_pdf  # noqa: E402, I001
from snapshot_renderer import _public_reason  # noqa: E402, I001


VIEWPORTS = (
    (375, 812, "iphone-375"),
    (390, 844, "iphone-390"),
    (414, 896, "iphone-414"),
    (844, 390, "phone-landscape"),
    (768, 1024, "tablet-768"),
    (1024, 768, "tablet-1024"),
    (1440, 900, "desktop-1440"),
)


def _wait_for_app(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.get_by_role("button", name="Main menu").wait_for(state="visible", timeout=90_000)
    page.get_by_role("combobox").first.wait_for(state="visible", timeout=90_000)
    page.wait_for_timeout(800)
    _assert_no_raw_markup(page)


def _assert_no_raw_markup(page: Page) -> None:
    """Reject visible CSS/HTML source accidentally emitted as page text."""

    body_text = page.locator("body").inner_text()
    forbidden = ("<style>", "--ui-canvas", "<header class=")
    leaked = [token for token in forbidden if token.casefold() in body_text.casefold()]
    assert not leaked, {"leaked_markup": leaked, "body_prefix": body_text[:500]}


def _open_menu(page: Page) -> None:
    button = page.get_by_role("button", name="Main menu")
    if button.get_attribute("aria-expanded") != "true":
        button.click()
    page.get_by_role("menuitemradio", name=re.compile("System")).wait_for(timeout=5_000)


def _choose_theme(page: Page, label: str) -> None:
    _open_menu(page)
    page.get_by_role("menuitemradio", name=re.compile(label)).click()
    page.wait_for_timeout(700)


def _theme_state(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => ({
          root: document.documentElement.getAttribute('data-utaipei-theme') || '',
          app: getComputedStyle(document.querySelector('.stApp')).backgroundColor,
          text: getComputedStyle(document.querySelector('.stApp')).color,
          header: getComputedStyle(document.querySelector('[data-testid="stHeader"]')).backgroundColor,
        })"""
    )


def _assert_primary_button_contrast(page: Page) -> float:
    colors = page.get_by_role("button", name="套用設定", exact=True).evaluate(
        """button => ({
          background: getComputedStyle(button).backgroundColor,
          foreground: getComputedStyle(button.querySelector('p') || button).color,
        })"""
    )

    def luminance(color: str) -> float:
        channels = [int(value) / 255 for value in re.findall(r"\d+", color)[:3]]
        assert len(channels) == 3, color
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    values = sorted(luminance(value) for value in colors.values())
    contrast = (values[1] + 0.05) / (values[0] + 0.05)
    assert contrast >= 4.5, {"contrast": contrast, **colors}
    return round(contrast, 2)


def _assert_theme_matrix(browser: Browser, url: str) -> dict[str, object]:
    results: dict[str, object] = {}
    for scheme in ("dark", "light"):
        context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme)
        page = context.new_page()
        _wait_for_app(page, url)
        _choose_theme(page, "Light")
        explicit_light = _theme_state(page)
        assert explicit_light["root"] == "light"
        assert explicit_light["app"] == "rgb(248, 250, 252)"
        light_button_contrast = _assert_primary_button_contrast(page)
        _choose_theme(page, "Dark")
        explicit_dark = _theme_state(page)
        assert explicit_dark["root"] == "dark"
        assert explicit_dark["app"] == "rgb(11, 17, 32)"
        dark_button_contrast = _assert_primary_button_contrast(page)
        _choose_theme(page, "System")
        system = _theme_state(page)
        assert system["root"] == scheme
        system_button_contrast = _assert_primary_button_contrast(page)
        results[scheme] = {
            "explicit_light": explicit_light,
            "explicit_dark": explicit_dark,
            "system": system,
            "primary_button_contrast": {"light": light_button_contrast, "dark": dark_button_contrast, "system": system_button_contrast},
        }
        context.close()
    return results


def _layout_state(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const root = document.documentElement;
          const body = document.body;
          const controls = [...document.querySelectorAll(
            'button, a, input:not([type="hidden"]), select, summary, [role="button"], [role="combobox"]'
          )];
          const small = controls.filter((el) => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const isSelectProxy = el.matches('input[role="combobox"]') && Boolean(el.closest('[data-baseweb="select"]'));
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
              && !isSelectProxy
              && (rect.width < 44 || rect.height < 44);
          }).map((el) => ({
            tag: el.tagName,
            role: el.getAttribute('role') || '',
            label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40),
            width: Math.round(el.getBoundingClientRect().width),
            height: Math.round(el.getBoundingClientRect().height),
          }));
          const selectTargets = [...document.querySelectorAll('[data-testid="stSelectbox"]')]
            .map((box) => box.querySelector('[role="group"]') || box.querySelector('[data-baseweb="select"]'))
            .filter(Boolean)
            .map((el) => ({
              width: Math.round(el.getBoundingClientRect().width),
              height: Math.round(el.getBoundingClientRect().height),
            }));
          const main = document.querySelector('[data-testid="stMain"]');
          const header = document.querySelector('[data-testid="stHeader"]');
          const block = document.querySelector('[data-testid="stMainBlockContainer"]');
          const firstContent = document.querySelector('.header-card');
          const scrollOwners = [...document.querySelectorAll('body, [data-testid="stAppViewContainer"], [data-testid="stMain"]')]
            .filter((el) => {
              const style = getComputedStyle(el);
              return /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 2;
            }).map((el) => el.getAttribute('data-testid') || el.tagName);
          const select = document.querySelector('[data-testid="stSelectbox"] [data-baseweb="select"]');
          return {
            innerWidth,
            scrollWidth: Math.max(root.scrollWidth, body.scrollWidth),
            horizontalOverflow: Math.max(root.scrollWidth, body.scrollWidth) > innerWidth + 1,
            small,
            smallSelectTargets: selectTargets.filter((rect) => rect.width < 44 || rect.height < 44),
            scrollOwners,
            mainClientHeight: main ? main.clientHeight : null,
            mainScrollHeight: main ? main.scrollHeight : null,
            headerBottom: header ? Math.round(header.getBoundingClientRect().bottom) : null,
            firstContentTop: firstContent ? Math.round(firstContent.getBoundingClientRect().top) : null,
            contentEndGap: main && block ? Math.max(0, Math.round(main.scrollHeight - block.offsetTop - block.offsetHeight)) : null,
            blockPaddingBottom: block ? Math.round(parseFloat(getComputedStyle(block).paddingBottom) || 0) : null,
            selectOverflow: select ? getComputedStyle(select).overflow : null,
          };
        }"""
    )


def _assert_responsive_matrix(page: Page) -> list[dict[str, object]]:
    results = []
    for width, height, label in VIEWPORTS:
        page.set_viewport_size({"width": width, "height": height})
        page.locator('[data-testid="stMain"]').evaluate("el => el.scrollTo(0, 0)")
        page.wait_for_timeout(180)
        state = _layout_state(page)
        assert state["horizontalOverflow"] is False, (label, state)
        assert state["small"] == [], (label, state["small"])
        assert state["smallSelectTargets"] == [], (label, state["smallSelectTargets"])
        assert state["scrollOwners"] in (["stMain"], []), (label, state["scrollOwners"])
        assert state["firstContentTop"] >= state["headerBottom"] - 1, (label, state)
        assert state["contentEndGap"] <= 80, (label, state)
        assert state["blockPaddingBottom"] <= 80, (label, state)
        results.append({"label": label, **state})
    return results


def _assert_select_focus(page: Page) -> dict[str, object]:
    page.set_viewport_size({"width": 390, "height": 844})
    proxy = page.locator('[data-testid="stSelectbox"] input[role="combobox"]').first
    proxy.focus()
    page.wait_for_timeout(80)
    state = proxy.evaluate(
        """(input) => {
          const inputStyle = getComputedStyle(input);
          const selectbox = input.closest('[data-testid="stSelectbox"]');
          const outer = selectbox?.querySelector('[role="group"]') || selectbox?.querySelector('[data-baseweb="select"]');
          const outerStyle = outer ? getComputedStyle(outer) : null;
          const rect = outer?.getBoundingClientRect();
          return {
            inputOutlineStyle: inputStyle.outlineStyle,
            inputOutlineWidth: inputStyle.outlineWidth,
            inputBoxShadow: inputStyle.boxShadow,
            inputBorderWidths: [inputStyle.borderTopWidth, inputStyle.borderRightWidth,
              inputStyle.borderBottomWidth, inputStyle.borderLeftWidth],
            inputCaretColor: inputStyle.caretColor,
            outerBoxShadow: outerStyle?.boxShadow || '',
            outerWidth: rect ? Math.round(rect.width) : 0,
            outerHeight: rect ? Math.round(rect.height) : 0,
          };
        }"""
    )
    assert state["inputOutlineStyle"] == "none", state
    assert state["inputBoxShadow"] == "none", state
    assert set(state["inputBorderWidths"]) == {"0px"}, state
    assert state["inputCaretColor"] in {"transparent", "rgba(0, 0, 0, 0)"}, state
    assert state["outerBoxShadow"] != "none", state
    assert state["outerWidth"] >= 44 and state["outerHeight"] >= 44, state
    return state


def _assert_update_reload(browser: Browser, url: str) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="light")
    page = context.new_page()
    try:
        _wait_for_app(page, url)
        page.evaluate(
            """async () => {
              await caches.open('browser-acceptance-preserve');
              await caches.open('utaipei-graduation-static-browser-old');
            }"""
        )
        dialogs: list[str] = []

        def dismiss_unexpected_dialog(dialog) -> None:
            dialogs.append(dialog.message)
            dialog.dismiss()

        page.on("dialog", dismiss_unexpected_dialog)
        _open_menu(page)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("menuitem", name="更新至最新版").click()
        page.get_by_role("button", name="Main menu").wait_for(state="visible", timeout=30_000)
        page.get_by_role("combobox").first.wait_for(state="visible", timeout=30_000)
        assert "_ut_update=" in page.url
        assert dialogs == []
        cache_names = _cache_names_after_navigation(page)
        assert "browser-acceptance-preserve" in cache_names
        assert "utaipei-graduation-static-browser-old" not in cache_names
        page.evaluate("async () => await caches.delete('browser-acceptance-preserve')")
        return {"url_has_cache_buster": True, "cache_names": cache_names, "dialogs": dialogs}
    finally:
        context.close()


def _cache_names_after_navigation(page: Page) -> list[str]:
    """Read Cache Storage after WebKit's update reload has fully settled."""

    deadline = time.monotonic() + 15
    last_error: PlaywrightError | None = None
    while time.monotonic() < deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
            page.get_by_role("button", name="Main menu").wait_for(state="visible", timeout=5_000)
            return page.evaluate("async () => await caches.keys()")
        except PlaywrightError as exc:
            message = str(exc)
            if "Execution context was destroyed" not in message and "navigation" not in message.lower():
                raise
            last_error = exc
    raise AssertionError("update navigation did not settle before reading Cache Storage") from last_error


_SELECT_SYNC_TIMEOUT_MS = 20_000
_SELECT_SYNC_POLL_MS = 100
_SELECT_STABLE_SAMPLES = 3
_SELECT_CLICK_ATTEMPT_TIMEOUT_MS = 750
_SELECT_CONFIRM_TIMEOUT_MS = 4_000
_SELECT_SELECTED_STABLE_SAMPLES = 8
_SETTINGS_APPLIED_NOTICE = "設定已套用；已依新的手冊與修讀身分更新分析條件。"
_SETTINGS_COMMIT_TIMEOUT_MS = 30_000


def _selectbox_state(page: Page) -> list[dict[str, str]]:
    return page.locator('[data-testid="stSelectbox"]').evaluate_all(
        """els => els.map((el) => {
          const input = el.querySelector('input[role="combobox"]');
          return {
            label: input?.getAttribute('aria-label') || '',
            disabled: input?.getAttribute('aria-disabled') || '',
          };
        })"""
    )


def _selectbox_input(page: Page, label: str):
    """Locate a select input through its stable Streamlit wrapper text.

    BaseWeb rewrites the input's accessible name from the field label to
    ``Selected <value>. <label>`` after a choice.  Locating the input itself
    by accessible name can therefore auto-wait on a name that no longer
    exists.  The wrapper keeps the visible field label across rerenders.
    """

    return (
        page.locator('[data-testid="stSelectbox"]')
        .filter(has_text=re.compile(label))
        .locator('input[role="combobox"]')
        .first
    )


def _wait_for_selectbox_stable(page: Page, *, deadline: float | None = None) -> None:
    """Wait for Streamlit's selectbox DOM to settle after a widget event.

    Streamlit can replace the widget nodes several times during one rerun, so
    the state is sampled through a fresh locator on every poll.  Requiring
    consecutive equal samples makes this an observable DOM synchronization,
    rather than a fixed sleep.
    """

    if deadline is None:
        deadline = time.monotonic() + (_SELECT_SYNC_TIMEOUT_MS / 1_000)
    previous: list[dict[str, str]] | None = None
    stable_samples = 0
    while time.monotonic() < deadline:
        state = _selectbox_state(page)
        if state == previous:
            stable_samples += 1
            if stable_samples >= _SELECT_STABLE_SAMPLES:
                return
        else:
            previous = state
            stable_samples = 1
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1_000))
        page.wait_for_timeout(min(_SELECT_SYNC_POLL_MS, remaining_ms))
    raise AssertionError(f"selectbox DOM did not settle within {_SELECT_SYNC_TIMEOUT_MS}ms")


def _wait_for_selectbox_ready(page: Page, label: str, *, deadline: float | None = None):
    """Return the current enabled combobox for *label*, refetching on reruns."""

    if deadline is None:
        deadline = time.monotonic() + (_SELECT_SYNC_TIMEOUT_MS / 1_000)
    while time.monotonic() < deadline:
        combobox = _selectbox_input(page, label)
        try:
            if combobox.count() == 1 and combobox.is_visible() and combobox.is_enabled():
                if combobox.get_attribute("aria-disabled") != "true":
                    return combobox
        except Exception:
            # The node may have been replaced between the visibility and
            # enabled checks; the next poll obtains a fresh locator.
            pass
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1_000))
        page.wait_for_timeout(min(_SELECT_SYNC_POLL_MS, remaining_ms))
    raise AssertionError(f"selectbox {label!r} was not enabled within {_SELECT_SYNC_TIMEOUT_MS}ms")


def _wait_for_selected_value(
    page: Page,
    label: str,
    option_pattern: str,
    *,
    deadline: float | None = None,
    stable_samples: int = _SELECT_SELECTED_STABLE_SAMPLES,
) -> str:
    """Wait until the rerendered selectbox exposes the selected option."""

    if deadline is None:
        deadline = time.monotonic() + (_SELECT_SYNC_TIMEOUT_MS / 1_000)
    option_re = re.compile(option_pattern)

    def selected_option_value(aria_label: str) -> str | None:
        candidates = [aria_label]
        if aria_label.startswith("Selected "):
            selected = aria_label.removeprefix("Selected ")
            candidates.append(selected.split(". ", maxsplit=1)[0])
        return next((candidate for candidate in candidates if option_re.search(candidate)), None)

    previous_selected: str | None = None
    selected_stable_count = 0
    while time.monotonic() < deadline:
        combobox = _selectbox_input(page, label)
        try:
            if combobox.count() != 1:
                remaining_ms = max(1, int((deadline - time.monotonic()) * 1_000))
                page.wait_for_timeout(min(_SELECT_SYNC_POLL_MS, remaining_ms))
                continue
            aria_label = combobox.get_attribute("aria-label") or ""
            selected_value = selected_option_value(aria_label)
            if combobox.is_visible() and combobox.is_enabled() and selected_value is not None:
                if selected_value == previous_selected:
                    selected_stable_count += 1
                else:
                    previous_selected = selected_value
                    selected_stable_count = 1
                if selected_stable_count >= stable_samples:
                    _wait_for_selectbox_stable(page, deadline=deadline)
                    current = _selectbox_input(page, label)
                    selected = current.get_attribute("aria-label") or ""
                    if selected_option_value(selected) == previous_selected:
                        return selected
            else:
                previous_selected = None
                selected_stable_count = 0
        except Exception:
            # Streamlit may replace this node during the same rerun.
            pass
        remaining_ms = int((deadline - time.monotonic()) * 1_000)
        if remaining_ms > 0:
            page.wait_for_timeout(min(_SELECT_SYNC_POLL_MS, remaining_ms))
    raise AssertionError(
        f"selectbox {label!r} did not select {option_pattern!r} within {_SELECT_SYNC_TIMEOUT_MS}ms"
    )


def _choose_select_option(
    page: Page,
    label: str,
    option_pattern: str,
    *,
    search_text: str | None = None,
) -> str:
    deadline = time.monotonic() + (_SELECT_SYNC_TIMEOUT_MS / 1_000)
    last_error: PlaywrightError | AssertionError | None = None

    def remaining_timeout_ms() -> int:
        return max(1, min(_SELECT_CLICK_ATTEMPT_TIMEOUT_MS, int((deadline - time.monotonic()) * 1_000)))

    def reset_select_interaction() -> None:
        # A detached BaseWeb option can leave its listbox open while the new
        # widget tree is being installed. Escape closes that transient layer;
        # the next loop iteration always obtains fresh locators.
        try:
            page.keyboard.press("Escape")
        except PlaywrightError:
            pass

    while time.monotonic() < deadline:
        try:
            combobox = _wait_for_selectbox_ready(page, label, deadline=deadline)
            combobox.click(timeout=remaining_timeout_ms())
            if search_text:
                # BaseWeb virtualizes long option lists. Typing the exact label makes
                # an off-screen option observable instead of relying on scroll timing.
                combobox.fill(search_text, timeout=remaining_timeout_ms())
            option = page.get_by_role("option", name=re.compile(option_pattern)).first
            option.wait_for(state="visible", timeout=remaining_timeout_ms())
            option.click(timeout=remaining_timeout_ms())
            confirmation_deadline = min(
                deadline,
                time.monotonic() + (_SELECT_CONFIRM_TIMEOUT_MS / 1_000),
            )
            return _wait_for_selected_value(
                page,
                label,
                option_pattern,
                deadline=confirmation_deadline,
            )
        except (PlaywrightError, AssertionError) as exc:
            last_error = exc
            reset_select_interaction()
            remaining_ms = int((deadline - time.monotonic()) * 1_000)
            if remaining_ms > 0:
                page.wait_for_timeout(min(_SELECT_SYNC_POLL_MS, remaining_ms))

    raise AssertionError(
        f"selectbox {label!r} did not select {option_pattern!r} within {_SELECT_SYNC_TIMEOUT_MS}ms"
    ) from last_error


def _apply_settings(page: Page) -> None:
    """Commit the complete draft once after progressive controls are filled."""

    button = page.get_by_role("button", name="套用設定")
    button.click()
    page.get_by_text(_SETTINGS_APPLIED_NOTICE, exact=True).wait_for(
        state="visible",
        timeout=_SETTINGS_COMMIT_TIMEOUT_MS,
    )
    _wait_for_selectbox_stable(page)


def _assert_settings_matrix(browser: Browser, url: str) -> list[dict[str, object]]:
    cases = (
        (375, 812, "111", "物化（電子物理）", "雙主修", "111｜雙主修目標｜資科"),
        (390, 844, "112", "地生（地球環境）", "輔系", "112｜輔系目標｜數學"),
        (768, 1024, "114", "資科", "雙主修", "114｜雙主修目標｜數學"),
        (1440, 900, "115", "數據科學與數學", "雙主修", "115｜雙主修目標｜物化（化學組）"),
    )
    results: list[dict[str, object]] = []
    for width, height, cohort, primary, program_type, target_label in cases:
        context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light")
        page = context.new_page()
        try:
            _wait_for_app(page, url)
            selected = {
                "cohort": _choose_select_option(page, "入學年度", rf"^{cohort} 學年度手冊$"),
                "primary_handbook": _choose_select_option(page, "主修適用學生手冊", rf"^{cohort} 學年度手冊$"),
                "primary": _choose_select_option(page, "主修系所／組別", rf"^{re.escape(primary)}$"),
                "program": _choose_select_option(page, "規劃類型", rf"^{program_type}$"),
            }
            if primary == "數據科學與數學":
                selected["primary_domain"] = _choose_select_option(
                    page, "主修專業領域", r"^數據科學$"
                )
            selected["target_year"] = _choose_select_option(
                page,
                "輔系／雙主修目標課表年度",
                rf"^{cohort} 學年度課表$",
            )
            selected["target"] = _choose_select_option(
                page,
                "輔系／雙主修目標系所／組別",
                rf"^{re.escape(target_label)}$",
                search_text=target_label,
            )
            target_year_top = _selectbox_input(page, "輔系／雙主修目標課表年度").evaluate(
                "el => el.closest('[data-testid=\"stSelectbox\"]')?.getBoundingClientRect().top"
            )
            target_program_top = _selectbox_input(page, "輔系／雙主修目標系所／組別").evaluate(
                "el => el.closest('[data-testid=\"stSelectbox\"]')?.getBoundingClientRect().top"
            )
            assert target_year_top is not None and target_program_top is not None
            assert target_year_top < target_program_top, {
                "target_year_top": target_year_top,
                "target_program_top": target_program_top,
            }
            selected.update(
                {
                "application_year": _choose_select_option(page, "申請年度", rf"^{cohort} 學年度$"),
                "application_semester": _choose_select_option(page, "申請學期", r"^2$"),
                "application_status": _choose_select_option(page, "申請狀態", r"^申請中$"),
                "approval_status": _choose_select_option(page, "系所／學校核准狀態", r"^自述已送出$"),
                }
            )
            _apply_settings(page)
            persisted = {
                "program": _wait_for_selected_value(page, "規劃類型", rf"^{program_type}$"),
                "target_year": _wait_for_selected_value(
                    page, "輔系／雙主修目標課表年度", rf"^{cohort} 學年度課表$"
                ),
                "target": _wait_for_selected_value(
                    page, "輔系／雙主修目標系所／組別", rf"^{re.escape(target_label)}$"
                ),
            }
            if "primary_domain" in selected:
                persisted["primary_domain"] = _wait_for_selected_value(
                    page, "主修專業領域", r"^數據科學$"
                )
            assert f"{program_type}申請與正式資格" in page.locator("body").inner_text()
            assert page.locator(".snapshot-report").count() == 0
            layout = _layout_state(page)
            assert layout["horizontalOverflow"] is False, (cohort, layout)
            assert layout["smallSelectTargets"] == [], (cohort, layout)
            assert all(selected.values()), selected
            results.append(
                {
                    "viewport": f"{width}x{height}",
                    "cohort": cohort,
                    "program_type": program_type,
                    "selected": selected,
                    "persisted": persisted,
                }
            )
        finally:
            context.close()
    return results


def _assert_pwa(page: Page, url: str) -> dict[str, object]:
    metadata = page.evaluate(
        """() => ({
          title: document.title,
          applicationName: document.querySelector('meta[name="application-name"]')?.content || '',
          appleTitle: document.querySelector('meta[name="apple-mobile-web-app-title"]')?.content || '',
          themeColor: document.querySelector('meta[name="theme-color"]')?.content || '',
          manifest: document.querySelector('link[rel="manifest"]')?.getAttribute('href') || '',
          appleIcon: document.querySelector('link[rel="apple-touch-icon"]')?.getAttribute('href') || '',
          viewport: document.querySelector('meta[name="viewport"]')?.content || '',
        })"""
    )
    assert metadata["title"] == "北市大畢業通"
    assert metadata["applicationName"] == "北市大畢業通"
    assert metadata["appleTitle"] in {"北市大畢業通", "畢業通"}
    assert metadata["themeColor"] == "#1E3A5F"
    assert "viewport-fit=cover" in metadata["viewport"]

    manifest_url = urljoin(url, metadata["manifest"])
    manifest_response = page.request.get(manifest_url)
    assert manifest_response.ok
    manifest = manifest_response.json()
    assert manifest["name"] == "北市大畢業通"
    assert manifest["short_name"] == "畢業通"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["theme_color"] == "#1E3A5F"
    assert manifest["background_color"] == "#F8FAFC"
    sizes = {item["sizes"] for item in manifest["icons"]}
    assert {"180x180", "192x192", "512x512"}.issubset(sizes)
    assert any("maskable" in item.get("purpose", "") for item in manifest["icons"])

    worker_url = urljoin(url, "/service-worker.js")
    worker_response = page.request.get(worker_url)
    assert worker_response.ok
    worker_source = worker_response.text()
    assert "UTAIPEI_SERVICE_WORKER_V2_BEGIN" in worker_source
    assert "CACHE_PREFIX = 'utaipei-graduation-static-'" in worker_source
    assert "request.mode === 'navigate'" in worker_source
    assert "!url.search" in worker_source
    assert worker_response.headers.get("content-type", "").startswith("application/javascript")

    registration = page.evaluate(
        """async () => {
          if (!('serviceWorker' in navigator)) return {supported: false};
          const ready = await Promise.race([
            navigator.serviceWorker.ready,
            new Promise((resolve) => setTimeout(() => resolve(null), 5000)),
          ]);
          const registrations = await navigator.serviceWorker.getRegistrations();
          return {
            supported: true,
            controlled: Boolean(navigator.serviceWorker.controller),
            readyScope: ready ? ready.scope : '',
            registrations: registrations.map((item) => ({
              scope: item.scope,
              active: item.active ? item.active.scriptURL : '',
            })),
          };
        }"""
    )
    assert registration["supported"] is True
    assert registration["registrations"]
    assert any(item["active"].endswith("/service-worker.js") for item in registration["registrations"])
    return {"metadata": metadata, "manifest": manifest, "service_worker": registration}


def _download(page: Page, label: str, destination: Path) -> bytes:
    with page.expect_download(timeout=15_000) as pending:
        page.get_by_role("button", name=label).click()
    download = pending.value
    download.save_as(destination)
    return destination.read_bytes()


def _assert_analysis_flow(page: Page, fixture: Path, output_dir: Path) -> dict[str, object]:
    # The bundled synthetic transcript explicitly declares a 114 admission
    # cohort and the CS department.  Keep this end-to-end fixture aligned with
    # the selected handbook before upload; otherwise the application's
    # intentional cohort-mismatch gate correctly refuses confirmation and the
    # test would wait for a report that must not exist.
    _choose_select_option(page, "入學年度", r"^114 學年度手冊$")
    _choose_select_option(page, "主修適用學生手冊", r"^114 學年度手冊$")
    _choose_select_option(page, "主修系所／組別", r"^資科$")
    _apply_settings(page)
    page.locator('input[type="file"]').set_input_files(fixture)
    confirm = page.get_by_role("button", name="確認目前成績列")
    confirm.wait_for(state="visible", timeout=30_000)
    editor = page.locator(
        '[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"], [data-testid="stDataEditor"]'
    )
    editor.first.wait_for(state="visible", timeout=30_000)
    data_testids = page.locator("[data-testid]").evaluate_all(
        "els => [...new Set(els.map(el => el.dataset.testid).filter(value => /data/i.test(value)))].sort()"
    )
    confirmation_text = page.locator("body").inner_text()
    assert editor.count() >= 1, {
        "data_testids": data_testids,
        "contenteditable": page.locator('[contenteditable="true"]').count(),
        "canvases": page.locator("canvas").count(),
        "grids": page.locator('[role="grid"]').count(),
        "iframes": page.locator("iframe").count(),
        "has_empty_rows_message": "目前沒有可供確認的課程列" in confirmation_text,
        "has_expected_course": "普通物理" in confirmation_text,
        "has_masked_student": "Z9••••99" in confirmation_text,
    }
    assert "Z999999999" not in page.locator("body").inner_text()
    preview = page.locator(".snapshot-import-preview")
    preview.wait_for(state="visible", timeout=30_000)
    preview_row_count = int(preview.get_attribute("data-row-count") or "-1")
    preview_earned_credits = float(preview.get_attribute("data-earned-credits") or "-1")
    assert preview_row_count == 5
    assert preview.locator("tbody tr").count() == 5
    assert preview_earned_credits == 9
    preview_text = preview.inner_text()
    assert "待確認" in preview_text
    assert "僅供核對" in preview_text
    assert page.locator(".snapshot-report").count() == 0
    confirm.click()
    page.wait_for_function(
        """() => {
        const reports = [...document.querySelectorAll('.snapshot-report')];
          const report = reports.at(-1);
          return reports.length === 1
            && report.dataset.snapshotId
            && report?.innerText.includes('計算結果')
            && report?.innerText.includes('資料確認：')
            && report.querySelectorAll('.snapshot-requirement-expander').length > 0;
        }""",
        timeout=30_000,
    )

    body_text = page.locator("body").inner_text()
    _assert_no_raw_markup(page)
    assert "主修畢業要求" in body_text
    assert "目前計算結果" in body_text
    assert "UNKNOWN" not in body_text
    assert page.locator(".snapshot-requirement-expander").count() > 0
    report = page.locator(".snapshot-report")
    statistics_schema = report.get_attribute("data-statistics-schema")
    statistics_digest = report.get_attribute("data-statistics-digest")
    assert statistics_schema == "decision-statistics.v2"
    assert statistics_digest and statistics_digest.startswith("sha256:")
    # v2 charts fail closed when their source dataset is not safe to chart;
    # an explicit unavailable card is still a successful rendering contract.
    assert report.locator('.lf-f1-chart, .lf-chart-unavailable[data-chart-id="F1"]').count() >= 1
    assert report.locator('.lf-f5-chart, .lf-chart-unavailable[data-chart-id="F5"]').count() >= 1
    # The optional status-distribution chart is omitted when the curriculum
    # exceeds its four-category capacity; course detail remains authoritative.
    assert report.locator('.lf-f11-chart, .lf-chart-unavailable[data-chart-id="F11"]').count() >= 1
    # Scope chart checks to the single current snapshot. Streamlit may retain a
    # detached, hidden element while reconciling a previous rerun; that node is
    # not part of the report a user can inspect and must not contaminate this
    # rendering assertion.
    unavailable = report.locator(".lf-chart-unavailable")
    for index in range(unavailable.count()):
        chart = unavailable.nth(index)
        reason_node = chart.locator(".lf-chart-unavailable-reason")
        reason = (reason_node.text_content() or "").strip()
        assert reason, {
            "chart_index": index,
            "chart_id": chart.get_attribute("data-chart-id"),
            "reason_count": reason_node.count(),
            "chart_visible": chart.is_visible(),
        }
        chart_details = chart.locator("xpath=ancestor::details[1]")
        if chart_details.count() and chart_details.get_attribute("open") is None:
            chart_details.locator(":scope > summary").click()
        reason_node.wait_for(state="visible", timeout=5_000)
        assert reason_node.inner_text().strip() == reason
    f5_chart = report.locator(".lf-f5-chart")
    if f5_chart.count():
        # After confirmation, this short synthetic transcript has definite
        # credit deficits; it is no longer the unconfirmed PENDING report.
        chart_details = f5_chart.first.locator("xpath=ancestor::details[1]")
        if chart_details.count() and chart_details.get_attribute("open") is None:
            chart_details.locator(":scope > summary").click()
        f5_table = f5_chart.first.locator(".lf-data-table")
        f5_table.wait_for(state="visible", timeout=5_000)
        headers = f5_table.locator("thead th").all_inner_texts()
        assert {"項目", "已完成", "門檻", "進度", "狀態"}.issubset(headers)
        assert f5_table.locator('td[data-status="FAIL"]').count() >= 1

    cs_electives = report.locator(".snapshot-cs-electives")
    if cs_electives.count():
        cs_summary = cs_electives.locator(":scope > summary")
        assert "54 學分" in cs_summary.inner_text()
        if cs_electives.get_attribute("open") is None:
            cs_summary.click()
        assert "甲類指定課程：32 學分" in cs_electives.inner_text()
        assert "乙類選修：22 學分" in cs_electives.inner_text()
    first_requirement = report.locator(".snapshot-requirement-expander").first
    first_requirement.locator(":scope > summary").click()
    page.wait_for_function("el => el.open === true", arg=first_requirement.element_handle(), timeout=5_000)
    page.wait_for_timeout(100)
    expanded = first_requirement.evaluate(
        """(el) => ({
          open: el.open,
          bodyHeight: el.querySelector('.snapshot-requirement-body')?.scrollHeight || 0,
          maxHeight: getComputedStyle(el.querySelector('.snapshot-requirement-body')).maxHeight,
          overflow: getComputedStyle(el.querySelector('.snapshot-requirement-body')).overflow,
        })"""
    )
    assert expanded["open"] is True
    assert expanded["bodyHeight"] > 0, expanded
    assert expanded["maxHeight"] == "none"
    assert expanded["overflow"] in {"visible", "clip"}

    before_url = page.url
    dialog_messages: list[str] = []

    def dismiss_update(dialog) -> None:
        dialog_messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", dismiss_update)
    _open_menu(page)
    page.get_by_role("menuitem", name="更新至最新版").click()
    page.wait_for_timeout(400)
    assert dialog_messages and "暫存分析資料" in dialog_messages[0]
    assert page.url == before_url
    assert page.locator(".snapshot-report").count() == 1
    if page.get_by_role("button", name="Main menu").get_attribute("aria-expanded") == "true":
        page.get_by_role("button", name="Main menu").click()

    snapshot_id = page.locator(".snapshot-report").get_attribute("data-snapshot-id")
    statistics_digest = page.locator(".snapshot-report").get_attribute("data-statistics-digest")
    assert snapshot_id and snapshot_id.startswith("snapshot:")
    assert statistics_digest and statistics_digest.startswith("sha256:")
    page.get_by_role("button", name="準備匯出檔案").click()
    page.get_by_role("button", name="下載列印 PDF").wait_for(state="visible", timeout=30_000)
    pdf = _download(page, "下載列印 PDF", output_dir / "report.pdf")
    csv_bytes = _download(page, "下載課程配置 CSV", output_dir / "allocation.csv")
    audit_bytes = _download(page, "下載規則與判定摘要", output_dir / "audit.json")
    audit = json.loads(audit_bytes.decode("utf-8"))
    csv_rows = list(csv_module.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert csv_rows
    page.wait_for_function(
        "id => { const reports = [...document.querySelectorAll('.snapshot-report')]; return reports.length === 1 && reports[0].dataset.snapshotId === id; }",
        arg=snapshot_id,
        timeout=10_000,
    )
    assert pdf.startswith(b"%PDF-")
    assert audit["snapshot_id"] == snapshot_id
    assert audit["statistics_digest"] == statistics_digest
    assert {row["報表編號"] for row in csv_rows} == {snapshot_id}
    assert "課程名稱" in csv_rows[0]
    assert "採計原因" in csv_rows[0]
    assert not re.search(r"\b(?:UNKNOWN|PASS|FAIL|NOT_APPLICABLE|EXCLUSIVE|SHARED_SHADOW)\b", csv_bytes.decode("utf-8-sig"))
    assert all(_public_reason(item, "部分進度圖表暫時無法顯示") in body_text for item in audit["presentation_warnings"])
    assert snapshot_id.encode() in csv_bytes
    assert b"Z999999999" not in pdf + csv_bytes + audit_bytes
    with fitz.open(stream=pdf, filetype="pdf") as document:
        assert document.page_count >= 1
        pdf_text = "\n".join(page.get_text() for page in document)
    assert snapshot_id in pdf_text
    assert "有效學分" in pdf_text
    assert "各項畢業要求" in pdf_text
    assert not re.search(r"\b(?:UNKNOWN|PASS|FAIL|NOT_APPLICABLE|EXCLUSIVE|SHARED_SHADOW)\b", pdf_text)

    return {
        "snapshot_id": snapshot_id,
        "statistics_digest": statistics_digest,
        "presentation_warnings": audit["presentation_warnings"],
        "requirements": page.locator(".snapshot-requirement-expander").count(),
        "expanded": expanded,
        "downloads": {"pdf": len(pdf), "csv": len(csv_bytes), "audit": len(audit_bytes)},
        "update_guard": dialog_messages[0],
    }


def run(url: str, browser_name: str, fixture: Path | None) -> dict[str, object]:
    if sync_playwright is None:
        raise RuntimeError("瀏覽器驗證需要先安裝 Playwright 與對應瀏覽器。")
    with sync_playwright() as playwright:
        launcher = getattr(playwright, browser_name)
        browser = launcher.launch(headless=True)
        try:
            theme = _assert_theme_matrix(browser, url)
            context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", accept_downloads=True)
            page = context.new_page()
            _wait_for_app(page, url)
            select_focus = _assert_select_focus(page)
            pwa = _assert_pwa(page, url)
            with tempfile.TemporaryDirectory(prefix="utaipei-browser-") as raw_output:
                output_dir = Path(raw_output)
                if fixture is None:
                    fixture_path = output_dir / "synthetic-transcript.pdf"
                    fixture_path.write_bytes(build_synthetic_transcript_pdf())
                else:
                    fixture_path = fixture
                analysis = _assert_analysis_flow(page, fixture_path, output_dir)
                responsive = _assert_responsive_matrix(page)
            context.close()
            update = _assert_update_reload(browser, url)
            settings = _assert_settings_matrix(browser, url)
            return {
                "browser": browser_name,
                "url": url,
                "theme": theme,
                "pwa": pwa,
                "select_focus": select_focus,
                "analysis": analysis,
                "responsive": responsive,
                "update": update,
                "settings": settings,
            }
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8505/")
    parser.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    result = run(args.url, args.browser, args.fixture)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
