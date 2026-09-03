"""Safe, session-aware access to the UTaipei student portal.

The portal frequently returns an HTML login page with status code 200. This
module therefore treats transport status and page identity as separate
contracts. The application intentionally imports only the transcript path:
login and the validated AG102 PDF are the only live portal data used for
graduation analysis.
"""

import re
from enum import Enum
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

LOGIN_URL = "https://my.utaipei.edu.tw/utaipei/login_check.jsp"
PERCHK_URL = "https://my.utaipei.edu.tw/utaipei/perchk.jsp"
FNC_URL = "https://my.utaipei.edu.tw/utaipei/fnc.jsp"
BASE_URL = "https://my.utaipei.edu.tw/utaipei/"
PORTAL_HOST = "my.utaipei.edu.tw"
ALLOWED_PORTAL_HOSTS = frozenset({PORTAL_HOST})
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_REDIRECT_HOPS = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://my.utaipei.edu.tw/utaipei/index_main.html",
}

_MAINTENANCE_MARKERS = (
    "維護中",
    "暫停服務",
    "系統忙碌",
    "系統維護",
    "maintenance",
    "service unavailable",
    "temporarily unavailable",
    "system busy",
    "under maintenance",
)
_LOGIN_FORM_IDS = {"login", "loginform", "login_form", "login-form"}
_LOGIN_CONTEXT_MARKERS = ("登入", "sign in", "log in", "login page", "login form", "login portal")


def _clean_page_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_maintenance_page(html_content):
    """Return true for known maintenance/interstitial page language."""

    if not html_content:
        return False
    soup = BeautifulSoup(str(html_content), "html.parser")
    text = _clean_page_text(soup.get_text(" ", strip=True)).lower()
    return any(marker.lower() in text for marker in _MAINTENANCE_MARKERS)


def _has_login_context(text):
    normalized = _clean_page_text(text).lower()
    if "登入" in normalized:
        return True
    return any(marker in normalized for marker in _LOGIN_CONTEXT_MARKERS[1:])


def is_login_page(html_content):
    """Identify a login page without mistaking authenticated hidden controls."""

    if not html_content:
        return False
    soup = BeautifulSoup(str(html_content), "html.parser")
    visible_text = _clean_page_text(soup.get_text(" ", strip=True))
    for form in soup.find_all("form"):
        action = str(form.get("action") or "").lower()
        form_id = str(form.get("id") or "").lower()
        if "login_check" in action or form_id in _LOGIN_FORM_IDS or form_id.startswith("login"):
            return True
        has_password_input = any(
            str(control.get("type") or "").lower() == "password" for control in form.find_all("input")
        )
        form_text = _clean_page_text(form.get_text(" ", strip=True))
        if has_password_input and (_has_login_context(form_text) or _has_login_context(visible_text)):
            return True
    return False

class PortalErrorCode(str, Enum):
    """Stable, non-sensitive failure categories exposed to the UI."""

    NETWORK_BLOCKED = "NETWORK_BLOCKED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    SESSION_REJECTED = "SESSION_REJECTED"
    PORTAL_CHANGED = "PORTAL_CHANGED"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    PDF_NOT_FOUND = "PDF_NOT_FOUND"
    AUTH_REJECTED = "AUTH_REJECTED"
    RATE_LIMITED = "RATE_LIMITED"


_PORTAL_MESSAGES = {
    PortalErrorCode.NETWORK_BLOCKED: "校務系統目前無法連線，請改用 PDF 或稍後重試。",
    PortalErrorCode.CAPTCHA_REQUIRED: "校務系統要求人工驗證，請改用 PDF 上傳。",
    PortalErrorCode.SESSION_REJECTED: "校務系統登入狀態已失效，請重新登入或改用 PDF。",
    PortalErrorCode.PORTAL_CHANGED: "校務系統頁面結構或網址已變更，請改用 PDF 並通知維護者。",
    PortalErrorCode.UPSTREAM_TIMEOUT: "校務系統回應逾時，請稍後重試或改用 PDF。",
    PortalErrorCode.PDF_NOT_FOUND: "校務系統未提供可驗證的成績單 PDF，請改用 PDF 上傳。",
    PortalErrorCode.AUTH_REJECTED: "校務系統拒絕登入，請確認帳號密碼或改用 PDF。",
    PortalErrorCode.RATE_LIMITED: "校務系統暫時限制請求，請稍後再試。",
}


