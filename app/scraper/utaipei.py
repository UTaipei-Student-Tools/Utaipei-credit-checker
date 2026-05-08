from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.parsers.selection import parse_selection_html
from app.parsers.transcript import parse_transcript_pdf


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


async def check_connectivity(base_url: str = "https://my.utaipei.edu.tw/", timeout: float = 8.0) -> None:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(base_url)
        if response.status_code >= 500:
            raise ConnectivityBlockedError("校務系統目前無法連線，請改用手動上傳模式或本地部署/代理。")
    except httpx.HTTPError as exc:
        raise ConnectivityBlockedError("無法從目前環境連到校務系統，請改用手動上傳模式或本地部署/代理。") from exc


async def scrape_readonly(username: str, password: str, base_url: str = "https://my.utaipei.edu.tw/") -> ScrapeResult:
    await check_connectivity(base_url)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
            await (await _find_locator(page, 'input[name="uid"]')).fill(username, timeout=10_000)
            await (await _find_locator(page, 'input[name="pwd"]')).fill(password, timeout=10_000)
            await (await _find_locator(page, 'input[name="chk"]')).click(timeout=10_000)
            await _wait_for_text(page, ("學生歷年成績查詢", "登　　出", "登 出"), timeout_ms=30_000)

            content = await _all_frame_content(page)
            if any(marker.lower() in content.lower() for marker in ("captcha", "驗證碼", "二次驗證", "mfa")):
                raise HumanVerificationRequired("校務系統要求驗證碼或二次驗證，請改用手動上傳模式。")
            if "學生歷年成績查詢" not in content and "登　　出" not in content and "登 出" not in content:
                raise ScraperError("登入失敗或頁面結構變更，請確認帳密或改用手動上傳模式。")

            transcript_courses = await _download_transcript(page, base_url)
            selection_courses = await _read_selection(page)
            return ScrapeResult(transcript_courses, selection_courses)
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
            except Exception as exc:
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
        except Exception:
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
            except Exception:
                continue
        await page.wait_for_timeout(500)
    raise PlaywrightTimeoutError(f"Timed out waiting for menu item {text}")


async def _download_transcript(page, base_url: str) -> list:
    await _click_menu_text(page, "學生歷年成績查詢")
    content = await _all_frame_content(page)
    if "成績確認沒問題" in content:
        # Deliberately do not click this write-like confirmation button.
        pass
    link = await _find_locator(page, 'a[href*="/utaipei/pdf/"]', timeout_ms=20_000)
    href = await link.get_attribute("href", timeout=10_000)
    if not href:
        raise ScraperError("找不到歷年成績單 PDF 連結，請改用手動上傳模式。")

    pdf_url = urljoin(base_url, href)
    cookies = await page.context.cookies()
    cookie_jar = {cookie["name"]: cookie["value"] for cookie in cookies}
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "transcript.pdf"
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, cookies=cookie_jar) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            path.write_bytes(response.content)
        return parse_transcript_pdf(path)


async def _read_selection(page) -> list:
    try:
        await _click_menu_text(page, "選課結果查詢")
        html = await _all_frame_content(page)
        return parse_selection_html(html)
    except Exception:
        return []


def scrape_readonly_sync(username: str, password: str, base_url: str = "https://my.utaipei.edu.tw/") -> ScrapeResult:
    return asyncio.run(scrape_readonly(username, password, base_url))
