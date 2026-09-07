"""One-shot, privacy-safe browser smoke test against the deployed HF Space.

The credential values are read inside this process and are never emitted in
stdout, stderr, screenshots, traces, HAR files, browser-console capture, or
exception output.  The browser is restricted to the exact authorized origin,
and the submit button is clicked exactly once.

This script is deployment tooling.  It is intentionally not a pytest test and
must only be run after an explicit authorization for one live credential test.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    WebSocketRoute,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.portal_live_smoke import (  # noqa: E402
    CredentialFileError,
    load_portal_credentials,
)

PUBLIC_URL = "https://sapphirejimmy-utaipei-credit-checker.hf.space/"
_AUTHORIZED_HOST = "sapphirejimmy-utaipei-credit-checker.hf.space"
_TERMINAL_STATES = frozenset({"SUCCESS", "ERROR"})
_MARKER_STATES = frozenset({"IDLE", "RUNNING", "SUCCESS", "ERROR"})
_MARKER_CODES = frozenset(
    {
        "IDLE",
        "RUNNING",
        "SUCCESS",
        "NETWORK_BLOCKED",
        "CAPTCHA_REQUIRED",
        "SESSION_REJECTED",
        "PORTAL_CHANGED",
        "UPSTREAM_TIMEOUT",
        "PDF_NOT_FOUND",
        "AUTH_REJECTED",
        "RATE_LIMITED",
        "TRANSCRIPT_IDENTITY_MISMATCH",
        "TRANSCRIPT_VALIDATION_FAILED",
    }
)
_INVALID_MARKER = "INVALID_MARKER"
_NO_TERMINAL_STATE = "NO_TERMINAL_STATE"
_ALLOWED_COHORT_YEARS = frozenset({"111", "112", "113", "114", "115"})
_COHORT_WARNING_RE = re.compile(r"^成績資料辨識為 ([0-9]{3}) 學年度")
_APP_READY_TIMEOUT_MS = 90_000
_START_STATE_TIMEOUT_MS = 30_000
_TERMINAL_TIMEOUT_SECONDS = 75.0
_CLEANUP_TIMEOUT_MS = 20_000
_CONFIRMATION_TIMEOUT_MS = 15_000


class SmokeCheckFailed(RuntimeError):
    """Internal fail-closed signal with no dynamic message."""


def _is_allowed_http_origin(url: object) -> bool:
    """Return whether an HTTP(S) URL belongs to the exact public origin."""

    try:
        parsed = urlsplit(str(url))
        return (
            parsed.scheme.lower() == "https"
            and (parsed.hostname or "").lower() == _AUTHORIZED_HOST
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except (TypeError, ValueError):
        return False


def _is_exact_public_page(url: object) -> bool:
    """Require the credential-bearing document to be the authorized root."""

    if not _is_allowed_http_origin(url):
        return False
    try:
        parsed = urlsplit(str(url))
        return parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
    except (TypeError, ValueError):
        return False


def _is_allowed_websocket_origin(url: object) -> bool:
    """Allow only the wss equivalent of the exact HTTPS public origin."""

    try:
        parsed = urlsplit(str(url))
        return (
            parsed.scheme.lower() == "wss"
            and (parsed.hostname or "").lower() == _AUTHORIZED_HOST
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except (TypeError, ValueError):
        return False


def _route_http_request(route) -> None:
    """Abort every HTTP(S) request that is not on the authorized origin."""

    try:
        url = route.request.url
        if _is_allowed_http_origin(url):
            route.continue_()
            return
        route.abort()
    except Exception:
        # A closed or already-handled request must not leak a dynamic exception
        # to the command output.  A failed request also keeps the smoke test
        # fail-closed because the required UI state will not be observed.
        return


def _route_websocket(websocket: WebSocketRoute) -> None:
    """Route WebSockets separately; Playwright HTTP routes do not cover them."""

    try:
        if _is_allowed_websocket_origin(websocket.url):
            websocket.connect_to_server()
        else:
            websocket.close()
    except Exception:
        return


def _new_restricted_context(browser: Browser) -> BrowserContext:
    """Create a context with service workers and cross-origin traffic closed."""

    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        service_workers="block",
    )
    context.route("**/*", _route_http_request)
    context.route_web_socket("**/*", _route_websocket)
    return context


def _wait_for_app(page: Page) -> None:
    page.goto(PUBLIC_URL, wait_until="domcontentloaded", timeout=_APP_READY_TIMEOUT_MS)
    page.get_by_role("button", name="Main menu").wait_for(
        state="visible",
        timeout=_APP_READY_TIMEOUT_MS,
    )
    page.get_by_role("combobox").first.wait_for(
        state="visible",
        timeout=_APP_READY_TIMEOUT_MS,
    )


def _safe_marker_value(value: object, allowed: frozenset[str]) -> str:
    value = value if isinstance(value, str) else ""
    return value if value in allowed else _INVALID_MARKER


def _portal_marker(page: Page) -> tuple[int, str, str]:
    """Read exactly one marker and normalize all DOM values to fixed enums."""

    try:
        values = page.locator("[data-utaipei-portal-state]").evaluate_all(
            """els => els.map((el) => ({
              state: el.getAttribute('data-utaipei-portal-state') || '',
              code: el.getAttribute('data-utaipei-portal-code') || '',
            }))"""
        )
    except PlaywrightError:
        return 0, _INVALID_MARKER, _INVALID_MARKER
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        count = min(len(values), 2) if isinstance(values, list) else 0
        return count, _INVALID_MARKER, _INVALID_MARKER
    return (
        1,
        _safe_marker_value(values[0].get("state"), _MARKER_STATES),
        _safe_marker_value(values[0].get("code"), _MARKER_CODES),
    )


def _has_confirmation_gate(page: Page) -> bool:
    try:
        return page.get_by_role("button", name="確認目前成績列", exact=True).count() > 0
    except PlaywrightError:
        return False


def _confirmation_gate_present(page: Page) -> bool:
    """Return whether any exact confirmation button is visibly present."""

    try:
        gates = page.get_by_role("button", name="確認目前成績列", exact=True)
        for index in range(gates.count()):
            if gates.nth(index).is_visible():
                return True
    except PlaywrightError:
        return False
    return False


def _cohort_mismatch_present(page: Page) -> bool:
    """Return whether the exact cohort acknowledgment checkbox is visible."""

    try:
        checkbox = page.get_by_role(
            "checkbox",
            name="我已核對適用規定，仍使用目前選定手冊",
            exact=True,
        )
        for index in range(checkbox.count()):
            if checkbox.nth(index).is_visible():
                return True
    except PlaywrightError:
        return False
    return False


def _confirmation_is_ready(page: Page) -> bool:
    """Require parsed rows that the application actually permits confirming."""

    try:
        gates = page.get_by_role("button", name="確認目前成績列", exact=True)
        for index in range(gates.count()):
            gate = gates.nth(index)
            if gate.is_visible() and gate.is_enabled():
                return True
    except PlaywrightError:
        return False
    return False


def _parse_cohort_warning_year(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    match = _COHORT_WARNING_RE.match(text.strip())
    return match.group(1) if match else None


def _cohort_warning_year(text: object) -> str | None:
    """Return an allowlisted cohort year from an anchored warning prefix."""

    year = _parse_cohort_warning_year(text)
    return year if year in _ALLOWED_COHORT_YEARS else None


def _observed_cohort_year(page: Page) -> str | None:
    """Read one visible matching Streamlit alert without scanning page text."""

    try:
        alerts = page.locator('[data-testid="stAlert"]')
        years: list[str] = []
        for index in range(alerts.count()):
            alert = alerts.nth(index)
            if not alert.is_visible():
                continue
            year = _parse_cohort_warning_year(alert.inner_text())
            if year is not None:
                years.append(year)
        if len(years) != 1:
            return None
        return _cohort_warning_year(f"成績資料辨識為 {years[0]} 學年度")
    except PlaywrightError:
        return None


def _selectbox_inputs(page: Page, label: str):
    return (
        page.locator('[data-testid="stSelectbox"]')
        .filter(has_text=re.compile(re.escape(label)))
        .locator('input[role="combobox"]')
    )


def _wait_for_selectbox(page: Page, label: str):
    deadline = time.monotonic() + (_CONFIRMATION_TIMEOUT_MS / 1_000)
    while time.monotonic() < deadline:
        try:
            inputs = _selectbox_inputs(page, label)
            for index in range(inputs.count()):
                candidate = inputs.nth(index)
                if (
                    candidate.is_visible()
                    and candidate.is_enabled()
                    and candidate.get_attribute("aria-disabled") != "true"
                ):
                    return candidate
        except PlaywrightError:
            pass
        remaining_ms = int((deadline - time.monotonic()) * 1_000)
        if remaining_ms > 0:
            try:
                page.wait_for_timeout(min(100, remaining_ms))
            except PlaywrightError:
                return None
    return None


def _wait_for_selected_cohort(page: Page, label: str, option_name: str) -> bool:
    deadline = time.monotonic() + (_CONFIRMATION_TIMEOUT_MS / 1_000)
    stable_samples = 0
    while time.monotonic() < deadline:
        selected = False
        try:
            inputs = _selectbox_inputs(page, label)
            for index in range(inputs.count()):
                candidate = inputs.nth(index)
                aria_label = candidate.get_attribute("aria-label") or ""
                if candidate.is_visible() and candidate.is_enabled() and option_name in aria_label:
                    selected = True
                    break
        except PlaywrightError:
            pass
        stable_samples = stable_samples + 1 if selected else 0
        if stable_samples >= 8:
            return True
        remaining_ms = int((deadline - time.monotonic()) * 1_000)
        if remaining_ms > 0:
            try:
                page.wait_for_timeout(min(100, remaining_ms))
            except PlaywrightError:
                return False
    return False


def _select_cohort_option(page: Page, label: str, year: str) -> bool:
    if year not in _ALLOWED_COHORT_YEARS:
        return False
    option_name = f"{year} 學年度手冊"
    try:
        combobox = _wait_for_selectbox(page, label)
        if combobox is None:
            return False
        combobox.click(timeout=750)
        option = page.get_by_role("option", name=option_name, exact=True)
        option.wait_for(state="visible", timeout=5_000)
        if option.count() != 1 or not option.is_visible():
            return False
        option.click(timeout=750)
        return _wait_for_selected_cohort(page, label, option_name)
    except PlaywrightError:
        return False


def _apply_cohort_settings(page: Page) -> bool:
    try:
        button = page.get_by_role("button", name="套用設定", exact=True)
        if button.count() != 1 or not button.is_visible() or not button.is_enabled():
            return False
        button.click(timeout=5_000)
        return True
    except PlaywrightError:
        return False


def _align_cohort_settings(page: Page, year: str) -> bool:
    if year not in _ALLOWED_COHORT_YEARS:
        return False
    for label in ("入學年度", "主修適用學生手冊"):
        if not _select_cohort_option(page, label, year):
            return False
    if not _apply_cohort_settings(page):
        return False
    return _wait_until(
        page,
        lambda current: not _cohort_mismatch_present(current) and _confirmation_is_ready(current),
        _CONFIRMATION_TIMEOUT_MS,
    )


def _has_preloaded_transcript_ui(page: Page) -> bool:
    """Detect fixed transcript widgets without copying page text to output."""

    try:
        for selector in (
            '[data-testid="stDataEditor"]',
            '[data-testid="stDataFrame"]',
            ".course-list",
            ".report-table-wrap",
        ):
            if page.locator(selector).count() > 0:
                return True
        return page.get_by_text("成績資料：", exact=False).count() > 0
    except PlaywrightError:
        return False


def _is_clean_idle(page: Page) -> bool:
    marker_count, state, code = _portal_marker(page)
    return (
        marker_count == 1
        and state == "IDLE"
        and code == "IDLE"
        and not _has_confirmation_gate(page)
        and not _has_preloaded_transcript_ui(page)
    )


def _wait_until(page: Page, predicate, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1_000
    while time.monotonic() < deadline:
        try:
            if predicate(page):
                return True
        except PlaywrightError:
            pass
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1_000))
        try:
            page.wait_for_timeout(min(200, remaining_ms))
        except PlaywrightError:
            return False
    return False


def _assert_pre_fill_clean(page: Page) -> None:
    """Guard the one credential submission with an exact clean UI boundary."""

    if not _is_exact_public_page(page.url):
        raise SmokeCheckFailed
    if not _wait_until(page, _is_clean_idle, _START_STATE_TIMEOUT_MS):
        raise SmokeCheckFailed


def _wait_for_terminal_state(page: Page) -> tuple[int, str, str, int]:
    started = time.monotonic()
    deadline = started + _TERMINAL_TIMEOUT_SECONDS
    last = (0, _NO_TERMINAL_STATE, _NO_TERMINAL_STATE)
    while time.monotonic() < deadline:
        try:
            last = _portal_marker(page)
            if last[0] == 1 and last[1] in _TERMINAL_STATES:
                break
        except PlaywrightError:
            pass
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1_000))
        try:
            page.wait_for_timeout(min(200, remaining_ms))
        except PlaywrightError:
            break
    elapsed_ms = round((time.monotonic() - started) * 1_000)
    return (*last, elapsed_ms)


def _credentials_are_empty(page: Page) -> bool:
    try:
        account = page.get_by_label("學號", exact=True)
        password = page.get_by_label("密碼", exact=True)
        return (
            account.count() == 1
            and password.count() == 1
            and account.input_value() == ""
            and password.input_value() == ""
        )
    except PlaywrightError:
        return False


def _wait_for_credentials_empty(page: Page) -> bool:
    return _wait_until(page, lambda current: _credentials_are_empty(current), _CONFIRMATION_TIMEOUT_MS)


def _open_data_panel(page: Page) -> None:
    panel = page.locator('[data-testid="stExpander"]').filter(
        has_text="成績資料與校務系統（點開載入）"
    ).first
    if panel.count() != 1:
        return
    summary = panel.locator(":scope > details > summary")
    if summary.count() == 0:
        summary = panel.locator("summary").first
    details = panel.locator("details").first
    if details.count() == 1 and details.get_attribute("open") is None:
        summary.click(timeout=5_000)


def _is_cleared_ui(page: Page) -> bool:
    marker_count, state, code = _portal_marker(page)
    return (
        marker_count == 1
        and state == "IDLE"
        and code == "IDLE"
        and not _has_confirmation_gate(page)
        and not _has_preloaded_transcript_ui(page)
    )


def _clear_ui_data(page: Page | None) -> bool:
    """Click Clear once and prove the server rerun produced IDLE/IDLE."""

    if page is None:
        return False
    try:
        _open_data_panel(page)
        clear = page.get_by_role("button", name="清除目前資料", exact=True)
        clear.wait_for(state="visible", timeout=5_000)
        clear.click(timeout=5_000)
        return _wait_until(page, _is_cleared_ui, _CLEANUP_TIMEOUT_MS)
    except PlaywrightError:
        return False


def _clear_browser_state(context: BrowserContext | None, page: Page | None) -> dict[str, bool]:
    """Clear and verify browser state without returning any dynamic values."""

    local_storage_empty = False
    session_storage_empty = False
    cache_storage_empty = False
    cookies_cleared = False
    if context is not None and page is not None:
        try:
            storage = page.evaluate(
                """async () => {
                  localStorage.clear();
                  sessionStorage.clear();
                  if (!window.caches || typeof window.caches.keys !== 'function') {
                    return {local: localStorage.length, session: sessionStorage.length, cache: false};
                  }
                  const before = await window.caches.keys();
                  await Promise.all(before.map((key) => window.caches.delete(key)));
                  const after = await window.caches.keys();
                  return {
                    local: localStorage.length,
                    session: sessionStorage.length,
                    cache: after.length === 0,
                  };
                }"""
            )
            if isinstance(storage, dict):
                local_storage_empty = storage.get("local") == 0
                session_storage_empty = storage.get("session") == 0
                cache_storage_empty = storage.get("cache") is True
        except PlaywrightError:
            pass
        try:
            context.clear_cookies()
            cookies_cleared = not bool(context.cookies())
        except PlaywrightError:
            pass
    return {
        "local_storage_empty": local_storage_empty,
        "session_storage_empty": session_storage_empty,
        "cache_storage_empty": cache_storage_empty,
        "cookies_cleared": cookies_cleared,
        "browser_state_cleared": (
            local_storage_empty
            and session_storage_empty
            and cache_storage_empty
            and cookies_cleared
        ),
    }


def _safe_close(resource: object | None) -> bool:
    if resource is None:
        return False
    try:
        resource.close()
        return True
    except Exception:
        return False


def _fresh_context_starts_clean(browser: Browser) -> bool:
    """Observe clean state in a new context; this does not prove old-session GC."""

    context: BrowserContext | None = None
    clean = False
    try:
        context = _new_restricted_context(browser)
        page = context.new_page()
        _wait_for_app(page)
        clean = _is_exact_public_page(page.url) and _wait_until(
            page,
            _is_clean_idle,
            _START_STATE_TIMEOUT_MS,
        )
    except Exception:
        clean = False
    finally:
        closed = _safe_close(context)
    return clean and closed


def _initial_result() -> dict[str, object]:
    return {
        "overall_status": "FAILED",
        "marker_count": 0,
        "state": _NO_TERMINAL_STATE,
        "code": _NO_TERMINAL_STATE,
        "terminal": False,
        "confirmation_gate": False,
        "confirmation_gate_present": False,
        "cohort_mismatch_present": False,
        "cohort_alignment_needed": False,
        "matching_cohort_selected": False,
        "credential_fields_empty": False,
        "elapsed_ms": 0,
        "ui_data_cleared": False,
        "local_storage_empty": False,
        "session_storage_empty": False,
        "cache_storage_empty": False,
        "cookies_cleared": False,
        "browser_state_cleared": False,
        "fresh_context_starts_clean": False,
        "submit_count": 0,
        "context_closed": False,
        "browser_closed": False,
    }


def run(credentials_file: Path) -> dict[str, object]:
    """Run exactly one credential submission and return fixed safe metrics."""

    account, password = load_portal_credentials(credentials_file)
    result = _initial_result()
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
                context = _new_restricted_context(browser)
                page = context.new_page()
                _wait_for_app(page)
                _assert_pre_fill_clean(page)

                page.get_by_label("學號", exact=True).fill(account)
                page.get_by_label("密碼", exact=True).fill(password)
                submit = page.get_by_role(
                    "button",
                    name="登入並抓取成績單",
                    exact=True,
                )
                submit.click(timeout=5_000)
                result["submit_count"] = 1
                account = ""
                password = ""

                marker_count, state, code, elapsed_ms = _wait_for_terminal_state(page)
                result.update(
                    {
                        "marker_count": marker_count,
                        "state": state,
                        "code": code,
                        "terminal": marker_count == 1 and state in _TERMINAL_STATES,
                        "elapsed_ms": elapsed_ms,
                        "credential_fields_empty": _wait_for_credentials_empty(page),
                    }
                )
                if state == "SUCCESS":
                    _wait_until(
                        page,
                        lambda current: _confirmation_is_ready(current) or _cohort_mismatch_present(current),
                        _CONFIRMATION_TIMEOUT_MS,
                    )
                    result["cohort_alignment_needed"] = _cohort_mismatch_present(page)
                    if result["cohort_alignment_needed"] is True:
                        observed_year = _observed_cohort_year(page)
                        if observed_year is not None:
                            result["matching_cohort_selected"] = _align_cohort_settings(page, observed_year)
                    if result["cohort_alignment_needed"] is False or result["matching_cohort_selected"] is True:
                        result["confirmation_gate"] = _wait_until(
                            page,
                            lambda current: _confirmation_is_ready(current),
                            _CONFIRMATION_TIMEOUT_MS,
                        )
                    result["confirmation_gate_present"] = _confirmation_gate_present(page)
                    result["cohort_mismatch_present"] = _cohort_mismatch_present(page)

                lifecycle_success = (
                    result["submit_count"] == 1
                    and result["marker_count"] == 1
                    and result["state"] == "SUCCESS"
                    and result["code"] == "SUCCESS"
                    and result["terminal"] is True
                    and result["confirmation_gate"] is True
                    and result["credential_fields_empty"] is True
                )
                result["overall_status"] = "PASS" if lifecycle_success else "FAILED"
            except Exception:
                result["code"] = "BROWSER_TEST_FAILED"
            finally:
                account = ""
                password = ""
                result["ui_data_cleared"] = _clear_ui_data(page)
                result.update(_clear_browser_state(context, page))
                result["context_closed"] = _safe_close(context)
                if browser is not None and result["context_closed"] is True:
                    result["fresh_context_starts_clean"] = _fresh_context_starts_clean(browser)
                result["browser_closed"] = _safe_close(browser)
                cleanup_success = (
                    result["ui_data_cleared"] is True
                    and result["browser_state_cleared"] is True
                    and result["fresh_context_starts_clean"] is True
                    and result["context_closed"] is True
                    and result["browser_closed"] is True
                )
                if not cleanup_success:
                    result["overall_status"] = "FAILED"
    except Exception:
        result["code"] = "BROWSER_TEST_FAILED"
        result["overall_status"] = "FAILED"
    finally:
        account = ""
        password = ""
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe deployed HF browser smoke test")
    parser.add_argument("--credentials-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.credentials_file)
    except CredentialFileError:
        result = {
            "overall_status": "FAILED",
            "code": "CREDENTIAL_FILE_INVALID",
            "submit_count": 0,
        }
    except Exception:
        result = {
            "overall_status": "FAILED",
            "code": "BROWSER_TEST_FAILED",
            "submit_count": 0,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
