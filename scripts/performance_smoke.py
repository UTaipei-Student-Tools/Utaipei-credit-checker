"""Privacy-safe concurrent browser timing for the Streamlit application.

This is an acceptance probe, not a synthetic HTTP benchmark: every sample is
an isolated browser context with its own Streamlit WebSocket/session.  It never
uploads a transcript, accepts credentials, records a trace, takes screenshots,
or returns page text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from collections.abc import Sequence
from urllib.parse import urlsplit, urlunsplit


def _safe_url(value: str) -> str:
    """Allow only a credential-free HTTP(S) URL with no query or fragment."""

    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("performance target must be an HTTP(S) origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("performance target cannot contain credentials, query, or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def _percentile(samples: Sequence[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in samples)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summarize(samples: Sequence[float]) -> dict[str, float | int]:
    """Return aggregate timings only; individual navigation data is discarded."""

    values = [float(value) for value in samples]
    if not values:
        return {"count": 0, "min_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(values),
        "min_ms": round(min(values), 1),
        "p50_ms": round(_percentile(values, 0.5), 1),
        "p95_ms": round(_percentile(values, 0.95), 1),
        "max_ms": round(max(values), 1),
    }


async def _probe_session(browser, url: str, *, timeout_ms: int) -> float:
    context = await browser.new_context(
        viewport={"width": 390, "height": 844},
        color_scheme="light",
        service_workers="block",
    )
    page = await context.new_page()
    started = time.perf_counter()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.locator('[data-testid="stMainMenuButton"]').wait_for(state="visible", timeout=timeout_ms)
        await page.locator('[data-testid="stSelectbox"] input[role="combobox"]').first.wait_for(
            state="visible", timeout=timeout_ms
        )
        state = await page.evaluate(
            """() => {
              const text = document.body.innerText.toLowerCase();
              return {
                horizontalOverflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
                  > window.innerWidth + 1,
                rawMarkup: ['<style>', '--ui-canvas', '<header class='].some(token => text.includes(token)),
              };
            }"""
        )
        if state["horizontalOverflow"] or state["rawMarkup"]:
            raise RuntimeError("render acceptance failed")
        return round((time.perf_counter() - started) * 1000, 1)
    finally:
        await context.close()


async def _run(url: str, browser_name: str, sessions: int, timeout_ms: int) -> dict[str, object]:
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as error:  # pragma: no cover - acceptance dependency
        raise RuntimeError("install Playwright and its browser binaries before running this probe") from error

    async with async_playwright() as playwright:
        launcher = getattr(playwright, browser_name)
        browser = await launcher.launch(headless=True)
        try:
            cold_ms = await _probe_session(browser, url, timeout_ms=timeout_ms)
            concurrent = await asyncio.gather(
                *(_probe_session(browser, url, timeout_ms=timeout_ms) for _ in range(sessions))
            )
        finally:
            await browser.close()
    return {
        "schema": "utaipei-performance-smoke.v1",
        "browser": browser_name,
        "target": url,
        "cold_ready_ms": cold_ms,
        "concurrent_sessions": _summarize(concurrent),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8505/")
    parser.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--max-ready-ms", type=float, default=15_000.0)
    args = parser.parse_args()
    if not 1 <= args.sessions <= 12:
        parser.error("--sessions must be between 1 and 12")

    result = asyncio.run(_run(_safe_url(args.url), args.browser, args.sessions, args.timeout_ms))
    maximum = float(result["concurrent_sessions"]["max_ms"])
    result["threshold_ms"] = args.max_ready_ms
    result["within_threshold"] = maximum <= args.max_ready_ms
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    if not result["within_threshold"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
