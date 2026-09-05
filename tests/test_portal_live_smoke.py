from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.portal_live_smoke as live_smoke
from scripts.portal_live_diagnostic import _describe
from scripts.portal_live_smoke import CredentialFileError, load_portal_credentials
from tests.synthetic_transcript_fixture import build_synthetic_transcript_pdf
from tests.test_transcript_reconciliation import transcript_with_summary


def test_credential_loader_accepts_only_labeled_portal_values(tmp_path: Path):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：student-placeholder\n"
        "校務密碼：password-placeholder\n"
        "HF Account：must-not-be-selected\n"
        "HF Password：must-not-be-selected\n"
        "HF Token：must-not-be-selected\n",
        encoding="utf-8",
    )

    account, password = load_portal_credentials(source)

    assert account == "student-placeholder"
    assert password == "password-placeholder"


@pytest.mark.parametrize(
    "content",
    (
        "校務帳號：student-placeholder\n校務密碼：password-placeholder\n",
        "網站：https://evil.example/login\n校務帳號：student-placeholder\n校務密碼：password-placeholder\n",
        "校務系統：https://my.utaipei.edu.tw/\nHF Token：token-placeholder\n",
    ),
)
def test_credential_loader_fails_closed_for_incomplete_or_nonofficial_scope(tmp_path: Path, content: str):
    source = tmp_path / "credentials.txt"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(CredentialFileError):
        load_portal_credentials(source)


def test_live_smoke_reports_verified_transcript_as_pass_without_schedule_fetch(tmp_path: Path, monkeypatch):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：private-account\n"
        "校務密碼：private-password\n",
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, account, password):
            assert account == "private-account"
            assert password == "private-password"

        def login(self):
            return None

        def fetch_transcript_pdf(self):
            return transcript_with_summary()

        def close(self):
            return None

    monkeypatch.setattr(live_smoke, "PortalClient", FakeClient)

    result = live_smoke.run_smoke(source)

    assert result["overall_status"] == "PASS"
    assert result["transcript_ok"] is True
    assert "schedule_ok" not in result
    assert "schedule_error_code" not in result
    assert "private-account" not in repr(result)
    assert "private-password" not in repr(result)


def test_live_smoke_pass_requires_parser_and_confirmation_gates(tmp_path: Path, monkeypatch):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：private-account\n"
        "校務密碼：private-password\n",
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, _account, _password):
            pass

        def login(self):
            return None

        def fetch_transcript_pdf(self):
            return transcript_with_summary()

        def close(self):
            return None

    monkeypatch.setattr(live_smoke, "PortalClient", FakeClient)

    result = live_smoke.run_smoke(source)

    assert result["ok"] is True
    assert result["overall_status"] == "PASS"
    assert result["transcript_ok"] is True
    assert result["pdf_parse_ok"] is True
    assert result["course_rows_present"] is True
    assert result["confirmation_state"] == "PARSED"
    assert result["formal_rows_released"] is False
    assert set(result) <= {
        "ok",
        "overall_status",
        "transcript_ok",
        "login_ms",
        "fetch_ms",
        "total_ms",
        "pdf_nonempty",
        "pdf_parse_ok",
        "course_rows_present",
        "parser_complete",
        "parser_fatal",
        "reconciliation_available",
        "reconciliation_status",
        "total_reconciled",
        "confirmation_state",
        "formal_rows_released",
    }


def test_live_smoke_maps_parser_failure_to_closed_error_without_exception_text(tmp_path: Path, monkeypatch):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：private-account\n"
        "校務密碼：private-password\n",
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, _account, _password):
            pass

        def login(self):
            return None

        def fetch_transcript_pdf(self):
            return b"%PDF-1.7 but-not-a-real-transcript"

        def close(self):
            return None

    monkeypatch.setattr(live_smoke, "PortalClient", FakeClient)

    result = live_smoke.run_smoke(source)

    assert result["ok"] is False
    assert result["overall_status"] == "FAILED"
    assert result["error_code"] == "TRANSCRIPT_PARSE_FAILED"
    assert result["pdf_parse_ok"] is False
    assert result["course_rows_present"] is False
    assert result["formal_rows_released"] is False
    assert "but-not-a-real-transcript" not in repr(result)
    assert "ValueError" not in repr(result)


