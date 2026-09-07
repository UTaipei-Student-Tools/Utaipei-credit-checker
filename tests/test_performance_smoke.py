from __future__ import annotations

import pytest

from scripts.performance_smoke import _safe_url, _summarize


def test_summarize_reports_distribution_without_sample_payloads():
    summary = _summarize([100.0, 300.0, 200.0, 400.0])

    assert summary == {
        "count": 4,
        "min_ms": 100.0,
        "p50_ms": 250.0,
        "p95_ms": 385.0,
        "max_ms": 400.0,
    }


@pytest.mark.parametrize(
    "value",
    (
        "file:///tmp/private",
        "javascript:alert(1)",
        "https://user:secret@example.test/",
        "https://example.test/?token=secret",
        "https://example.test/#password=secret",
    ),
)
def test_safe_url_rejects_local_or_credential_bearing_targets(value):
    with pytest.raises(ValueError):
        _safe_url(value)


def test_safe_url_accepts_loopback_and_public_http_origins_without_query():
    assert _safe_url("http://127.0.0.1:8505/") == "http://127.0.0.1:8505/"
    assert _safe_url("https://example.test/app") == "https://example.test/app"
