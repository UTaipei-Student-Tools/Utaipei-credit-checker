import tempfile
import unittest
from unittest.mock import patch

import scraper
import sidebar


class _Response:
    def __init__(self, text="", content=b"", content_type="text/html"):
        self.status_code = 200
        self.text = text
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.url = scraper.BASE_URL + "ag_pro/ag102.jsp"
        self.encoding = "utf-8"


class _Session:
    def __init__(self, fail_post=False):
        self.closed = False
        self.fail_post = fail_post
        self.posts = 0

    def get(self, *args, **kwargs):
        return _Response("<html><body>校務系統入口</body></html>")

    def post(self, *args, **kwargs):
        if self.fail_post:
            raise RuntimeError("portal sentinel")
        self.posts += 1
        if self.posts == 1:
            return _Response('<form id="thisform"><input name="token" value="x"></form>')
        if self.posts == 2:
            return _Response("<html><body>校務系統主選單</body></html>")
        if self.posts == 3:
            return _Response('<form id="thisform" action="/utaipei/ag_pro/ag102.jsp"><input name="download" value="y"></form>')
        return _Response(content=b"%PDF-test", content_type="application/pdf")

    def close(self):
        self.closed = True


class ScraperLifecycleTests(unittest.TestCase):
    def test_login_form_purges_raw_account_keys_after_success_and_failure(self):
        class Form:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeUi:
            def __init__(self, submit):
                self.session_state = {
                    "student_id": "old-account",
                    "portal_account_input": "old-account",
                    "portal_password_input": "old-password",
                }
                self.submit = submit

            def markdown(self, *_args, **_kwargs):
                return None

            def caption(self, *_args, **_kwargs):
                return None

            def form(self, *_args, **_kwargs):
                return Form()

            def text_input(self, _label, **kwargs):
                # A keyed widget would reintroduce the defect under test.
                if kwargs.get("key"):
                    self.session_state[kwargs["key"]] = "raw-account"
                return "account" if "Password" not in _label else "password"

            def columns(self, count):
                return [self for _ in range(count)]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def selectbox(self, *_args, **_kwargs):
                return "115" if "學年度" in str(_args[0]) else "1"

            def form_submit_button(self, *_args, **_kwargs):
                result = self.submit
                self.submit = False
                return result

            def success(self, *_args, **_kwargs):
                return None

            def warning(self, *_args, **_kwargs):
                return None

            def error(self, *_args, **_kwargs):
                return None

            def info(self, *_args, **_kwargs):
                return None

        for submit in (True, False):
            fake = FakeUi(submit)
            with patch.object(sidebar, "st", fake), patch.object(sidebar, "_attempt_live_scrape"):
                sidebar._init_session_state()
                sidebar._render_login_section(fake)
            self.assertNotIn("student_id", fake.session_state)
            self.assertNotIn("student_pwd", fake.session_state)
            self.assertNotIn("portal_password_input", fake.session_state)
            self.assertNotIn("portal_account_input", fake.session_state)

    def test_setup_state_and_live_scrape_never_store_password(self):
        state = {
            "handbook_year": "114",
            "admission_cohort": "114",
            "transcript_pdf_path": None,
            "transcript_pdf_bytes": None,
            "source_label": "尚未載入",
        }
        fake_streamlit = type("FakeStreamlit", (), {"session_state": state})()
        feedback = type(
            "Feedback",
            (),
            {
                "success": lambda self, *_args, **_kwargs: None,
                "warning": lambda self, *_args, **_kwargs: None,
                "error": lambda self, *_args, **_kwargs: None,
            },
        )()
        with patch.object(sidebar, "st", fake_streamlit), patch.object(
            sidebar, "fetch_transcript", return_value=b"%PDF-test"
        ) as fetch_mock, patch.object(sidebar, "_validate_live_transcript"):
            sidebar._attempt_live_scrape("u", "secret", ui=feedback)
        fetch_mock.assert_called_once_with("u", "secret")
        self.assertNotIn("student_pwd", state)
        self.assertNotIn("portal_password_input", state)

    def test_clear_loaded_data_resets_persisted_portal_state(self):
        state = {
            "_utaipei_portal_state": "SUCCESS",
            "_utaipei_portal_code": "SUCCESS",
            "transcript_pdf_path": None,
            "transcript_pdf_bytes": b"%PDF-old",
            "source_label": "校務系統即時抓取",
            "masked_student_id": "••••1234",
        }
        fake_streamlit = type("FakeStreamlit", (), {"session_state": state})()

        with patch.object(sidebar, "st", fake_streamlit):
            sidebar._clear_loaded_data()

        self.assertEqual(state["_utaipei_portal_state"], "IDLE")
        self.assertEqual(state["_utaipei_portal_code"], "IDLE")

    def test_early_failure_keeps_original_error_and_does_not_hit_unbound_path(self):
        session = _Session(fail_post=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(scraper.PortalError) as raised:
                scraper._fetch_transcript_inline("u", "p", session=session)
            self.assertEqual(raised.exception.code, scraper.PortalErrorCode.NETWORK_BLOCKED)
            self.assertTrue(session.closed)
            self.assertEqual([], list(__import__("pathlib").Path(temp_dir).glob("utaipei-transcript-*.pdf")))

    def test_success_returns_memory_and_removes_crawler_file(self):
        session = _Session()
        with tempfile.TemporaryDirectory() as temp_dir:
            content = scraper._fetch_transcript_inline("u", "p", session=session)
            self.assertEqual(content, b"%PDF-test")
            self.assertTrue(session.closed)
            self.assertEqual([], list(__import__("pathlib").Path(temp_dir).glob("utaipei-transcript-*.pdf")))


if __name__ == "__main__":
    unittest.main()
