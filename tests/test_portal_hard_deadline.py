"""Focused contract tests for the supervised realtime portal boundary."""

from __future__ import annotations

import multiprocessing
import time

import pytest
import requests

import scraper


def _permanently_blocking_worker(connection, _operation_timeout, _correlation_id):
    """A spawn-safe worker double that never produces a result."""

    try:
        connection.recv()
        while True:
            time.sleep(1)
    finally:
        connection.close()


def _raising_worker(connection, _operation_timeout, _correlation_id):
    connection.recv()
    raise RuntimeError("private test exception must not cross the seam")


def _success_worker(connection, _operation_timeout, _correlation_id):
    try:
        payload = connection.recv()
        assert payload[0] == "credentials"
        connection.send(("success", b"%PDF-child"))
    finally:
        connection.close()


def _near_limit_success_worker(connection, _operation_timeout, _correlation_id):
    try:
        connection.recv()
        payload = b"%PDF-" + (b"x" * (scraper.MAX_PDF_BYTES - 5 - 1024))
        connection.send(("success", payload))
    finally:
        connection.close()


class _StreamingResponse:
    def __init__(self, chunks):
        self.headers = {"Content-Type": "application/pdf"}
        self._chunks = chunks
        self.closed = False

    def iter_content(self, **_kwargs):
        yield from self._chunks

    def close(self):
        self.closed = True


class _DeferredTextFailureResponse:
    def __init__(self, error):
        self.status_code = 200
        self.headers = {"Content-Type": "text/html"}
        self.url = scraper.BASE_URL + "ag_pro/ag102.jsp"
        self.history = []
        self.closed = False
        self._error = error

    @property
    def text(self):
        raise self._error

    def close(self):
        self.closed = True


class _CandidateResponse:
    def __init__(self, text):
        self.status_code = 200
        self.text = text
        self.headers = {"Content-Type": "text/html"}
        self.url = scraper.BASE_URL + "ag_pro/ag102.jsp"
        self.history = []
        self.closed = False

    def close(self):
        self.closed = True


class _CandidateSession:
    def __init__(self):
        self.calls = 0
        self.closed = False

    def get(self, _url, **_kwargs):
        self.calls += 1
        return _CandidateResponse("<html><body>沒有可下載檔案</body></html>")

    def close(self):
        self.closed = True


def test_iter_content_timeout_is_stable_and_response_is_closed():
    def timeout_chunks():
        yield b"%PDF-1.7"
        raise requests.exceptions.ReadTimeout()

    response = _StreamingResponse(timeout_chunks())
    with pytest.raises(scraper.PortalError) as raised:
        scraper._read_pdf_response(response)
    assert raised.value.code is scraper.PortalErrorCode.UPSTREAM_TIMEOUT
    assert response.closed is True


def test_slow_drip_hits_shared_deadline_and_closes_response():
    response = _StreamingResponse((b"%PDF-1.7",))

    def slow_chunks():
        yield b"%PDF-1.7"
        time.sleep(0.04)
        yield b"late"

    response._chunks = slow_chunks()
    with pytest.raises(scraper.PortalError) as raised:
        scraper._read_pdf_response(response, deadline=scraper._OperationDeadline(0.01))
    assert raised.value.code is scraper.PortalErrorCode.UPSTREAM_TIMEOUT
    assert response.closed is True


def test_request_read_timeout_is_capped_at_ten_seconds():
    connect_timeout, read_timeout = scraper._OperationDeadline(60).request_timeout(25)
    assert connect_timeout <= 5
    assert read_timeout <= 10


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (requests.exceptions.ReadTimeout(), scraper.PortalErrorCode.UPSTREAM_TIMEOUT),
        (requests.exceptions.ConnectionError(), scraper.PortalErrorCode.NETWORK_BLOCKED),
    ],
)
def test_deferred_html_body_errors_keep_transport_semantics_and_close_response(error, expected):
    response = _DeferredTextFailureResponse(error)
    client = scraper.PortalClient("account", "password", deadline=scraper._OperationDeadline(2))
    try:
        with pytest.raises(scraper.PortalError) as raised:
            client._extract_pdf(response)
    finally:
        client.close()
    assert raised.value.code is expected
    assert response.closed is True


def test_pdf_candidates_are_deduplicated_and_capped_at_three_attempts():
    session = _CandidateSession()
    client = scraper.PortalClient(
        "account",
        "password",
        session=session,
        deadline=scraper._OperationDeadline(2),
    )
    client._logged_in = True
    wrapper = _CandidateResponse(
        "<a href='/one.pdf'>下載</a>"
        "<a href='/one.pdf'>重複</a>"
        "<a href='/two.pdf'>下載</a>"
        "<a href='/three.pdf'>下載</a>"
        "<a href='/four.pdf'>下載</a>"
    )
    with pytest.raises(scraper.PortalError) as raised:
        client._extract_pdf(wrapper)
    assert raised.value.code is scraper.PortalErrorCode.PDF_NOT_FOUND
    assert session.calls == scraper.MAX_PDF_CANDIDATES
    assert wrapper.closed is True
    client.close()


