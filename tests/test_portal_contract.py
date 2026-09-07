import unittest
from unittest.mock import patch

import scraper
import sidebar


class FakeResponse:
    def __init__(
        self,
        *,
        text="",
        content=b"",
        url=None,
        content_type="text/html",
        status_code=200,
        headers=None,
        history=None,
    ):
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.url = url or scraper.BASE_URL
        self.history = list(history or ())
        self.encoding = "utf-8"
        self.close_count = 0

    def close(self):
        self.close_count += 1


LOGIN_FORM = """
<form id="thisform" action="/utaipei/perchk.jsp" method="post">
  <input type="hidden" name="ticket" value="ticket-1">
</form>
"""
PERCHK_PAGE = "<html><title>學生入口</title><body>校務系統主選單</body></html>"
AG102_FORM = """
<form id="thisform" action="/utaipei/ag_pro/ag102.jsp" method="post">
  <input type="hidden" name="token" value="transcript-1">
</form>
"""
LOGIN_PAGE = """
<html><body><form id="login" action="/utaipei/login_check.jsp">
<input name="uid"><input name="pwd" type="password"></form>登入校務系統</body></html>
"""
AUTHENTICATED_ACCOUNT_SETTINGS_PAGE = """
<html><body><h1>帳號設定</h1><p>Last login: 2026-09-03</p>
<form action="/utaipei/account/save" method="post">
  <input type="hidden" name="uid" value="student">
  <button name="save" value="1">儲存</button>
</form></body></html>
"""
AUTHENTICATED_AG102_PAGE = """
<html><body><h1>歷年成績單下載</h1>
<form id="thisform1" action="../perchk.jsp" method="post">
  <input type="hidden" name="flag" value="1">
  <input type="hidden" name="hid_type" value="S">
  <input type="hidden" name="uid" value="student">
  <input type="hidden" name="pwd" value="session-proof">
</form>
<a href="/utaipei/servlet/transcript?id=1">下載成績單</a>
</body></html>
"""


class PortalSession:
    def __init__(self, *, pdf=b"%PDF-1.7 fake"):
        self.pdf = pdf
        self.closed = False
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(text="<html><body>入口</body></html>", url=url)

    def post(self, url, data=None, **kwargs):
        self.calls.append(("POST", url, data or {}, kwargs))
        if url.endswith("login_check.jsp"):
            return FakeResponse(text=LOGIN_FORM, url=url)
        if url.endswith("perchk.jsp"):
            return FakeResponse(text=PERCHK_PAGE, url=url)
        if url.endswith("fnc.jsp"):
            fncid = (data or {}).get("fncid")
            return FakeResponse(text=AG102_FORM if fncid == "AG102" else "", url=url)
        if "ag102.jsp" in url:
            return FakeResponse(content=self.pdf, url=url, content_type="application/octet-stream")
        return FakeResponse(text="", url=url, status_code=404)

    def close(self):
        self.closed = True


class StreamResponse:
    """Response double that fails if production reads ``.content`` eagerly."""

    def __init__(self, chunks, *, url, content_type="application/octet-stream", content_length=None):
        self.status_code = 200
        self.text = ""
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.url = url
        self.history = []
        self._chunks = chunks
        self.iter_calls = 0
        self.tail_read = False
        self.closed = False

    @property
    def content(self):
        raise AssertionError("streaming response content must not be read eagerly")

    def iter_content(self, **_kwargs):
        self.iter_calls += 1
        yield from self._chunks(self)

    def close(self):
        self.closed = True


class StreamingPortalSession(PortalSession):
    def __init__(self, *, direct_chunks=None, linked=False, content_length=None):
        super().__init__()
        self.direct_chunks = direct_chunks
        self.linked = linked
        self.content_length = content_length
        self.stream_response = None

    def post(self, url, data=None, **kwargs):
        if self.linked and "ag102.jsp" in url:
            self.calls.append(("POST", url, data or {}, kwargs))
            return FakeResponse(
                text='<html><body><a href="/servlet/transcript?id=1">下載成績單</a></body></html>',
                url=url,
            )
        if self.direct_chunks is not None and "ag102.jsp" in url:
            self.calls.append(("POST", url, data or {}, kwargs))
            self.stream_response = StreamResponse(
                self.direct_chunks,
                url=url,
                content_length=self.content_length,
            )
            return self.stream_response
        return super().post(url, data=data, **kwargs)

    def get(self, url, **kwargs):
        if self.linked and "servlet/transcript" in url:
            self.calls.append(("GET", url, kwargs))
            self.stream_response = StreamResponse(
                self.direct_chunks,
                url=url,
                content_length=self.content_length,
            )
            return self.stream_response
        return super().get(url, **kwargs)