class PortalError(RuntimeError):
    """An intentionally safe portal error with no response or credential text."""

    def __init__(self, code, message=None):
        try:
            normalized = code if isinstance(code, PortalErrorCode) else PortalErrorCode(str(code))
        except ValueError:
            normalized = PortalErrorCode.PORTAL_CHANGED
        self.code = normalized
        self.error_code = normalized
        self.message = message if message in _PORTAL_MESSAGES.values() else _PORTAL_MESSAGES[normalized]
        super().__init__(self.message)

    def __str__(self):
        return self.message


def _safe_portal_url(target, base_url=BASE_URL):
    """Resolve a portal URL and reject scheme/host changes before requesting."""

    candidate = urljoin(str(base_url or BASE_URL), str(target or ""))
    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError:
        raise PortalError(PortalErrorCode.PORTAL_CHANGED) from None
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() not in ALLOWED_PORTAL_HOSTS
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise PortalError(PortalErrorCode.PORTAL_CHANGED)
    return candidate


def _response_headers(response):
    headers = getattr(response, "headers", None)
    return headers if hasattr(headers, "get") else {}


def _response_url(response, fallback):
    value = getattr(response, "url", None)
    return str(value or fallback)


def _check_response_origin(response, request_url):
    """Reject a cross-domain redirect or final response, even when HTTP 200."""

    final_url = _safe_portal_url(_response_url(response, request_url), request_url)
    for previous in getattr(response, "history", ()) or ():
        _safe_portal_url(_response_url(previous, request_url), request_url)
        location = _response_headers(previous).get("Location") or _response_headers(previous).get("location")
        if location:
            _safe_portal_url(location, _response_url(previous, request_url))
    location = _response_headers(response).get("Location") or _response_headers(response).get("location")
    if location:
        _safe_portal_url(location, final_url)
    return final_url


def _map_request_exception(exc):
    if isinstance(exc, (requests.Timeout, TimeoutError)):
        return PortalError(PortalErrorCode.UPSTREAM_TIMEOUT)
    return PortalError(PortalErrorCode.NETWORK_BLOCKED)


def _is_login_page(html_content):
    return is_login_page(html_content)


def _is_captcha_page(html_content):
    """Detect human-verification interstitials without returning their markup."""

    if not html_content:
        return False
    soup = BeautifulSoup(str(html_content), "html.parser")
    visible_text = " ".join(soup.get_text(" ", strip=True).split()).lower()
    compact_html = str(html_content).lower()
    if any(marker in visible_text for marker in ("captcha", "recaptcha", "hcaptcha", "驗證碼", "challenge")):
        return True
    return any(
        marker in compact_html
        for marker in (
            "captcha",
            "recaptcha",
            "hcaptcha",
            'name="challenge"',
            "name='challenge'",
            'id="challenge"',
            "id='challenge'",
        )
    )


