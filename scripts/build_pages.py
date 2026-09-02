from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "web" / "static"
GENERATED_OUTPUT_ROOT = (ROOT / "dist").resolve()
OUTPUT_MARKER = ".utaipei-credit-audit-pages"
DEFAULT_API_BASE_URL = "https://sapphirejimmy-utaipei-credit-audit.hf.space"


def _validated_api_base_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    parsed = urlparse(cleaned)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Pages API base URL must contain a valid port") from exc
    if (
        cleaned == "*"
        or any(character.isspace() for character in cleaned)
        or "\\" in cleaned
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname == "*"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Pages API base URL must be an HTTPS origin without a path, query, or credentials")
    return cleaned


def build_pages(output_dir: Path, api_base_url: str = DEFAULT_API_BASE_URL, max_upload_mb: int = 8) -> None:
    api_origin = _validated_api_base_url(api_base_url)
    if isinstance(max_upload_mb, bool) or not isinstance(max_upload_mb, int) or not 1 <= max_upload_mb <= 1024:
        raise ValueError("Pages upload limit must be an integer between 1 and 1024 MiB")
    output_dir = output_dir.resolve()
    if output_dir == ROOT:
        raise ValueError("Pages output cannot replace the project root")
    if output_dir.exists():
        is_generated_path = output_dir == GENERATED_OUTPUT_ROOT or GENERATED_OUTPUT_ROOT in output_dir.parents
        has_marker = output_dir.is_dir() and (output_dir / OUTPUT_MARKER).is_file()
        if not (is_generated_path or has_marker):
            raise ValueError("Existing Pages output must be under dist or contain the Pages build marker")
        shutil.rmtree(output_dir)
    (output_dir / "static").mkdir(parents=True)

    for asset in ("app.js", "styles.css"):
        shutil.copy2(STATIC_DIR / asset, output_dir / "static" / asset)

    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    replacements = {
        "{{REMOTE_LOGIN_ENABLED}}": "false",
        "{{MAX_UPLOAD_MB}}": str(max_upload_mb),
        "{{API_BASE_URL}}": api_origin,
    }
    for placeholder, value in replacements.items():
        index = index.replace(placeholder, value)
    if "{{" in index or "}}" in index:
        raise ValueError("Unresolved template placeholder in Pages index")

    (output_dir / "index.html").write_text(index, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    (output_dir / OUTPUT_MARKER).write_text("generated; safe to replace\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages frontend")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "pages")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--max-upload-mb", type=int, default=8)
    args = parser.parse_args()
    build_pages(args.output, args.api_base_url, args.max_upload_mb)


if __name__ == "__main__":
    main()