class AuthenticatedTranscriptSession(PortalSession):
    def __init__(self):
        super().__init__()
        self.wrapper_response = None
        self.link_response = None

    def post(self, url, data=None, **kwargs):
        if "ag102.jsp" in url:
            self.calls.append(("POST", url, data or {}, kwargs))
            self.wrapper_response = FakeResponse(text=AUTHENTICATED_AG102_PAGE, url=url)
            return self.wrapper_response
        return super().post(url, data=data, **kwargs)

    def get(self, url, **kwargs):
        if "servlet/transcript" in url:
            self.calls.append(("GET", url, kwargs))
            self.link_response = FakeResponse(content=b"%PDF-1.7 authenticated", url=url, content_type="application/pdf")
            return self.link_response
        return super().get(url, **kwargs)


class NoCandidateTranscriptSession(PortalSession):
    def __init__(self):
        super().__init__()
        self.wrapper_response = None

    def post(self, url, data=None, **kwargs):
        if "ag102.jsp" in url:
            self.calls.append(("POST", url, data or {}, kwargs))
            self.wrapper_response = FakeResponse(
                text="<html><body><h1>歷年成績單下載</h1><p>目前沒有可下載檔案</p></body></html>",
                url=url,
            )
            return self.wrapper_response
        return super().post(url, data=data, **kwargs)


class LinkedHtmlErrorTranscriptSession(AuthenticatedTranscriptSession):
    def get(self, url, **kwargs):
        if "servlet/transcript" in url:
            self.calls.append(("GET", url, kwargs))
            self.link_response = FakeResponse(
                text="<html><body><h1>下載失敗</h1><p>暫無檔案</p></body></html>",
                url=url,
            )
            return self.link_response
        return super().get(url, **kwargs)


class RedirectSession(PortalSession):
    def __init__(self, location, *, status_code=302):
        super().__init__()
        self.location = location
        self.status_code = status_code
        self.evil_calls = 0

    def post(self, url, data=None, **kwargs):
        self.calls.append(("POST", url, data or {}, kwargs))
        if url.endswith("login_check.jsp"):
            return FakeResponse(status_code=self.status_code, url=url, headers={"Location": self.location})
        return super().post(url, data=data, **kwargs)

    def get(self, url, **kwargs):
        if "evil.example" in url:
            self.evil_calls += 1
        if url == scraper.PERCHK_URL:
            return FakeResponse(text=LOGIN_FORM, url=url)
        return super().get(url, **kwargs)


class StrictRefererSession(PortalSession):
    """Require each POST to use the URL of the immediately preceding page."""

    def __init__(self):
        super().__init__()
        self.previous_url = scraper.BASE_URL + "index_main.html"
        self.violations = []

    def _check(self, url, kwargs):
        referer = (kwargs.get("headers") or {}).get("Referer")
        if referer != self.previous_url:
            self.violations.append((url, referer, self.previous_url))
        self.previous_url = url

    def post(self, url, data=None, **kwargs):
        self._check(url, kwargs)
        if url.endswith("login_check.jsp"):
            result = FakeResponse(text=LOGIN_FORM.replace(
                'action="/utaipei/perchk.jsp"', 'action="/utaipei/dynamic/perchk.jsp"'
            ), url=url + "?step=done")
        elif url.endswith("dynamic/perchk.jsp"):
            result = FakeResponse(text=PERCHK_PAGE, url=url + "?step=session")
        elif url.endswith("fnc.jsp"):
            result = FakeResponse(text=AG102_FORM, url=url + "?step=fnc")
        elif "ag102.jsp" in url:
            result = FakeResponse(content=b"%PDF-1.7 strict", url=url, content_type="application/pdf")
        else:
            result = super().post(url, data=data, **kwargs)
        self.previous_url = result.url
        return result


