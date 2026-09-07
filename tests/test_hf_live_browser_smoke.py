from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import scripts.hf_live_browser_smoke as smoke


class _FakeRoute:
    def __init__(self, url: str):
        self.request = SimpleNamespace(url=url)
        self.aborted = 0
        self.continued = 0

    def abort(self) -> None:
        self.aborted += 1

    def continue_(self) -> None:
        self.continued += 1


class _FakeWebSocket:
    def __init__(self, url: str):
        self.url = url
        self.closed = 0
        self.connected = 0

    def close(self) -> None:
        self.closed += 1

    def connect_to_server(self) -> None:
        self.connected += 1


def test_exact_public_page_rejects_redirects_queries_and_userinfo():
    assert smoke._is_exact_public_page(smoke.PUBLIC_URL)
    assert not smoke._is_exact_public_page("http://sapphirejimmy-utaipei-credit-checker.hf.space/")
    assert not smoke._is_exact_public_page("https://sapphirejimmy-utaipei-credit-checker.hf.space/other")
    assert not smoke._is_exact_public_page("https://sapphirejimmy-utaipei-credit-checker.hf.space/?next=other")
    assert not smoke._is_exact_public_page("https://user:secret@sapphirejimmy-utaipei-credit-checker.hf.space/")
    assert not smoke._is_exact_public_page("https://example.test/")


def test_http_router_allows_only_authorized_https_origin():
    allowed = _FakeRoute(f"{smoke.PUBLIC_URL}app/static/app.css")
    external = _FakeRoute("https://fonts.googleapis.com/example.css")
    insecure = _FakeRoute("http://sapphirejimmy-utaipei-credit-checker.hf.space/")

    smoke._route_http_request(allowed)
    smoke._route_http_request(external)
    smoke._route_http_request(insecure)

    assert (allowed.continued, allowed.aborted) == (1, 0)
    assert (external.continued, external.aborted) == (0, 1)
    assert (insecure.continued, insecure.aborted) == (0, 1)


def test_websocket_router_allows_only_authorized_wss_origin():
    allowed = _FakeWebSocket("wss://sapphirejimmy-utaipei-credit-checker.hf.space/_stcore/stream")
    external = _FakeWebSocket("wss://example.test/socket")
    insecure = _FakeWebSocket("ws://sapphirejimmy-utaipei-credit-checker.hf.space/socket")

    smoke._route_websocket(allowed)
    smoke._route_websocket(external)
    smoke._route_websocket(insecure)

    assert (allowed.connected, allowed.closed) == (1, 0)
    assert (external.connected, external.closed) == (0, 1)
    assert (insecure.connected, insecure.closed) == (0, 1)


def test_untrusted_marker_value_is_never_reported():
    secret_sentinel = "private-student-value"
    assert smoke._safe_marker_value(secret_sentinel, smoke._MARKER_STATES) == "INVALID_MARKER"
    assert secret_sentinel not in repr(smoke._initial_result())


class _FakeRoleLocator:
    def __init__(self, *elements):
        self._elements = elements

    def count(self):
        return len(self._elements)

    def nth(self, index):
        return self._elements[index]


class _FakeRoleElement:
    def __init__(self, *, visible, enabled):
        self.visible = visible
        self.enabled = enabled

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled


class _FakeConfirmationPage:
    def __init__(self, *buttons):
        self.buttons = _FakeRoleLocator(*buttons)

    def get_by_role(self, role, **_kwargs):
        return self.buttons if role == "button" else _FakeRoleLocator()


class _FakeAlertElement:
    def __init__(self, text, *, visible=True):
        self.text = text
        self.visible = visible

    def is_visible(self):
        return self.visible

    def inner_text(self):
        return self.text


class _FakeAlertPage:
    def __init__(self, *alerts):
        self.alerts = _FakeRoleLocator(*alerts)

    def locator(self, selector):
        assert selector == '[data-testid="stAlert"]'
        return self.alerts