def test_child_exception_crosses_only_as_stable_code():
    with pytest.raises(scraper.PortalError) as raised:
        scraper.fetch_transcript(
            "test-account",
            "test-secret",
            operation_timeout=1.5,
            hard_timeout=3.0,
            worker_target=_raising_worker,
        )
    assert raised.value.code is scraper.PortalErrorCode.PORTAL_CHANGED
    assert "private test exception" not in str(raised.value)


def test_successful_child_returns_only_validated_pdf_bytes():
    assert (
        scraper.fetch_transcript(
            "test-account",
            "test-secret",
            operation_timeout=1.5,
            hard_timeout=3.0,
            worker_target=_success_worker,
        )
        == b"%PDF-child"
    )


def test_near_limit_pdf_crosses_spawn_pipe_without_deadlock_or_live_child():
    before_pids = {process.pid for process in multiprocessing.active_children() if process.pid}
    result = scraper.fetch_transcript(
        "test-account",
        "test-secret",
        operation_timeout=5.0,
        hard_timeout=8.0,
        worker_target=_near_limit_success_worker,
    )
    after_pids = {process.pid for process in multiprocessing.active_children() if process.pid}
    assert len(result) == scraper.MAX_PDF_BYTES - 1024
    assert result.startswith(b"%PDF-")
    assert (after_pids - before_pids) == set()


def test_wrapped_requests_session_cannot_disable_public_supervisor(monkeypatch):
    observed = {}

    class WrappedSession:
        pass

    def supervised(uid, pwd, *, operation_timeout, hard_timeout, worker_target=None):
        observed.update(
            uid=uid,
            pwd=pwd,
            operation_timeout=operation_timeout,
            hard_timeout=hard_timeout,
            worker_target=worker_target,
        )
        return b"%PDF-supervised"

    monkeypatch.setattr(scraper.requests, "Session", WrappedSession)
    monkeypatch.setattr(scraper, "_supervised_fetch_transcript", supervised)

    result = scraper.fetch_transcript("account", "secret")

    assert result == b"%PDF-supervised"
    assert observed["uid"] == "account"
    assert observed["pwd"] == "secret"


class _Feedback:
    def __init__(self):
        self.messages = []

    def error(self, value, **_kwargs):
        self.messages.append(str(value))

    def warning(self, value, **_kwargs):
        self.messages.append(str(value))

    def success(self, value, **_kwargs):
        self.messages.append(str(value))

    def markdown(self, value, **_kwargs):
        self.messages.append(str(value))


def test_blocking_worker_hits_hard_deadline_and_preserves_prior_state():
    """A stuck worker must become a stable timeout without changing old data."""

    # Windows spawn imports this module in every worker. Keep the UI import
    # local so transport-only test doubles do not load Streamlit at startup.
    import sidebar

    state = {
        "transcript_pdf_bytes": b"%PDF-old",
        "transcript_pdf_path": None,
        "source_label": "已確認資料",
        "masked_student_id": "••••1234",
        "decision_snapshot": {"sentinel": "unchanged"},
    }
    feedback = _Feedback()
    before_pids = {process.pid for process in multiprocessing.active_children() if process.pid}
    started = time.monotonic()

    class _Streamlit:
        session_state = state

    original_streamlit = sidebar.st
    sidebar.st = _Streamlit()
    try:
        sidebar._attempt_live_scrape(
            "test-account",
            "test-secret",
            ui=feedback,
            operation_timeout=0.2,
            hard_timeout=0.35,
            worker_target=_permanently_blocking_worker,
        )
    finally:
        sidebar.st = original_streamlit

    elapsed = time.monotonic() - started
    after_pids = {process.pid for process in multiprocessing.active_children() if process.pid}
    assert elapsed < 0.5
    assert (after_pids - before_pids) == set()
    assert state["transcript_pdf_bytes"] == b"%PDF-old"
    assert state["decision_snapshot"] == {"sentinel": "unchanged"}
    assert state["_utaipei_portal_state"] == "ERROR"
    assert state["_utaipei_portal_code"] == scraper.PortalErrorCode.UPSTREAM_TIMEOUT.value
    joined = "\n".join(feedback.messages)
    assert scraper.PortalErrorCode.UPSTREAM_TIMEOUT.value in joined
    assert "test-secret" not in joined
