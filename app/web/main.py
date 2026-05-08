from __future__ import annotations

import asyncio
import os
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.audit import audit_all
from app.models import AuditRequest, CourseRecord
from app.parsers.selection import parse_selection_html
from app.parsers.transcript import parse_transcript_pdf
from app.scraper.utaipei import ConnectivityBlockedError, HumanVerificationRequired, ScraperError, check_connectivity, scrape_readonly
from app.web.security import RedactingFilter

import logging
import tempfile
from pathlib import Path


logging.getLogger().addFilter(RedactingFilter())

MAX_BROWSER_CONCURRENCY = int(os.getenv("MAX_BROWSER_CONCURRENCY", "1"))
QUEUE_TIMEOUT_SECONDS = float(os.getenv("REQUEST_QUEUE_TIMEOUT_SECONDS", "30"))
BASE_URL = os.getenv("UTAIPEI_BASE_URL", "https://my.utaipei.edu.tw/")

browser_semaphore = asyncio.Semaphore(MAX_BROWSER_CONCURRENCY)
app = FastAPI(title="UTaipei Credit Audit")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logging.exception("Unhandled application error")
    return JSONResponse(status_code=500, content={"detail": "系統發生錯誤，敏感資訊已遮蔽。請改用手動上傳模式或稍後再試。"})


@app.get("/health")
async def health():
    return {"ok": True, "max_browser_concurrency": MAX_BROWSER_CONCURRENCY}


