from fastapi.testclient import TestClient

from app.web.main import app

client = TestClient(app)


def test_health_and_no_store_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["remote_login_enabled"] is False
    assert response.headers["cache-control"].startswith("no-store")
    assert "huggingface.co" in response.headers["content-security-policy"]
    assert "x-frame-options" not in response.headers


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