def _has_session_identity(html_content):
    soup = BeautifulSoup(str(html_content or ""), "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split()).lower()
    return any(marker in text for marker in ("校務系統", "主選單", "學生", "utaipei", "成績"))


def _has_fnc_identity(html_content, expected_fncid):
    soup = BeautifulSoup(str(html_content or ""), "html.parser")
    expected = str(expected_fncid or "").lower()
    if expected and expected in str(html_content or "").lower():
        return bool(soup.find("form"))
    for form in soup.find_all("form"):
        action = str(form.get("action") or "").lower()
        if expected and expected in action and form.get("id") == "thisform":
            return True
    return False


def _validate_transport(response, request_url):
    _check_response_origin(response, request_url)
    status = int(getattr(response, "status_code", 0) or 0)
    if status == 403:
        raise PortalError(PortalErrorCode.NETWORK_BLOCKED)
    if status in {401, 419}:
        raise PortalError(PortalErrorCode.SESSION_REJECTED)
    if status == 429:
        raise PortalError(PortalErrorCode.RATE_LIMITED)
    if status in {408, 504}:
        raise PortalError(PortalErrorCode.UPSTREAM_TIMEOUT)
    if status != 200:
        raise PortalError(PortalErrorCode.NETWORK_BLOCKED)
    return response


def _header_value(response, name):
    """Read a response header from both normal and case-insensitive mappings."""

    wanted = str(name).lower()
    headers = _response_headers(response)
    items = getattr(headers, "items", None)
    if callable(items):
        for key, value in items():
            if str(key).lower() == wanted:
                return value
    else:
        value = headers.get(name)
        if value is not None:
            return value
    return ""


def _is_binary_pdf_response(response):
    """Identify response metadata that permits the capped PDF reader."""

    content_type = str(_header_value(response, "Content-Type") or "").lower()
    disposition = str(_header_value(response, "Content-Disposition") or "").lower()
    return (
        "pdf" in content_type
        or content_type in {"application/octet-stream", "binary/octet-stream"}
        or "attachment" in disposition
        or "filename=" in disposition
    )


_SENSITIVE_REDIRECT_KEYS = frozenset(
    {
        "account",
        "cookie",
        "csrf",
        "idno",
        "password",
        "passwd",
        "pwd",
        "secret",
        "session",
        "student",
        "student_id",
        "token",
        "uid",
    }
)


def _contains_sensitive_post_data(data):
    """Return whether redirect replay could expose credentials or a token."""

    if data is None:
        return False
    if isinstance(data, dict):
        return any(str(key).strip().lower() in _SENSITIVE_REDIRECT_KEYS for key in data)
    # Unknown encoded request bodies are conservatively treated as sensitive.
    return bool(data)


def _close_response(response):
    """Release a redirect response before opening its next hop."""

    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _request_with_safe_redirects(session, method, url, *, referer=None, data=None, timeout=15, stream=False):
    """Issue one request while validating every redirect before following it."""

    target = _safe_portal_url(url)
    current_method = str(method or "GET").upper()
    current_data = data
    current_referer = referer
    for hop in range(MAX_REDIRECT_HOPS + 1):
        headers = {**HEADERS}
        if current_referer:
            headers["Referer"] = _safe_portal_url(current_referer)
        request_kwargs = {
            "headers": headers,
            "data": current_data,
            "timeout": timeout,
            "allow_redirects": False,
        }
        if stream:
            request_kwargs["stream"] = True
        try:
            response = getattr(session, current_method.lower())(target, **request_kwargs)
        except PortalError:
            raise
        except Exception as exc:
            raise _map_request_exception(exc) from None

        # Validate Location and final URL before inspecting status or issuing
        # another request.  This guarantees an evil origin receives no call.
        try:
            _check_response_origin(response, target)
        except Exception:
            _close_response(response)
            raise
        status = int(getattr(response, "status_code", 0) or 0)
        if status in {301, 302, 303, 307, 308}:
            try:
                if hop >= MAX_REDIRECT_HOPS:
                    raise PortalError(PortalErrorCode.PORTAL_CHANGED)
                location = _header_value(response, "Location")
                if not location:
                    raise PortalError(PortalErrorCode.PORTAL_CHANGED)
                next_target = _safe_portal_url(location, _response_url(response, target))
                if status in {307, 308}:
                    if current_method in {"POST", "PUT", "PATCH"} and _contains_sensitive_post_data(current_data):
                        raise PortalError(PortalErrorCode.PORTAL_CHANGED)
                    next_method = current_method
                    next_data = current_data
                else:
                    # Match browser/requests semantics for form POST redirects.
                    next_method = "GET" if current_method == "POST" else current_method
                    next_data = None if next_method == "GET" else current_data
                current_referer = _response_url(response, target)
                target = next_target
                current_method = next_method
                current_data = next_data
            finally:
                _close_response(response)
            continue
        return _validate_transport(response, target)
    raise PortalError(PortalErrorCode.PORTAL_CHANGED)


def _validate_html_identity(response, request_url, *, role, expected_fncid=None):
    """Apply the page identity guard to each HTTP 200 HTML response."""

    _validate_transport(response, request_url)
    headers = _response_headers(response)
    disposition = str(headers.get("Content-Disposition", "")).lower()
    if _is_binary_pdf_response(response) or "attachment" in disposition:
        return response
    html = getattr(response, "text", "") or ""
    if not html.strip():
        raise PortalError(PortalErrorCode.PORTAL_CHANGED)
    if _is_captcha_page(html):
        raise PortalError(PortalErrorCode.CAPTCHA_REQUIRED)
    if role != "entry" and _is_login_page(html):
        raise PortalError(PortalErrorCode.SESSION_REJECTED)
    if is_maintenance_page(html):
        raise PortalError(PortalErrorCode.PORTAL_CHANGED)
    if role == "login":
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", id="thisform")
        error = soup.find("input", id="err")
        if error and str(error.get("value", "")).upper() == "Y":
            raise PortalError(PortalErrorCode.AUTH_REJECTED)
        if not form:
            raise PortalError(PortalErrorCode.AUTH_REJECTED)
    elif role == "session" and not _has_session_identity(html):
        raise PortalError(PortalErrorCode.PORTAL_CHANGED)
    elif role == "fnc" and not _has_fnc_identity(html, expected_fncid):
        raise PortalError(PortalErrorCode.PORTAL_CHANGED)
    return response


def _form_controls(form):
    """Collect named hidden/select/button controls without trusting markup."""

    values = {}
    for control in form.find_all(["input", "select", "button"]):
        if control.has_attr("disabled"):
            continue
        name = str(control.get("name") or "").strip()
        if not name:
            continue
        tag = control.name.lower()
        if tag == "select":
            options = [option for option in control.find_all("option") if not option.has_attr("disabled")]
            option = next((item for item in options if item.has_attr("selected")), None) or (options[0] if options else None)
            values[name] = str((option or {}).get("value", "") if option else "")
        elif tag == "button":
            values[name] = str(control.get("value", ""))
        else:
            input_type = str(control.get("type") or "hidden").lower()
            if input_type in {"submit", "button", "reset", "file"}:
                continue
            if input_type in {"checkbox", "radio"} and not control.has_attr("checked"):
                continue
            values[name] = str(control.get("value", ""))
    return values


def _find_form(response, *, form_id="thisform"):
    soup = BeautifulSoup(getattr(response, "text", "") or "", "html.parser")
    return soup.find("form", id=form_id) or soup.find("form")


def _find_login_form(response):
    """Return the first form that explicitly accepts both login controls."""

    soup = BeautifulSoup(getattr(response, "text", "") or "", "html.parser")
    for form in soup.find_all("form"):
        names = {
            str(control.get("name") or "").strip().lower()
            for control in form.find_all(["input", "select", "button"])
        }
        if {"uid", "pwd"}.issubset(names):
            return form
    return None


class PortalClient:
    """One authenticated portal client; callers own its close lifecycle."""

    def __init__(self, uid, pwd, *, session_factory=None, session=None, timeout=15):
        self.uid = str(uid or "").strip()
        self.pwd = str(pwd or "")
        if session is not None:
            self._session_factory = lambda: session
        else:
            self._session_factory = session_factory or requests.Session
        self.timeout = timeout
        self.session = self._session_factory()
        self._logged_in = False
        self._last_response_url = None

    def close(self):
        session = self.session
        self.session = None
        self.pwd = ""
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False

    def _request(self, method, url, *, referer=None, data=None, timeout=None, stream=False):
        return _request_with_safe_redirects(
            self.session,
            method,
            url,
            referer=referer,
            data=data,
            timeout=timeout or self.timeout,
            stream=stream,
        )

    def _post_form(self, response, *, fallback_url, data=None, referer=None, role="portal", stream=False):
        form = _find_form(response)
        if not form:
            raise PortalError(PortalErrorCode.PORTAL_CHANGED)
        action = _safe_portal_url(form.get("action") or fallback_url, _response_url(response, fallback_url))
        payload = _form_controls(form)
        payload.update(data or {})
        result = self._request(
            "POST",
            action,
            referer=referer or _response_url(response, fallback_url),
            data=payload,
            stream=stream,
        )
        self._last_response_url = _response_url(result, action)
        return _validate_html_identity(result, _response_url(result, action), role=role)

    def login(self):
        if self._logged_in:
            return self
        if not self.uid or not self.pwd:
            self.close()
            raise PortalError(PortalErrorCode.AUTH_REJECTED)
        try:
            entry_url = BASE_URL + "index_main.html"
            entry_response = self._request("GET", entry_url, referer=BASE_URL, timeout=self.timeout)
            _validate_html_identity(entry_response, entry_url, role="entry")
            login_data = {
                "uid": self.uid,
                "pwd": self.pwd,
                "myway": "yes",
                "check_choice": "",
                "teach_roll": "",
                "std_dorm": "",
                "std_vote": "",
                "std_choice": "",
            }
            login_form = _find_login_form(entry_response)
            if login_form is None:
                if BeautifulSoup(getattr(entry_response, "text", "") or "", "html.parser").find("form"):
                    raise PortalError(PortalErrorCode.PORTAL_CHANGED)
                login_action = LOGIN_URL
            else:
                login_action = _safe_portal_url(
                    login_form.get("action") or LOGIN_URL,
                    _response_url(entry_response, entry_url),
                )
                login_data = _form_controls(login_form)
                login_data.update({"uid": self.uid, "pwd": self.pwd})
            entry_response_url = _response_url(entry_response, entry_url)
            response = self._request("POST", login_action, referer=entry_response_url, data=login_data)
            login_response_url = _response_url(response, login_action)
            _validate_html_identity(response, login_response_url, role="login")
            # The successful login response supplies the actual per-session
            # action. A hard-coded perchk endpoint would break on a portal
            # change and could post to an attacker-controlled action.
            self._post_form(
                response,
                fallback_url=PERCHK_URL,
                referer=login_response_url,
                role="session",
            )
            self._logged_in = True
            return self
        except PortalError:
            self.close()
            raise
        except Exception:
            self.close()
            raise PortalError(PortalErrorCode.PORTAL_CHANGED) from None

    def _create_fnc(self, fncid):
        response = self._request(
            "POST",
            FNC_URL,
            referer=self._last_response_url or PERCHK_URL,
            data={
                "fncid": fncid,
                "hid_type": "S",
                "hid_choice_check": "",
                "hid_teach_roll": "",
                "hid_dorm_room": "",
                "hid_std_vote": "",
                "hid_std_choice": "",
                "hid_atd": "0",
            },
        )
        response_url = _response_url(response, FNC_URL)
        self._last_response_url = response_url
        return _validate_html_identity(response, response_url, role="fnc", expected_fncid=fncid)

    def fetch_transcript_pdf(self):
        if not self._logged_in:
            raise PortalError(PortalErrorCode.SESSION_REJECTED)
        try:
            response = self._create_fnc("AG102")
            fnc_response_url = _response_url(response, FNC_URL)
            result = self._post_form(
                response,
                fallback_url=BASE_URL + "ag_pro/ag102.jsp",
                referer=fnc_response_url,
                role="portal",
                stream=True,
            )
            return self._extract_pdf(result)
        except PortalError:
            raise
        except Exception:
            raise PortalError(PortalErrorCode.PDF_NOT_FOUND) from None

    def _extract_pdf(self, response):
        if _is_binary_pdf_response(response):
            return _read_pdf_response(response)
        try:
            html = getattr(response, "text", "") or ""
            if _is_captcha_page(html):
                raise PortalError(PortalErrorCode.CAPTCHA_REQUIRED)
            if _is_login_page(html):
                raise PortalError(PortalErrorCode.SESSION_REJECTED)
            soup = BeautifulSoup(html, "html.parser")
            candidates = []
            for element, attribute in (
                ("a", "href"),
                ("iframe", "src"),
                ("embed", "src"),
                ("object", "data"),
            ):
                for node in soup.find_all(element):
                    value = str(node.get(attribute) or "").strip()
                    if not value:
                        continue
                    hint = " ".join(
                        [value, str(node.get_text(" ", strip=True)), str(node.get("title") or "")]
                    ).lower()
                    if ".pdf" in hint or "下載" in hint or "transcript" in hint or "download" in hint:
                        candidates.append(value)
            if not candidates:
                raise PortalError(PortalErrorCode.PDF_NOT_FOUND)
            for candidate in candidates:
                pdf_url = _safe_portal_url(candidate, _response_url(response, BASE_URL))
                pdf_response = None
                try:
                    pdf_response = self._request(
                        "GET",
                        pdf_url,
                        referer=_response_url(response, BASE_URL),
                        timeout=25,
                        stream=True,
                    )
                    if _is_binary_pdf_response(pdf_response):
                        return _read_pdf_response(pdf_response)
                    linked_html = getattr(pdf_response, "text", "") or ""
                    if _is_login_page(linked_html):
                        raise PortalError(PortalErrorCode.SESSION_REJECTED)
                finally:
                    # Binary responses are already owned and closed by
                    # _read_pdf_response.  This branch owns only the
                    # non-binary candidate response, so it closes exactly
                    # once even when the candidate is an error/login page.
                    if pdf_response is not None and not _is_binary_pdf_response(pdf_response):
                        _close_response(pdf_response)
            raise PortalError(PortalErrorCode.PDF_NOT_FOUND)
        finally:
            # A non-binary AG102 wrapper belongs to this extraction call.  It
            # must not remain open while linked candidates are inspected.
            _close_response(response)

def _validated_pdf(content):
    if not content.startswith(b"%PDF-"):
        raise PortalError(PortalErrorCode.PDF_NOT_FOUND)
    if len(content) > MAX_PDF_BYTES:
        raise PortalError(PortalErrorCode.PDF_NOT_FOUND)
    return content


def _read_pdf_response(response):
    """Read a PDF response with a hard cap before materializing its bytes."""
    try:
        content_length = str(_header_value(response, "Content-Length") or "").strip()
        try:
            declared_length = int(content_length) if content_length else None
        except (TypeError, ValueError):
            declared_length = None
        if declared_length is not None and declared_length > MAX_PDF_BYTES:
            raise PortalError(PortalErrorCode.PDF_NOT_FOUND)

        iterator = getattr(response, "iter_content", None)
        if callable(iterator):
            chunks = []
            total = 0
            try:
                stream = iterator(chunk_size=64 * 1024)
            except TypeError:
                # Keep compatibility with small response doubles and old clients;
                # the requests product path accepts chunk_size above.
                stream = iterator()
            for chunk in stream:
                if not chunk:
                    continue
                piece = bytes(chunk)
                total += len(piece)
                if total > MAX_PDF_BYTES:
                    raise PortalError(PortalErrorCode.PDF_NOT_FOUND)
                chunks.append(piece)
            return _validated_pdf(b"".join(chunks))

        # Legacy response doubles may expose only ``content``.  This fallback is
        # deliberately unreachable for the streaming requests product path.
        return _validated_pdf(bytes(getattr(response, "content", b"") or b""))
    finally:
        _close_response(response)


def _start_session(uid, pwd):
    """Compatibility helper returning a logged-in Session owned by the caller."""

    client = PortalClient(uid, pwd)
    try:
        client.login()
    except Exception:
        client.close()
        raise
    return client.session


def _create_fnc_session(session, fncid):
    """Compatibility helper for callers that already own a verified Session."""

    target = _safe_portal_url(FNC_URL)
    response = _request_with_safe_redirects(
        session,
        "POST",
        target,
        referer=PERCHK_URL,
        data={
            "fncid": fncid,
            "hid_type": "S",
            "hid_choice_check": "",
            "hid_teach_roll": "",
            "hid_dorm_room": "",
            "hid_std_vote": "",
            "hid_std_choice": "",
            "hid_atd": "0",
        },
        timeout=15,
    )
    _validate_html_identity(response, _response_url(response, target), role="fnc", expected_fncid=fncid)
    return response


def _submit_portal_form(session, action_path, form_data, referer):
    """Compatibility helper with same-host action and response checks."""

    target = _safe_portal_url(action_path, referer or BASE_URL)
    response = _request_with_safe_redirects(
        session,
        "POST",
        target,
        referer=referer or BASE_URL,
        data=form_data,
        timeout=20,
    )
    _validate_html_identity(response, _response_url(response, target), role="portal")
    return response


def fetch_transcript(uid, pwd):
    """Authenticate once and return only the validated transcript PDF bytes."""

    client = PortalClient(uid, pwd)
    try:
        client.login()
        return client.fetch_transcript_pdf()
    finally:
        client.close()


def crawl_transcript_pdf(uid, pwd, download_dir=None):
    """Backward-compatible one-shot transcript PDF fetch returning bytes.

    download_dir is retained for callers from the earlier API. The current
    implementation never writes credentials or transcript bytes to a shared
    filesystem, so the argument is intentionally ignored.
    """

    del download_dir
    return fetch_transcript(uid, pwd)