def test_confirmation_readiness_ignores_hidden_duplicate_and_accepts_visible_enabled_button():
    page = _FakeConfirmationPage(
        _FakeRoleElement(visible=False, enabled=True),
        _FakeRoleElement(visible=True, enabled=True),
    )

    assert smoke._confirmation_gate_present(page)
    assert smoke._confirmation_is_ready(page)


def test_disabled_confirmation_cannot_certify_a_successful_transcript_parse():
    button = _FakeRoleElement(visible=True, enabled=False)
    page = _FakeConfirmationPage(button)
    assert smoke._has_confirmation_gate(page)
    assert smoke._confirmation_gate_present(page)
    assert not smoke._confirmation_is_ready(page)
    button.enabled = True
    assert smoke._confirmation_is_ready(page)


def test_missing_confirmation_gate_is_not_ready_or_present():
    page = _FakeConfirmationPage()

    assert not smoke._has_confirmation_gate(page)
    assert not smoke._confirmation_gate_present(page)
    assert not smoke._confirmation_is_ready(page)


def test_cohort_warning_year_requires_anchored_allowlisted_prefix():
    assert smoke._cohort_warning_year("成績資料辨識為 114 學年度，與目前選定手冊不同") == "114"
    assert smoke._cohort_warning_year("前置文字：成績資料辨識為 114 學年度") is None
    assert smoke._cohort_warning_year("成績資料辨識為 116 學年度，與目前選定手冊不同") is None


def test_observed_cohort_year_reads_only_one_visible_streamlit_alert():
    page = _FakeAlertPage(
        _FakeAlertElement("成績資料辨識為 114 學年度，與目前選定手冊不同"),
        _FakeAlertElement("成績資料辨識為 115 學年度，與目前選定手冊不同", visible=False),
    )

    assert smoke._observed_cohort_year(page) == "114"


def test_cohort_alignment_does_not_operate_mismatch_override(monkeypatch):
    selections = []
    applied = []

    monkeypatch.setattr(
        smoke,
        "_select_cohort_option",
        lambda _page, label, year: selections.append((label, year)) or True,
    )
    monkeypatch.setattr(smoke, "_apply_cohort_settings", lambda _page: applied.append(True) or True)
    monkeypatch.setattr(smoke, "_wait_until", lambda *_args, **_kwargs: True)

    class _NoOverridePage:
        def get_by_role(self, role, **_kwargs):
            if role == "checkbox":
                raise AssertionError("cohort mismatch override must not be inspected during alignment")
            raise AssertionError("unexpected role interaction")

    assert smoke._align_cohort_settings(_NoOverridePage(), "114")
    assert selections == [("入學年度", "114"), ("主修適用學生手冊", "114")]
    assert applied == [True]


class _IdleMarkerLocator:
    def evaluate_all(self, _script):
        return [{"state": "IDLE", "code": "IDLE"}]


class _CountLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class _CleanupPage:
    def __init__(self, *, residual_selector=None, residual_title=False):
        self.residual_selector = residual_selector
        self.residual_title = residual_title

    def locator(self, selector):
        if selector == "[data-utaipei-portal-state]":
            return _IdleMarkerLocator()
        return _CountLocator(int(selector == self.residual_selector))

    def get_by_role(self, *_args, **_kwargs):
        return _CountLocator(0)

    def get_by_text(self, *_args, **_kwargs):
        return _CountLocator(int(self.residual_title))


def test_cleanup_requires_idle_marker_and_no_preloaded_transcript_widgets():
    assert smoke._is_cleared_ui(_CleanupPage())
    for selector in (
        '[data-testid="stDataEditor"]',
        '[data-testid="stDataFrame"]',
        ".course-list",
        ".report-table-wrap",
    ):
        assert not smoke._is_cleared_ui(_CleanupPage(residual_selector=selector))
    assert not smoke._is_cleared_ui(_CleanupPage(residual_title=True))


def test_live_script_contains_one_submit_click_and_no_capture_artifacts():
    source = Path(smoke.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    submit_clicks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "submit"
    ]

    assert len(submit_clicks) == 1
    for forbidden in ("screenshot(", "tracing.start(", "record_har", "record_video"):
        assert forbidden not in source
