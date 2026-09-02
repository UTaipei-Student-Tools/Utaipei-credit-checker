from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.models import DataQuality, ParseDiagnostic
from app.parsers.selection import parse_selection_html_with_diagnostics
from app.parsers.transcript import parse_transcript_pdf_with_diagnostics


class ScraperError(RuntimeError):
    pass


class ConnectivityBlockedError(ScraperError):
    pass


class HumanVerificationRequired(ScraperError):
    pass


@dataclass(frozen=True)
class ScrapeResult:
    transcript_courses: list
    selection_courses: list
    diagnostics: list[ParseDiagnostic] = field(default_factory=list)


async def check_connectivity(base_url: str = "https://my.utaipei.edu.tw/", timeout: float = 8.0) -> None:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(base_url)
        if response.status_code >= 500:
            raise ConnectivityBlockedError("校務系統目前無法連線，請改用手動上傳模式或本地部署。")
    except httpx.HTTPError as exc:
        raise ConnectivityBlockedError("無法從目前環境連到校務系統，請改用手動上傳模式或本地部署。") from exc


async def scrape_readonly(username: str, password: str, base_url: str = "https://my.utaipei.edu.tw/") -> ScrapeResult:
    await check_connectivity(base_url)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(accept_downloads=False)
        page = await context.new_page()
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
            await (await _find_locator(page, 'input[name="uid"]')).fill(username, timeout=10_000)
            await (await _find_locator(page, 'input[name="pwd"]')).fill(password, timeout=10_000)
            await (await _find_locator(page, 'input[name="chk"]')).click(timeout=10_000)
            await _wait_for_text(page, ("學生歷年成績查詢", "登　　出", "登 出"), timeout_ms=30_000)

            content = await _all_frame_content(page)
            if any(marker.casefold() in content.casefold() for marker in ("captcha", "驗證碼", "二次驗證", "mfa")):
                raise HumanVerificationRequired("校務系統要求驗證碼或二次驗證，請改用手動上傳模式。")
            if "學生歷年成績查詢" not in content and "登　　出" not in content and "登 出" not in content:
                raise ScraperError("登入失敗或頁面結構變更，請確認帳密或改用手動上傳模式。")

            transcript = await _download_transcript(page, base_url)
            selection = await _read_selection(page)
            if transcript.diagnostic.quality == DataQuality.FAILED:
                raise ScraperError("歷年成績單解析失敗，為避免錯算已停止審核。")
            if selection.diagnostic.quality == DataQuality.FAILED:
                raise ScraperError("選課結果解析失敗，為避免漏算本學期課程已停止審核。")
            return ScrapeResult(
                transcript_courses=transcript.courses,
                selection_courses=selection.courses,
                diagnostics=[transcript.diagnostic, selection.diagnostic],
            )
        except PlaywrightTimeoutError as exc:
            raise ScraperError("校務系統回應逾時，請稍後重試或改用手動上傳模式。") from exc
        finally:
            await context.close()
            await browser.close()


async def _find_locator(page, selector: str, timeout_ms: int = 15_000):
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    last_error: Exception | None = None
    while asyncio.get_running_loop().time() < deadline:
        for frame in page.frames:
            locator = frame.locator(selector)
            try:
                if await locator.count() > 0:
                    return locator.first
            except Exception as exc:  # pragma: no cover - defensive against detached frames
                last_error = exc
        await page.wait_for_timeout(250)
    if last_error:
        raise PlaywrightTimeoutError(f"Timed out waiting for selector {selector}") from last_error
    raise PlaywrightTimeoutError(f"Timed out waiting for selector {selector}")


async def _all_frame_content(page) -> str:
    chunks: list[str] = []
    for frame in page.frames:
        try:
            chunks.append(await frame.content())
        except Exception:  # pragma: no cover - detached frame race
            continue
    return "\n".join(chunks)


async def _wait_for_text(page, texts: tuple[str, ...], timeout_ms: int = 20_000) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        content = await _all_frame_content(page)
        if any(text in content for text in texts):
            return
        await page.wait_for_timeout(500)
    raise PlaywrightTimeoutError(f"Timed out waiting for any of: {', '.join(texts)}")


async def _click_menu_text(page, text: str) -> None:
    deadline = asyncio.get_running_loop().time() + 20
    while asyncio.get_running_loop().time() < deadline:
        for frame in page.frames:
            locator = frame.get_by_text(text, exact=True)
            try:
                if await locator.count() > 0:
                    await locator.first.click(timeout=10_000)
                    await page.wait_for_timeout(1_500)
                    return
            except Exception:  # pragma: no cover - UI race
                continue
        await page.wait_for_timeout(500)
    raise PlaywrightTimeoutError(f"Timed out waiting for menu item {text}")


def _validate_download_url(base_url: str, target_url: str) -> None:
    base = urlparse(base_url)
    target = urlparse(target_url)
    if target.scheme != "https" or target.hostname != base.hostname:
        raise ScraperError("成績單下載連結不在校務系統網域，已停止下載。")


async def _download_transcript(page, base_url: str):
    await _click_menu_text(page, "學生歷年成績查詢")
    link = await _find_locator(page, 'a[href*="/utaipei/pdf/"]', timeout_ms=20_000)
    href = await link.get_attribute("href", timeout=10_000)
    if not href:
        raise ScraperError("找不到歷年成績單 PDF 連結，請改用手動上傳模式。")

    pdf_url = urljoin(base_url, href)
    _validate_download_url(base_url, pdf_url)
    cookies = await page.context.cookies()
    cookie_jar = {cookie["name"]: cookie["value"] for cookie in cookies}
    max_bytes = int(os.getenv("MAX_TRANSCRIPT_DOWNLOAD_BYTES", str(8 * 1024 * 1024)))

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "transcript.pdf"
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, cookies=cookie_jar) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").casefold()
        payload = response.content
        if "pdf" not in content_type and not payload.startswith(b"%PDF-"):
            raise ScraperError("校務系統回傳的成績單不是 PDF。")
        if len(payload) > max_bytes:
            raise ScraperError("成績單檔案過大，已停止處理。")
        if not payload.startswith(b"%PDF-"):
            raise ScraperError("成績單 PDF 檔頭無效，已停止處理。")
        path.write_bytes(payload)
        return parse_transcript_pdf_with_diagnostics(path)


async def _read_selection(page):
    await _click_menu_text(page, "選課結果查詢")
    html = await _all_frame_content(page)
    return parse_selection_html_with_diagnostics(html)


def scrape_readonly_sync(username: str, password: str, base_url: str = "https://my.utaipei.edu.tw/") -> ScrapeResult:
    return asyncio.run(scrape_readonly(username, password, base_url))
