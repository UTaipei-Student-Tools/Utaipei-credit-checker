"""Portal transcript identity and parser-completeness acceptance cases."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import scraper
import sidebar
from tests.synthetic_transcript_fixture import build_synthetic_transcript_pdf
from tests.test_transcript_reconciliation import transcript_with_summary


def test_real_pdf_parser_enforces_document_identity_before_commit():
    pdf = transcript_with_summary()
    sidebar._validate_live_transcript(pdf, "Z999999999")
    with pytest.raises(scraper.PortalError) as caught:
        sidebar._validate_live_transcript(pdf, "Z999999998")
    assert caught.value.code == scraper.PortalErrorCode.TRANSCRIPT_IDENTITY_MISMATCH
    with pytest.raises(scraper.PortalError) as incomplete:
        sidebar._validate_live_transcript(build_synthetic_transcript_pdf(), "Z999999999")
    assert incomplete.value.code == scraper.PortalErrorCode.TRANSCRIPT_VALIDATION_FAILED


class _Feedback:
    def __init__(self):
        self.messages = []

    def error(self, value, **_kwargs):
        self.messages.append(str(value))

    def warning(self, value, **_kwargs):
        self.messages.append(str(value))

    def success(self, value, **_kwargs):
        self.messages.append(str(value))

    def info(self, value, **_kwargs):
        self.messages.append(str(value))


def _state():
    return {
        "transcript_pdf_bytes": b"%PDF-old",
        "transcript_pdf_path": None,
        "source_label": "已確認資料",
        "masked_student_id": "••••1234",
        "student_pwd": "old-password",
        "portal_account_input": "old-account",
        "_utaipei_portal_state": "SUCCESS",
        "_utaipei_portal_code": "SUCCESS",
    }


def _student(*, student_id="u", complete=True, fatal=False, status="reconciled"):
    return {
        "student_id": student_id,
        "parse_diagnostics": {
            "complete": complete,
            "fatal": fatal,
            "reconciliation": {"status": status},
        },
    }


def _run(monkeypatch, parsed, *, account="u"):
    state = _state()
    feedback = _Feedback()
    fake_streamlit = SimpleNamespace(session_state=state)
    monkeypatch.setattr(sidebar, "st", fake_streamlit)
    monkeypatch.setattr(sidebar, "fetch_transcript", lambda *_args, **_kwargs: b"%PDF-new")
    if isinstance(parsed, BaseException):
        def parse(_pdf):
            raise parsed
    else:
        def parse(_pdf):
            return parsed, [{"course_name": "課程"}]
    monkeypatch.setattr(sidebar, "parse_transcript_pdf", parse)
    sidebar._attempt_live_scrape(account, "secret", ui=feedback)
    return state, feedback


def test_live_scrape_commits_only_exact_normalized_identity_with_complete_reconciliation(monkeypatch):
    state, feedback = _run(monkeypatch, _student(student_id=" U "))

    assert state["transcript_pdf_bytes"] == b"%PDF-new"
    assert state["source_label"] == "校務系統即時抓取"
    assert state["_utaipei_portal_state"] == "SUCCESS"
    assert state["_utaipei_portal_code"] == "SUCCESS"
    assert any("已即時抓取" in message for message in feedback.messages)
    assert "secret" not in "\n".join(feedback.messages)
    assert "old-password" not in state.values()
    assert "student_pwd" not in state
    assert "portal_account_input" not in state


@pytest.mark.parametrize(
    ("parsed", "account", "expected_code"),
    [
        (_student(student_id="other"), "u", scraper.PortalErrorCode.TRANSCRIPT_IDENTITY_MISMATCH),
        (_student(student_id=""), "u", scraper.PortalErrorCode.TRANSCRIPT_IDENTITY_MISMATCH),
        (_student(complete=False), "u", scraper.PortalErrorCode.TRANSCRIPT_VALIDATION_FAILED),
        (_student(fatal=True), "u", scraper.PortalErrorCode.TRANSCRIPT_VALIDATION_FAILED),
        (_student(status="not_available"), "u", scraper.PortalErrorCode.TRANSCRIPT_VALIDATION_FAILED),
        (ValueError("private PDF and account details"), "u", scraper.PortalErrorCode.TRANSCRIPT_VALIDATION_FAILED),
    ],
)
def test_invalid_live_transcript_preserves_previous_data_and_clears_credential_state(
    monkeypatch, parsed, account, expected_code
):
    state, feedback = _run(monkeypatch, parsed, account=account)

    assert state["transcript_pdf_bytes"] == b"%PDF-old"
    assert state["source_label"] == "已確認資料"
    assert state["masked_student_id"] == "••••1234"
    assert state["_utaipei_portal_state"] == "ERROR"
    assert state["_utaipei_portal_code"] == expected_code.value
    assert "student_pwd" not in state
    assert "portal_account_input" not in state
    joined = "\n".join(feedback.messages)
    assert "未套用" in joined
    assert "private PDF" not in joined
    assert "secret" not in joined


def test_upload_path_does_not_require_live_portal_identity_validator(monkeypatch):
    state = {
        "transcript_pdf_bytes": b"%PDF-old",
        "transcript_pdf_path": None,
        "source_label": "已確認資料",
        "upload_key_version": 0,
    }
    feedback = _Feedback()
    uploaded = SimpleNamespace(getvalue=lambda: b"%PDF-upload")

    class _Ui:
        def markdown(self, *_args, **_kwargs):
            return None

        def file_uploader(self, *_args, **_kwargs):
            return uploaded

        def button(self, *_args, **_kwargs):
            return False

        def error(self, value, **_kwargs):
            feedback.error(value)

        def success(self, value, **_kwargs):
            feedback.success(value)

    fake_streamlit = SimpleNamespace(session_state=state)
    monkeypatch.setattr(sidebar, "st", fake_streamlit)
    parse_called = False

    def parse(_pdf):
        nonlocal parse_called
        parse_called = True
        return _student(), []

    monkeypatch.setattr(sidebar, "parse_transcript_pdf", parse)
    sidebar._render_upload_section(_Ui())

    assert state["transcript_pdf_bytes"] == b"%PDF-upload"
    assert state["source_label"] == "自行上傳 PDF"
    assert state[sidebar.TRANSCRIPT_SCOPE_KEY]["source"] == "upload"
    assert parse_called is False