class PortalContractTests(unittest.TestCase):
    def test_authenticated_navigation_hidden_uid_pwd_is_not_login(self):
        self.assertFalse(scraper._is_login_page(AUTHENTICATED_AG102_PAGE))

    def test_authenticated_account_settings_and_last_login_text_is_not_login(self):
        self.assertFalse(scraper._is_login_page(AUTHENTICATED_ACCOUNT_SETTINGS_PAGE))

    def test_profile_text_with_login_account_and_password_words_is_not_login_without_form(self):
        profile_text = """
        <html><body><h1>帳號設定</h1>
        <p>最近登入紀錄：Last login 2026-09-03</p>
        <p>密碼最後更新時間：2026-08-01</p>
        </body></html>
        """
        self.assertFalse(scraper._is_login_page(profile_text))

    def test_authenticated_ag102_navigation_form_can_reach_pdf(self):
        session = AuthenticatedTranscriptSession()
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        result = client.fetch_transcript_pdf()
        self.assertTrue(result.startswith(b"%PDF-"))
        self.assertEqual(session.wrapper_response.close_count, 1)
        self.assertEqual(session.link_response.close_count, 1)
        client.close()

    def test_nonbinary_ag102_wrapper_closes_when_no_pdf_candidates(self):
        session = NoCandidateTranscriptSession()
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        with self.assertRaises(scraper.PortalError) as raised:
            client.fetch_transcript_pdf()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PDF_NOT_FOUND)
        self.assertEqual(session.wrapper_response.close_count, 1)
        client.close()

    def test_nonbinary_ag102_wrapper_and_linked_html_close_on_error(self):
        session = LinkedHtmlErrorTranscriptSession()
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        with self.assertRaises(scraper.PortalError) as raised:
            client.fetch_transcript_pdf()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PDF_NOT_FOUND)
        self.assertEqual(session.wrapper_response.close_count, 1)
        self.assertEqual(session.link_response.close_count, 1)
        client.close()

    def test_login_semantics_still_reject_http_200_login_pages(self):
        login_pages = (
            '<form action="/utaipei/login_check.jsp"><input name="uid"><input name="pwd"></form>',
            '<form id="login"><input name="uid"><input name="pwd"></form>',
            '<form><input name="account"><input name="password" type="password">登入</form>',
        )
        for page in login_pages:
            with self.subTest(page=page):
                self.assertTrue(scraper._is_login_page(page))

    def test_dynamic_login_action_is_followed(self):
        session = PortalSession()
        dynamic_form = LOGIN_FORM.replace('action="/utaipei/perchk.jsp"', 'action="/utaipei/dynamic/perchk.jsp"')

        def post(url, data=None, **kwargs):
            session.calls.append(("POST", url, data or {}, kwargs))
            if url.endswith("login_check.jsp"):
                return FakeResponse(text=dynamic_form, url=url)
            if url.endswith("perchk.jsp"):
                return FakeResponse(text=PERCHK_PAGE, url=url)
            return PortalSession.post(session, url, data=data, **kwargs)

        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        self.assertTrue(any("/dynamic/perchk.jsp" in call[1] for call in session.calls if call[0] == "POST"))
        client.close()

    def test_dynamic_index_login_action_and_controls_are_followed(self):
        session = PortalSession()
        index_form = """
        <form id="portal-login" action="/utaipei/dynamic/login.jsp" method="post">
          <input type="hidden" name="csrf" value="csrf-1">
          <input name="uid"><input name="pwd" type="password">
          <select name="mode"><option value="student">學生</option></select>
          <button name="go" value="login">登入</button>
        </form>
        """
        original_get = session.get

        def get(url, **kwargs):
            if url.endswith("index_main.html"):
                session.calls.append(("GET", url, kwargs))
                return FakeResponse(text=index_form, url=url)
            return original_get(url, **kwargs)

        original_post = session.post

        def post(url, data=None, **kwargs):
            if url.endswith("dynamic/login.jsp"):
                session.calls.append(("POST", url, data or {}, kwargs))
                return FakeResponse(text=LOGIN_FORM, url=url)
            return original_post(url, data=data, **kwargs)

        session.get = get
        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        login_call = next(call for call in session.calls if call[0] == "POST" and call[1].endswith("dynamic/login.jsp"))
        self.assertEqual(login_call[2]["csrf"], "csrf-1")
        self.assertEqual(login_call[2]["uid"], "u")
        self.assertEqual(login_call[2]["pwd"], "p")
        client.close()

    def test_same_origin_redirect_is_followed_and_validated(self):
        session = PortalSession()
        original_post = session.post
        original_get = session.get

        def post(url, data=None, **kwargs):
            if url.endswith("login_check.jsp"):
                session.calls.append(("POST", url, data or {}, kwargs))
                return FakeResponse(status_code=302, url=url, headers={"Location": scraper.PERCHK_URL})
            return original_post(url, data=data, **kwargs)

        def get(url, **kwargs):
            if url == scraper.PERCHK_URL:
                session.calls.append(("GET", url, kwargs))
                return FakeResponse(text=LOGIN_FORM, url=url)
            return original_get(url, **kwargs)

        session.post = post
        session.get = get
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        login_posts = [call for call in session.calls if call[0] == "POST" and call[1].endswith("login_check.jsp")]
        self.assertEqual(len(login_posts), 1)
        self.assertFalse(login_posts[0][3].get("allow_redirects", True))
        self.assertTrue(any(call[0] == "GET" and call[1] == scraper.PERCHK_URL for call in session.calls))
        client.close()

    def test_same_origin_redirect_is_followed_manually_with_get_semantics(self):
        session = RedirectSession("https://my.utaipei.edu.tw/utaipei/login_result.jsp")
        original_get = session.get

        def get(url, **kwargs):
            if url.endswith("login_result.jsp"):
                session.calls.append(("GET", url, kwargs))
                return FakeResponse(text=LOGIN_FORM, url=url)
            return original_get(url, **kwargs)

        session.get = get
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        self.assertEqual(session.evil_calls, 0)
        login_follow = [call for call in session.calls if call[0] == "GET" and call[1].endswith("login_result.jsp")]
        self.assertEqual(len(login_follow), 1)
        client.close()

    def test_redirect_response_is_closed_before_next_hop(self):
        class CloseAwareResponse(FakeResponse):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.was_closed = False

            def close(self):
                self.was_closed = True

        session = PortalSession()
        redirect_holder = {}
        original_get = session.get
        original_post = session.post

        def post(url, data=None, **kwargs):
            if url.endswith("login_check.jsp"):
                redirect = CloseAwareResponse(
                    status_code=302,
                    url=url,
                    headers={"Location": scraper.PERCHK_URL},
                )
                redirect_holder["response"] = redirect
                return redirect
            return original_post(url, data=data, **kwargs)

        def get(url, **kwargs):
            if url == scraper.PERCHK_URL:
                return FakeResponse(text=LOGIN_FORM, url=url)
            return original_get(url, **kwargs)

        session.post = post
        session.get = get
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        self.assertTrue(redirect_holder["response"].was_closed)
        client.close()

    def test_evil_redirect_is_rejected_before_any_evil_host_call(self):
        session = RedirectSession("https://evil.example/login_result.jsp")
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PORTAL_CHANGED)
        self.assertEqual(session.evil_calls, 0)
        self.assertTrue(session.closed)

    def test_sensitive_post_307_is_not_replayed(self):
        session = RedirectSession(scraper.PERCHK_URL, status_code=307)
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PORTAL_CHANGED)
        self.assertEqual(session.evil_calls, 0)
        self.assertTrue(session.closed)

    def test_cross_domain_redirect_is_rejected_even_when_final_response_is_200(self):
        session = PortalSession()
        original_post = session.post

        def post(url, data=None, **kwargs):
            if url.endswith("login_check.jsp"):
                session.calls.append(("POST", url, data or {}, kwargs))
                redirect = FakeResponse(status_code=302, url=url, headers={"Location": "https://evil.example/"})
                return FakeResponse(text=LOGIN_FORM, url=url, history=[redirect])
            return original_post(url, data=data, **kwargs)

        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PORTAL_CHANGED)
        self.assertTrue(session.closed)

    def test_captcha_page_fails_closed_with_dedicated_code(self):
        session = PortalSession()
        original_get = session.get

        def get(url, **kwargs):
            if url.endswith("index_main.html"):
                session.calls.append(("GET", url, kwargs))
                return FakeResponse(
                    text='<form action="/utaipei/login_check.jsp"><input name="uid"><input name="pwd"><div class="g-recaptcha"></div></form>',
                    url=url,
                )
            return original_get(url, **kwargs)

        session.get = get
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.CAPTCHA_REQUIRED)
        self.assertTrue(session.closed)

    def test_maintenance_page_is_not_a_valid_session_or_feature(self):
        session = PortalSession()
        original_post = session.post

        def post(url, data=None, **kwargs):
            if url.endswith("perchk.jsp"):
                session.calls.append(("POST", url, data or {}, kwargs))
                return FakeResponse(text="<html><title>系統維護</title><body>maintenance</body></html>", url=url)
            return original_post(url, data=data, **kwargs)

        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PORTAL_CHANGED)
        self.assertTrue(session.closed)

    def test_maintenance_entry_page_fails_closed_before_login_post(self):
        session = PortalSession()
        original_get = session.get

        def get(url, **kwargs):
            if url.endswith("index_main.html"):
                session.calls.append(("GET", url, kwargs))
                return FakeResponse(text="<html><title>維護中</title><body>系統維護中</body></html>", url=url)
            return original_get(url, **kwargs)

        session.get = get
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PORTAL_CHANGED)
        self.assertFalse(any(call[0] == "POST" for call in session.calls))
        self.assertTrue(session.closed)

    def test_maintenance_detector_rejects_chinese_and_english_pages_as_invalid(self):
        for page in (
            "<html><title>系統維護中</title><body>請稍後再試</body></html>",
            "<html><title>暫停服務</title><body>maintenance</body></html>",
            "<html><title>系統忙碌</title><body>service unavailable</body></html>",
        ):
            with self.subTest(page=page):
                self.assertTrue(scraper.is_maintenance_page(page))

    def test_login_controls_skip_disabled_and_unchecked_controls(self):
        session = PortalSession()
        index_form = """
        <form action="/utaipei/dynamic/login.jsp">
          <input type="hidden" name="csrf" value="csrf-2">
          <input type="hidden" name="disabled_hidden" value="no" disabled>
          <input name="uid"><input name="pwd" type="password">
          <input type="checkbox" name="unchecked" value="no">
          <input type="checkbox" name="checked" value="yes" checked>
          <input type="radio" name="radio" value="off">
          <input type="radio" name="radio" value="on" checked>
        </form>
        """
        original_get = session.get
        original_post = session.post

        def get(url, **kwargs):
            if url.endswith("index_main.html"):
                return FakeResponse(text=index_form, url=url)
            return original_get(url, **kwargs)

        def post(url, data=None, **kwargs):
            if url.endswith("dynamic/login.jsp"):
                session.captured_login_data = dict(data or {})
                return FakeResponse(text=LOGIN_FORM, url=url)
            return original_post(url, data=data, **kwargs)

        session.get = get
        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        self.assertEqual(session.captured_login_data["csrf"], "csrf-2")
        self.assertEqual(session.captured_login_data["checked"], "yes")
        self.assertEqual(session.captured_login_data["radio"], "on")
        self.assertNotIn("disabled_hidden", session.captured_login_data)
        self.assertNotIn("unchecked", session.captured_login_data)
        client.close()

    def test_dynamic_request_referers_follow_actual_previous_response_urls(self):
        session = StrictRefererSession()
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        client.login()
        client.fetch_transcript_pdf()
        self.assertEqual(session.violations, [])
        client.close()

    def test_cross_domain_dynamic_action_fails_closed_and_closes_session(self):
        session = PortalSession()

        def post(url, data=None, **kwargs):
            session.calls.append(("POST", url, data or {}, kwargs))
            if url.endswith("login_check.jsp"):
                return FakeResponse(
                    text=LOGIN_FORM.replace('action="/utaipei/perchk.jsp"', 'action="https://evil.example/x"'),
                    url=url,
                )
            return PortalSession.post(session, url, data=data, **kwargs)

        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError) as raised:
            client.login()
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PORTAL_CHANGED)
        self.assertTrue(session.closed)

    def test_octet_stream_pdf_is_accepted_without_pdf_extension(self):
        session = PortalSession(pdf=b"%PDF-1.7 octet")
        result = scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertTrue(result.startswith(b"%PDF-"))
        self.assertTrue(session.closed)

    def test_direct_pdf_uses_capped_streaming_reader_for_small_file(self):
        def chunks(_response):
            return iter((b"%PDF-1.7", b"small"))

        session = StreamingPortalSession(direct_chunks=chunks)
        result = scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(result, b"%PDF-1.7small")
        self.assertEqual(session.stream_response.iter_calls, 1)
        self.assertTrue(session.stream_response.closed)

    def test_direct_pdf_content_length_over_limit_is_rejected_without_reading(self):
        def fail_if_read(response):
            raise AssertionError("iter_content must not run after oversized Content-Length")

        session = StreamingPortalSession(
            direct_chunks=fail_if_read,
            content_length=scraper.MAX_PDF_BYTES + 1,
        )
        with self.assertRaises(scraper.PortalError) as raised:
            scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PDF_NOT_FOUND)
        self.assertEqual(session.stream_response.iter_calls, 0)
        self.assertTrue(session.stream_response.closed)

    def test_direct_pdf_stream_stops_after_limit_plus_one_without_reading_tail(self):
        def chunks(response):
            yield b"%PDF-"
            yield b"x" * scraper.MAX_PDF_BYTES
            response.tail_read = True
            yield b"tail that must never be consumed"

        session = StreamingPortalSession(direct_chunks=chunks)
        with self.assertRaises(scraper.PortalError) as raised:
            scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PDF_NOT_FOUND)
        self.assertFalse(session.stream_response.tail_read)
        self.assertTrue(session.stream_response.closed)

    def test_pdf_stream_with_invalid_signature_is_closed(self):
        def chunks(_response):
            return iter((b"not-a-pdf",))

        session = StreamingPortalSession(direct_chunks=chunks)
        with self.assertRaises(scraper.PortalError) as raised:
            scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PDF_NOT_FOUND)
        self.assertTrue(session.stream_response.closed)

    def test_linked_pdf_uses_the_same_capped_streaming_reader(self):
        def chunks(_response):
            return iter((b"%PDF-1.7", b"linked"))

        session = StreamingPortalSession(direct_chunks=chunks, linked=True)
        result = scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(result, b"%PDF-1.7linked")
        self.assertEqual(session.stream_response.iter_calls, 1)
        self.assertTrue(session.stream_response.closed)

    def test_linked_pdf_content_length_over_limit_is_rejected_without_reading(self):
        def fail_if_read(response):
            raise AssertionError("iter_content must not run after oversized Content-Length")

        session = StreamingPortalSession(
            direct_chunks=fail_if_read,
            linked=True,
            content_length=scraper.MAX_PDF_BYTES + 1,
        )
        with self.assertRaises(scraper.PortalError) as raised:
            scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(raised.exception.code, scraper.PortalErrorCode.PDF_NOT_FOUND)
        self.assertEqual(session.stream_response.iter_calls, 0)
        self.assertTrue(session.stream_response.closed)

    def test_pdf_exactly_at_limit_is_accepted(self):
        def chunks(_response):
            return iter((b"%PDF-", b"x" * (scraper.MAX_PDF_BYTES - 5)))

        session = StreamingPortalSession(direct_chunks=chunks)
        result = scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertEqual(len(result), scraper.MAX_PDF_BYTES)
        self.assertTrue(session.stream_response.closed)

    def test_http_200_login_page_is_rejected_before_transcript_fetch(self):
        session = PortalSession()

        def post(url, data=None, **kwargs):
            session.calls.append(("POST", url, data or {}, kwargs))
            if url.endswith("login_check.jsp"):
                return FakeResponse(text=LOGIN_PAGE, url=url)
            return PortalSession.post(session, url, data=data, **kwargs)

        session.post = post
        with self.assertRaises(scraper.PortalError) as raised:
            scraper._fetch_transcript_inline("u", "p", session=session)
        self.assertIn(raised.exception.code, {scraper.PortalErrorCode.SESSION_REJECTED, scraper.PortalErrorCode.PORTAL_CHANGED})
        self.assertTrue(session.closed)

    def test_failed_login_closes_session(self):
        session = PortalSession()

        def post(url, data=None, **kwargs):
            session.calls.append(("POST", url, data or {}, kwargs))
            if url.endswith("login_check.jsp"):
                return FakeResponse(text=LOGIN_PAGE, url=url)
            return PortalSession.post(session, url, data=data, **kwargs)

        session.post = post
        client = scraper.PortalClient("u", "p", session_factory=lambda: session)
        with self.assertRaises(scraper.PortalError):
            client.login()
        self.assertTrue(session.closed)

    def test_transcript_fetch_uses_one_login_and_returns_pdf(self):
        session = PortalSession()
        result = scraper._fetch_transcript_inline("u", "p", session=session)
        login_posts = [call for call in session.calls if call[0] == "POST" and call[1].endswith("login_check.jsp")]
        self.assertEqual(len(login_posts), 1)
        self.assertTrue(result.startswith(b"%PDF-"))
        self.assertTrue(session.closed)

    def test_sidebar_failure_preserves_previously_confirmed_data(self):
        state = {
            "transcript_pdf_bytes": b"%PDF-old",
            "transcript_pdf_path": None,
            "source_label": "已確認資料",
            "masked_student_id": "••••1234",
        }
        messages = []
        feedback = type(
            "Feedback",
            (),
            {
                "error": lambda self, value, **kwargs: messages.append(str(value)),
                "warning": lambda self, value, **kwargs: messages.append(str(value)),
                "success": lambda self, value, **kwargs: messages.append(str(value)),
                "info": lambda self, value, **kwargs: messages.append(str(value)),
            },
        )()
        fake_streamlit = type("FakeStreamlit", (), {"session_state": state})()
        with patch.object(sidebar, "st", fake_streamlit), patch.object(
            sidebar,
            "fetch_transcript",
            side_effect=scraper.PortalError(scraper.PortalErrorCode.SESSION_REJECTED),
        ):
            sidebar._attempt_live_scrape("u", "secret", ui=feedback)
        self.assertEqual(state["transcript_pdf_bytes"], b"%PDF-old")
        self.assertEqual(state["masked_student_id"], "••••1234")
        self.assertTrue(any("未套用" in message for message in messages))
        self.assertFalse(any(value in "\n".join(messages) for value in ("secret", "Cookie", "<html>")))

    def test_sidebar_commits_verified_transcript_without_timetable_state(self):
        state = {
            "transcript_pdf_bytes": b"%PDF-old",
            "transcript_pdf_path": None,
            "source_label": "已確認資料",
            "masked_student_id": "••••1234",
        }
        messages = []
        feedback = type(
            "Feedback",
            (),
            {
                "error": lambda self, value, **kwargs: messages.append(str(value)),
                "warning": lambda self, value, **kwargs: messages.append(str(value)),
                "success": lambda self, value, **kwargs: messages.append(str(value)),
                "info": lambda self, value, **kwargs: messages.append(str(value)),
            },
        )()
        fake_streamlit = type("FakeStreamlit", (), {"session_state": state})()
        with patch.object(sidebar, "st", fake_streamlit), patch.object(
            sidebar, "fetch_transcript", return_value=b"%PDF-new"
        ), patch.object(sidebar, "_validate_live_transcript"):
            sidebar._attempt_live_scrape("u", "secret", ui=feedback)
        self.assertEqual(state["transcript_pdf_bytes"], b"%PDF-new")
        self.assertEqual(state["source_label"], "校務系統即時抓取")
        joined = "\n".join(messages)
        self.assertIn("成績單", joined)
        self.assertNotIn("secret", joined)

    def test_login_form_does_not_relabel_existing_data_before_fetch_success(self):
        class Form:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Ui:
            def markdown(self, *_args, **_kwargs):
                return None

            def caption(self, *_args, **_kwargs):
                return None

            def form(self, *_args, **_kwargs):
                return Form()

            def text_input(self, label, **_kwargs):
                return "new-account" if "學號" in label or "Account" in label else "new-password"

            def columns(self, count):
                return [self for _ in range(count)]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def selectbox(self, label, **_kwargs):
                return "115" if "學年度" in label else "1"

            def form_submit_button(self, *_args, **_kwargs):
                return True

        state = {"masked_student_id": "••••1234"}
        fake_streamlit = type("FakeStreamlit", (), {"session_state": state})()
        with patch.object(sidebar, "st", fake_streamlit), patch.object(sidebar, "_attempt_live_scrape"):
            sidebar._render_login_section(Ui())
        self.assertEqual(state["masked_student_id"], "••••1234")


if __name__ == "__main__":
    unittest.main()
