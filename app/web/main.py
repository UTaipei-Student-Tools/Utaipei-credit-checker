from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.audit import audit_all
from app.models import AuditRequest, DataQuality, EarthBioDomain, ParseDiagnostic
from app.parsers.selection import parse_selection_html_with_diagnostics
from app.parsers.transcript import parse_transcript_pdf_with_diagnostics
from app.scraper.utaipei import (
    ConnectivityBlockedError,
    HumanVerificationRequired,
    ScraperError,
    check_connectivity,
    scrape_readonly,
)
from app.web.security import install_log_redaction

install_log_redaction()


def _validated_github_pages_origin(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return ""

    parsed = urlparse(cleaned)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("GITHUB_PAGES_ORIGIN must contain a valid port") from exc

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
        raise ValueError("GITHUB_PAGES_ORIGIN must be an HTTPS origin without a path, query, or credentials")
    return cleaned

MAX_BROWSER_CONCURRENCY = max(1, int(os.getenv("MAX_BROWSER_CONCURRENCY", "1")))
QUEUE_TIMEOUT_SECONDS = max(1.0, float(os.getenv("REQUEST_QUEUE_TIMEOUT_SECONDS", "30")))
SCRAPER_TIMEOUT_SECONDS = max(10.0, float(os.getenv("SCRAPER_TIMEOUT_SECONDS", "60")))
MAX_UPLOAD_BYTES = max(1024, int(os.getenv("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024))))
MAX_HTML_TEXT_CHARS = max(1000, int(os.getenv("MAX_HTML_TEXT_CHARS", "2000000")))
BASE_URL = os.getenv("UTAIPEI_BASE_URL", "https://my.utaipei.edu.tw/")
ENABLE_REMOTE_LOGIN = os.getenv("ENABLE_REMOTE_LOGIN", "false").casefold() in {"1", "true", "yes", "on"}
GITHUB_PAGES_ORIGIN = _validated_github_pages_origin(
    os.getenv("GITHUB_PAGES_ORIGIN", "https://jimmymochi.github.io")
)

STATIC_DIR = Path(__file__).with_name("static")
INDEX_TEMPLATE = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

browser_semaphore = asyncio.Semaphore(MAX_BROWSER_CONCURRENCY)
app = FastAPI(title="UTaipei Credit Audit", docs_url=None, redoc_url=None)
if GITHUB_PAGES_ORIGIN:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[GITHUB_PAGES_ORIGIN],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; form-action 'self'; "
        "img-src 'self' data:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'self' https://huggingface.co https://*.huggingface.co https://hf.co"
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logging.error("Unhandled application error type=%s", type(exc).__name__)
    response = JSONResponse(
        status_code=500,
        content={"detail": "系統發生錯誤，敏感資訊已遮蔽。請改用手動上傳模式或稍後再試。"},
    )
    if GITHUB_PAGES_ORIGIN and request.headers.get("origin") == GITHUB_PAGES_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = GITHUB_PAGES_ORIGIN
        response.headers["Vary"] = "Origin"
    return response


@app.get("/health")
async def health():
    return {
        "ok": True,
        "max_browser_concurrency": MAX_BROWSER_CONCURRENCY,
        "remote_login_enabled": ENABLE_REMOTE_LOGIN,
        "supported_admission_years": [114],
    }


@app.get("/connectivity")
async def connectivity():
    if not ENABLE_REMOTE_LOGIN:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "此部署未啟用遠端帳密登入。"})
    try:
        await check_connectivity(BASE_URL)
        return {"ok": True}
    except ConnectivityBlockedError as exc:
        return JSONResponse(status_code=503, content={"ok": False, "detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def index():
    return (
        INDEX_TEMPLATE.replace("{{REMOTE_LOGIN_ENABLED}}", str(ENABLE_REMOTE_LOGIN).lower())
        .replace("{{MAX_UPLOAD_MB}}", f"{MAX_UPLOAD_BYTES / 1024 / 1024:.0f}")
        .replace("{{API_BASE_URL}}", "")
    )


def _overall_quality(diagnostics: list[ParseDiagnostic]) -> DataQuality:
    if any(item.quality == DataQuality.FAILED for item in diagnostics):
        return DataQuality.FAILED
    if any(item.quality == DataQuality.PARTIAL for item in diagnostics):
        return DataQuality.PARTIAL
    return DataQuality.COMPLETE


def _public_course(course: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in course.items() if key != "raw"}


def _public_diagnostic(diagnostic: ParseDiagnostic) -> dict[str, Any]:
    return diagnostic.model_dump(mode="json", exclude={"unparsed_samples"})


def _public_audit_result(result) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    for requirement in payload["requirements"]:
        requirement["matched_courses"] = [_public_course(course) for course in requirement["matched_courses"]]
    for key in ("in_progress", "needs_review", "excluded"):
        payload[key] = [_public_course(course) for course in payload[key]]
    return payload


def _response_payload(courses, diagnostics: list[ParseDiagnostic], request: AuditRequest) -> dict[str, Any]:
    if not courses:
        raise HTTPException(status_code=422, detail="沒有可供審核的課程資料，已停止產生可能誤導的結果。")
    quality = _overall_quality(diagnostics)
    if quality == DataQuality.FAILED:
        raise HTTPException(status_code=422, detail="至少一項輸入解析失敗，已停止學分審核。")
    return {
        "data_quality": quality.value,
        "diagnostics": [_public_diagnostic(item) for item in diagnostics],
        "results": [_public_audit_result(result) for result in audit_all(courses, request)],
        "disclaimer": "本結果為預估；正式畢業、雙主修、輔系及兼充認定以教務處與系所審核為準。",
    }


async def _read_limited_upload(upload: UploadFile, *, expected: str) -> bytes:
    payload = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{expected} 超過 {MAX_UPLOAD_BYTES // 1024 // 1024} MB 上限。")
    if not payload:
        raise HTTPException(status_code=422, detail=f"{expected} 是空檔案。")
    return payload


def _audit_request(
    admission_year: int,
    earth_bio_domain: EarthBioDomain,
    include_chem_double_major: bool,
    include_cs_double_major: bool,
    include_cs_minor: bool,
) -> AuditRequest:
    return AuditRequest(
        admission_year=admission_year,
        earth_bio_domain=earth_bio_domain,
        include_chem_double_major=include_chem_double_major,
        include_cs_double_major=include_cs_double_major,
        include_cs_minor=include_cs_minor,
    )


@app.post("/audit/login")
async def audit_login(
    username: Annotated[str, Form(min_length=1, max_length=128)],
    password: Annotated[str, Form(min_length=1, max_length=256)],
    admission_year: Annotated[int, Form()] = 114,
    include_chem_double_major: Annotated[bool, Form()] = False,
    include_cs_double_major: Annotated[bool, Form()] = False,
    include_cs_minor: Annotated[bool, Form()] = False,
    earth_bio_domain: Annotated[EarthBioDomain, Form()] = EarthBioDomain.EARTH_ENVIRONMENT,
):
    if not ENABLE_REMOTE_LOGIN:
        raise HTTPException(status_code=403, detail="此部署未啟用遠端帳密登入，請使用手動上傳。")
    try:
        await asyncio.wait_for(browser_semaphore.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail="目前查詢排隊人數過多，請稍後再試。") from exc
    try:
        scrape_result = await asyncio.wait_for(
            scrape_readonly(username, password, BASE_URL),
            timeout=SCRAPER_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="完整查詢作業逾時，請改用手動上傳模式。") from exc
    except ConnectivityBlockedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HumanVerificationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScraperError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        browser_semaphore.release()

    courses = [*scrape_result.transcript_courses, *scrape_result.selection_courses]
    request = _audit_request(
        admission_year,
        earth_bio_domain,
        include_chem_double_major,
        include_cs_double_major,
        include_cs_minor,
    )
    return _response_payload(courses, scrape_result.diagnostics, request)


@app.post("/audit/upload")
async def audit_upload(
    transcript_pdf: Annotated[UploadFile | None, File()] = None,
    selection_html: Annotated[UploadFile | None, File()] = None,
    selection_html_text: Annotated[str, Form()] = "",
    admission_year: Annotated[int, Form()] = 114,
    include_chem_double_major: Annotated[bool, Form()] = False,
    include_cs_double_major: Annotated[bool, Form()] = False,
    include_cs_minor: Annotated[bool, Form()] = False,
    earth_bio_domain: Annotated[EarthBioDomain, Form()] = EarthBioDomain.EARTH_ENVIRONMENT,
):
    if not any(
        (
            transcript_pdf and transcript_pdf.filename,
            selection_html and selection_html.filename,
            selection_html_text.strip(),
        )
    ):
        raise HTTPException(status_code=422, detail="請至少提供歷年成績單 PDF 或選課結果 HTML。")
    if len(selection_html_text) > MAX_HTML_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="貼上的 HTML 內容過大。")

    courses = []
    diagnostics: list[ParseDiagnostic] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        if transcript_pdf and transcript_pdf.filename:
            if not transcript_pdf.filename.casefold().endswith(".pdf"):
                raise HTTPException(status_code=415, detail="歷年成績單必須是 PDF。")
            payload = await _read_limited_upload(transcript_pdf, expected="歷年成績單")
            if not payload.startswith(b"%PDF-"):
                raise HTTPException(status_code=415, detail="歷年成績單的 PDF 檔頭無效。")
            path = Path(tmpdir) / "transcript.pdf"
            path.write_bytes(payload)
            parsed = parse_transcript_pdf_with_diagnostics(path)
            courses.extend(parsed.courses)
            diagnostics.append(parsed.diagnostic)

        if selection_html and selection_html.filename:
            if not selection_html.filename.casefold().endswith((".html", ".htm")):
                raise HTTPException(status_code=415, detail="選課結果檔案必須是 HTML。")
            payload = await _read_limited_upload(selection_html, expected="選課結果 HTML")
            parsed = parse_selection_html_with_diagnostics(payload.decode("utf-8", errors="replace"))
            courses.extend(parsed.courses)
            diagnostics.append(parsed.diagnostic)

        if selection_html_text.strip():
            parsed = parse_selection_html_with_diagnostics(selection_html_text)
            courses.extend(parsed.courses)
            diagnostics.append(parsed.diagnostic.model_copy(update={"source": "selection_html_text"}))

    request = _audit_request(
        admission_year,
        earth_bio_domain,
        include_chem_double_major,
        include_cs_double_major,
        include_cs_minor,
    )
    return _response_payload(courses, diagnostics, request)