@app.get("/connectivity")
async def connectivity():
    try:
        await check_connectivity(BASE_URL)
        return {"ok": True}
    except ConnectivityBlockedError as exc:
        return JSONResponse(status_code=503, content={"ok": False, "detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/audit/login")
async def audit_login(
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    include_chem_double_major: Annotated[bool, Form()] = True,
    include_cs_double_major: Annotated[bool, Form()] = True,
    include_cs_minor: Annotated[bool, Form()] = False,
    earth_bio_domain: Annotated[str, Form()] = "earth_environment",
):
    try:
        await asyncio.wait_for(browser_semaphore.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail="目前查詢排隊人數過多，請稍後再試。") from exc
    try:
        scrape_result = await scrape_readonly(username, password, BASE_URL)
    except ConnectivityBlockedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HumanVerificationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScraperError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        browser_semaphore.release()

    courses = [*scrape_result.transcript_courses, *scrape_result.selection_courses]
    request = AuditRequest(
        include_chem_double_major=include_chem_double_major,
        include_cs_double_major=include_cs_double_major,
        include_cs_minor=include_cs_minor,
        earth_bio_domain=earth_bio_domain,
    )
    return {"results": [result.model_dump() for result in audit_all(courses, request)]}


@app.post("/audit/upload")
async def audit_upload(
    transcript_pdf: Annotated[UploadFile | None, File()] = None,
    selection_html: Annotated[UploadFile | None, File()] = None,
    selection_html_text: Annotated[str, Form()] = "",
    include_chem_double_major: Annotated[bool, Form()] = True,
    include_cs_double_major: Annotated[bool, Form()] = True,
    include_cs_minor: Annotated[bool, Form()] = False,
    earth_bio_domain: Annotated[str, Form()] = "earth_environment",
):
    courses: list[CourseRecord] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        if transcript_pdf and transcript_pdf.filename:
            path = Path(tmpdir) / "transcript.pdf"
            path.write_bytes(await transcript_pdf.read())
            courses.extend(parse_transcript_pdf(path))
        if selection_html and selection_html.filename:
            html = (await selection_html.read()).decode("utf-8", errors="ignore")
            courses.extend(parse_selection_html(html))
        if selection_html_text.strip():
            courses.extend(parse_selection_html(selection_html_text))
    request = AuditRequest(
        include_chem_double_major=include_chem_double_major,
        include_cs_double_major=include_cs_double_major,
        include_cs_minor=include_cs_minor,
        earth_bio_domain=earth_bio_domain,
    )
    return {"results": [result.model_dump() for result in audit_all(courses, request)]}


HTML = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UTaipei Credit Audit</title>
  <style>
    body { font-family: system-ui, "Noto Sans TC", sans-serif; margin: 0; background: #f6f7f9; color: #17202a; }
    main { max-width: 1040px; margin: 0 auto; padding: 28px; }
    section { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 20px; margin: 16px 0; }
    label { display: block; margin: 10px 0 4px; font-weight: 600; }
    input, select, textarea, button { font: inherit; }
    input, select, textarea { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #b8c0cc; border-radius: 6px; }
    textarea { min-height: 120px; }
    button { padding: 10px 14px; border: 0; border-radius: 6px; background: #105f7a; color: white; cursor: pointer; margin-top: 12px; }
    .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .checks label { font-weight: 400; display: flex; gap: 8px; align-items: center; }
    .checks input { width: auto; }
    pre { white-space: pre-wrap; background: #101820; color: #f4f7fb; padding: 16px; border-radius: 8px; overflow: auto; }
  </style>
</head>
<body>
<main>
  <h1>臺北市立大學學分審核</h1>
  <section>
    <h2>校務系統唯讀查詢</h2>
    <form id="loginForm">
      <div class="row">
        <div><label>帳號</label><input name="username" autocomplete="username" required></div>
        <div><label>密碼</label><input name="password" type="password" autocomplete="current-password" required></div>
      </div>
      <label>地生系專業領域</label>
      <select name="earth_bio_domain">
        <option value="earth_environment">地球環境</option>
        <option value="life_science">生命科學</option>
      </select>
      <div class="checks">
        <label><input type="checkbox" name="include_chem_double_major" checked> 物化系應用化學組雙主修</label>
        <label><input type="checkbox" name="include_cs_double_major" checked> 資訊科學系雙主修</label>
        <label><input type="checkbox" name="include_cs_minor"> 資訊科學系輔系</label>
      </div>
      <button>查詢並審核</button>
    </form>
  </section>
  <section>
    <h2>Fallback 手動上傳</h2>
    <form id="uploadForm">
      <label>歷年成績單 PDF</label><input type="file" name="transcript_pdf" accept="application/pdf">
      <label>選課結果 HTML</label><input type="file" name="selection_html" accept=".html,text/html">
      <label>或貼上選課結果 HTML</label><textarea name="selection_html_text"></textarea>
      <label>地生系專業領域</label>
      <select name="earth_bio_domain">
        <option value="earth_environment">地球環境</option>
        <option value="life_science">生命科學</option>
      </select>
      <div class="checks">
        <label><input type="checkbox" name="include_chem_double_major" checked> 物化系應用化學組雙主修</label>
        <label><input type="checkbox" name="include_cs_double_major" checked> 資訊科學系雙主修</label>
        <label><input type="checkbox" name="include_cs_minor"> 資訊科學系輔系</label>
      </div>
      <button>上傳並審核</button>
    </form>
  </section>
  <section>
    <h2>結果</h2>
    <pre id="output">尚未查詢</pre>
  </section>
</main>
<script>
async function submitForm(form, url) {
  const output = document.querySelector("#output");
  output.textContent = "處理中...";
  const data = new FormData(form);
  for (const name of ["include_chem_double_major", "include_cs_double_major", "include_cs_minor"]) {
    if (!data.has(name)) data.set(name, "false");
  }
  const res = await fetch(url, { method: "POST", body: data });
  const json = await res.json();
  output.textContent = JSON.stringify(json, null, 2);
}
document.querySelector("#loginForm").addEventListener("submit", event => {
  event.preventDefault(); submitForm(event.currentTarget, "/audit/login");
});
document.querySelector("#uploadForm").addEventListener("submit", event => {
  event.preventDefault(); submitForm(event.currentTarget, "/audit/upload");
});
</script>
</body>
</html>
"""
