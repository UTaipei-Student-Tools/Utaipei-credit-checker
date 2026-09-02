from pathlib import Path

import pytest

from scripts.build_pages import ROOT, build_pages


def test_build_pages_reuses_static_frontend(tmp_path: Path):
    output = tmp_path / "pages"
    build_pages(output)

    index = (output / "index.html").read_text(encoding="utf-8")
    assert (output / "static" / "app.js").is_file()
    assert (output / "static" / "styles.css").is_file()
    assert (output / ".nojekyll").is_file()
    assert (output / ".utaipei-credit-audit-pages").is_file()
    assert "https://sapphirejimmy-utaipei-credit-audit.hf.space" in index
    assert 'data-remote-login-enabled="false"' in index
    assert 'href="./static/styles.css"' in index
    assert "{{" not in index


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://example.com/path",
        "https://example.com?debug=true",
        "https://example.com#fragment",
        "https://user:password@example.com",
        "https://*",
        "javascript:alert(1)",
        "",
    ],
)
def test_build_pages_rejects_invalid_api_origins(tmp_path: Path, value: str):
    with pytest.raises(ValueError):
        build_pages(tmp_path / "pages", value)


@pytest.mark.parametrize("value", [-1, 0, 1025, True])
def test_build_pages_rejects_invalid_upload_limits(tmp_path: Path, value: int):
    with pytest.raises(ValueError):
        build_pages(tmp_path / "pages", max_upload_mb=value)


def test_build_pages_will_not_replace_source_directory():
    source_sentinel = ROOT / "tests" / "test_pages.py"
    with pytest.raises(ValueError):
        build_pages(ROOT / "tests")
    assert source_sentinel.is_file()


def test_build_pages_can_replace_its_own_marked_output(tmp_path: Path):
    output = tmp_path / "pages"
    build_pages(output)
    stale_file = output / "stale.txt"
    stale_file.write_text("old", encoding="utf-8")

    build_pages(output)

    assert not stale_file.exists()
    assert (output / "index.html").is_file()
