import pytest
from fastapi.testclient import TestClient

import app.web.main as web_main
from app.web.main import _validated_github_pages_origin, app

client = TestClient(app)


def test_health_and_no_store_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["remote_login_enabled"] is False
    assert response.headers["cache-control"].startswith("no-store")
    assert "huggingface.co" in response.headers["content-security-policy"]
    assert "x-frame-options" not in response.headers


def test_github_pages_origin_is_allowed_without_credentials():
    response = client.options(
        "/audit/upload",
        headers={
            "Origin": "https://jimmymochi.github.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://jimmymochi.github.io"
    assert "access-control-allow-credentials" not in response.headers


def test_unknown_cross_origin_is_not_allowed():
    response = client.options(
        "/audit/upload",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "http://jimmymochi.github.io",
        "https://jimmymochi.github.io/utaipei-credit-audit",
        "https://jimmymochi.github.io?scope=all",
        "https://user:password@jimmymochi.github.io",
    ],
)
def test_github_pages_origin_rejects_non_origins(value: str):
    with pytest.raises(ValueError):
        _validated_github_pages_origin(value)


def test_github_pages_origin_allows_https_origin_or_empty_disable():
    assert _validated_github_pages_origin("https://jimmymochi.github.io/") == "https://jimmymochi.github.io"
    assert _validated_github_pages_origin("  ") == ""


def test_remote_login_is_disabled_by_default():
    response = client.post("/audit/login", data={"username": "u", "password": "p"})
    assert response.status_code == 403


def test_upload_selection_html_returns_public_result_without_raw():
    html = """
    <table>
      <tr><th>選課代號</th><th>課程名稱</th><th>學分</th><th>必選修</th></tr>
      <tr><td>12345</td><td>演算法</td><td>3</td><td>必修</td></tr>
    </table>
    """
    response = client.post("/audit/upload", data={"selection_html_text": html})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_quality"] == "complete"
    assert "unparsed_samples" not in payload["diagnostics"][0]
    course = payload["results"][0]["in_progress"][0]
    assert course["name"] == "演算法"
    assert "raw" not in course


def test_invalid_selection_html_stops_audit():
    response = client.post("/audit/upload", data={"selection_html_text": "<p>not a table</p>"})
    assert response.status_code == 422


def test_upload_requires_input():
    response = client.post("/audit/upload", data={})
    assert response.status_code == 422


def test_invalid_pdf_signature_is_rejected():
    response = client.post(
        "/audit/upload",
        files={"transcript_pdf": ("transcript.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_static_assets_are_served():
    css = client.get("/static/styles.css")
    js = client.get("/static/app.js")
    assert css.status_code == 200
    assert js.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert "javascript" in js.headers["content-type"]


def test_index_uses_relative_assets_and_same_origin_api_on_hf():
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="./static/styles.css"' in response.text
    assert 'src="./static/app.js"' in response.text
    assert 'data-api-base-url=""' in response.text
    assert "{{REMOTE_LOGIN_ENABLED}}" not in response.text
    assert "{{MAX_UPLOAD_MB}}" not in response.text
    assert "{{API_BASE_URL}}" not in response.text


def test_unhandled_error_response_preserves_pages_cors(monkeypatch: pytest.MonkeyPatch):
    def raise_unexpected_error(_html: str):
        raise RuntimeError("private parser detail")

    monkeypatch.setattr(web_main, "parse_selection_html_with_diagnostics", raise_unexpected_error)
    with TestClient(app, raise_server_exceptions=False) as error_client:
        response = error_client.post(
            "/audit/upload",
            data={"selection_html_text": "<table></table>"},
            headers={"Origin": "https://jimmymochi.github.io"},
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://jimmymochi.github.io"
    assert response.headers["vary"] == "Origin"
    assert "private parser detail" not in response.text
