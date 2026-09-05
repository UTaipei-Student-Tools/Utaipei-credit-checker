from types import SimpleNamespace

import scripts.portal_live_diagnostic as live_diagnostic


def _response(html: str, url: str = "https://my.utaipei.edu.tw/utaipei/ag_pro/ag102.jsp"):
    return SimpleNamespace(
        status_code=200,
        url=url,
        headers={"Content-Type": "text/html; charset=UTF-8"},
        text=html,
        content=html.encode("utf-8"),
        encoding="utf-8",
        apparent_encoding="utf-8",
        close=lambda: None,
    )


def test_diagnostic_uses_product_pdf_extraction_for_wrapper_response(monkeypatch):
    fnc_response = _response(
        '<form id="thisform" action="/utaipei/ag_pro/ag102.jsp">'
        '<input type="hidden" name="fncid" value="AG102"></form>',
        "https://my.utaipei.edu.tw/utaipei/fnc.jsp",
    )
    wrapper_response = _response(
        '<html><body><h1>歷年成績單下載</h1>'
        '<iframe src="/utaipei/servlet/transcript?id=private"></iframe>'
        "</body></html>"
    )

    class FakeClient:
        _last_response_url = "https://my.utaipei.edu.tw/utaipei/perchk.jsp"

        def __init__(self, _account, _password):
            self.extraction_input = None

        def login(self):
            return None

        def _create_fnc(self, _fncid):
            return fnc_response

        def _request(self, *_args, **_kwargs):
            return wrapper_response

        def _extract_pdf(self, response):
            self.extraction_input = response
            return b"%PDF-1.7 validated"

        def close(self):
            return None

    client_holder = {}

    def build_client(account, password):
        client = FakeClient(account, password)
        client_holder["client"] = client
        return client

    monkeypatch.setattr(live_diagnostic, "load_portal_credentials", lambda _path: ("account", "password"))
    monkeypatch.setattr(live_diagnostic, "PortalClient", build_client)

    result = live_diagnostic.diagnose(object())
    assert result["ok"] is True
    assert result["stages"][-1]["stage"] == "ag102_pdf"
    assert result["stages"][-1]["ok"] is True
    assert client_holder["client"].extraction_input is wrapper_response