def test_live_smoke_rejects_unconfirmed_rows_and_releases_nothing(tmp_path: Path, monkeypatch):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：private-account\n"
        "校務密碼：private-password\n",
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, _account, _password):
            pass

        def login(self):
            return None

        def fetch_transcript_pdf(self):
            return b"%PDF-1.7 parser-seam-fixture"

        def close(self):
            return None

    monkeypatch.setattr(live_smoke, "PortalClient", FakeClient)
    monkeypatch.setattr(
        live_smoke,
        "parse_transcript_pdf",
        lambda _pdf: (
            {
                "student_id": "PRIVATE-STUDENT-ID",
                "parse_diagnostics": {
                    "complete": True,
                    "fatal": False,
                    "reconciliation": {
                        "available": True,
                        "status": "reconciled",
                    },
                    "total_reconciled": True,
                },
            },
            [{"course_name": "課程", "credits": 3, "status": "未辨識", "academic_year": "114", "semester": "1"}],
        ),
    )

    result = live_smoke.run_smoke(source)

    assert result["ok"] is False
    assert result["overall_status"] == "FAILED"
    assert result["error_code"] == "TRANSCRIPT_CONFIRMATION_UNSAFE"
    assert result["pdf_parse_ok"] is True
    assert result["parser_complete"] is True
    assert result["parser_fatal"] is False
    assert result["reconciliation_available"] is True
    assert result["total_reconciled"] is True
    assert result["course_rows_present"] is True
    assert result["confirmation_state"] == "UNCONFIRMED"
    assert result["formal_rows_released"] is False
    assert "PRIVATE-STUDENT-ID" not in repr(result)


def test_live_smoke_never_emits_parser_values_or_fingerprint(tmp_path: Path, monkeypatch):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：private-account\n"
        "校務密碼：private-password\n",
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, _account, _password):
            pass

        def login(self):
            return None

        def fetch_transcript_pdf(self):
            return build_synthetic_transcript_pdf()

        def close(self):
            return None

    def parse_with_private_values(_pdf):
        raise RuntimeError("PRIVATE-EXCEPTION student-id course-name fingerprint")

    monkeypatch.setattr(live_smoke, "PortalClient", FakeClient)
    monkeypatch.setattr(live_smoke, "parse_transcript_pdf", parse_with_private_values)

    result = live_smoke.run_smoke(source)

    assert result["error_code"] == "TRANSCRIPT_PARSE_FAILED"
    rendered = repr(result)
    assert "PRIVATE-EXCEPTION" not in rendered
    assert "student-id" not in rendered
    assert "course-name" not in rendered
    assert "fingerprint" not in rendered


def test_live_smoke_keeps_missing_reconciliation_distinct_from_parser_fatal(tmp_path: Path, monkeypatch):
    source = tmp_path / "credentials.txt"
    source.write_text(
        "校務系統：https://my.utaipei.edu.tw/utaipei/index_main.html\n"
        "校務帳號：private-account\n"
        "校務密碼：private-password\n",
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, _account, _password):
            pass

        def login(self):
            return None

        def fetch_transcript_pdf(self):
            return build_synthetic_transcript_pdf()

        def close(self):
            return None

    monkeypatch.setattr(live_smoke, "PortalClient", FakeClient)

    result = live_smoke.run_smoke(source)

    assert result["ok"] is False
    assert result["overall_status"] == "FAILED"
    assert result["error_code"] == "TRANSCRIPT_RECONCILIATION_UNAVAILABLE"
    assert result["pdf_parse_ok"] is True
    assert result["parser_complete"] is True
    assert result["parser_fatal"] is False
    assert result["reconciliation_available"] is False
    assert result["reconciliation_status"] == "not_available"
    assert result["total_reconciled"] is False


def test_live_diagnostic_description_never_emits_control_or_script_values():
    html = """
    <html><body>
      <form id="student-123456789" action="student/123456789/result.jsp?token=private-token">
        <input type="hidden" name="uid" value="private-student-id">
        <input type="hidden" name="pwd" value="private-password?with=query">
        <input type="hidden" name="studentNumber123456789" value="private-value">
      </form>
      <script>
        function switch_yms() {
          var unrelated = "private-script-value?with=query";
          thisform.spath.value = "ag_pro/ag104.jsp?";
          window.location.href = "fnc.jsp?token=private-token";
          window.close();
        }
      </script>
    </body></html>
    """

    response = SimpleNamespace(
        status_code=200,
        url="https://my.utaipei.edu.tw/utaipei/student/123456789/result.jsp?token=private-token",
        headers={"Content-Type": "text/html; charset=UTF-8"},
        text=html,
        content=html.encode("utf-8"),
        encoding="UTF-8",
        apparent_encoding="utf-8",
    )

    output = repr(_describe(response))

    assert "private-student-id" not in output
    assert "private-password" not in output
    assert "private-script-value" not in output
    assert "123456789" not in output
    assert "private-token" not in output
    assert "studentNumber" not in output
    assert _describe(response)["script_behavior"] == {
        "async_request_present": False,
        "document_write_present": False,
        "form_submit_present": False,
        "location_navigation_present": True,
        "opener_access_present": False,
        "popup_open_present": False,
        "post_message_present": False,
        "window_close_present": True,
    }
