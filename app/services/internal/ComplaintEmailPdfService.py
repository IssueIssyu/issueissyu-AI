from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright

logger = logging.getLogger(__name__)

_TEMPLATE_BASE = Path(__file__).resolve().parent.parent / "templates"
_CHROMIUM_LAUNCH_ARGS = ("--no-sandbox", "--disable-setuid-sandbox", "--allow-file-access-from-files")
_playwright: Playwright | None = None
_browser: Browser | None = None
_pw_lock = asyncio.Lock()

_DEFAULT_KOREAN_FONT_CANDIDATES: tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf"),
)
_MACOS_BREW_LIB_PATH = Path("/opt/homebrew/lib")


def _korean_font_candidates() -> tuple[Path, ...]:
    configured = get_settings().pdf_korean_font_path_list
    if configured:
        return tuple(configured) + _DEFAULT_KOREAN_FONT_CANDIDATES
    return _DEFAULT_KOREAN_FONT_CANDIDATES


class ComplaintEmailPdfService:

    @staticmethod
    async def start_playwright_browser() -> None:
        async with _pw_lock:
            await ComplaintEmailPdfService._start_playwright_unlocked()

    @staticmethod
    async def stop_playwright_browser() -> None:
        async with _pw_lock:
            await ComplaintEmailPdfService._shutdown_playwright_unlocked()

    @staticmethod
    async def _start_playwright_unlocked() -> None:
        global _playwright, _browser
        if _browser is not None and _browser.is_connected():
            return
        await ComplaintEmailPdfService._shutdown_playwright_unlocked()
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=list(_CHROMIUM_LAUNCH_ARGS),
        )
        logger.info("Playwright Chromium started (PDF fallback, async_api)")

    @staticmethod
    async def _shutdown_playwright_unlocked() -> None:
        global _playwright, _browser
        if _browser is not None:
            try:
                await _browser.close()
            except Exception:
                logger.debug("Playwright browser close failed", exc_info=True)
            _browser = None
        if _playwright is not None:
            try:
                await _playwright.stop()
            except Exception:
                logger.debug("Playwright stop failed", exc_info=True)
            _playwright = None

    @staticmethod
    async def _ensure_browser() -> Browser:
        if _browser is not None and _browser.is_connected():
            return _browser
        async with _pw_lock:
            if _browser is not None and _browser.is_connected():
                return _browser
            await ComplaintEmailPdfService._start_playwright_unlocked()
        if _browser is None:
            raise RuntimeError("Playwright Chromium을 시작할 수 없습니다.")
        return _browser

    @staticmethod
    async def html_to_pdf(html: str) -> bytes:
        try:
            return await run_in_threadpool(ComplaintEmailPdfService._render_weasyprint, html)
        except Exception:
            logger.exception("WeasyPrint PDF 실패 — Playwright fallback")
            return await ComplaintEmailPdfService._render_playwright(html)

    @staticmethod
    def _prepare_html(html: str) -> str:
        text = (html or "").strip()
        if not text:
            return ""
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
        font_css = ComplaintEmailPdfService._korean_font_face_css()
        if font_css and "@font-face" not in text:
            text = text.replace("</head>", f"{font_css}</head>", 1)
        return text

    @staticmethod
    def _render_weasyprint(html: str) -> bytes:
        ComplaintEmailPdfService._configure_macos_weasyprint_library_path()
        from weasyprint import HTML

        source = ComplaintEmailPdfService._prepare_html(html)
        if not source:
            raise ValueError("PDF로 변환할 HTML이 비어 있습니다.")

        pdf_bytes = HTML(string=source, base_url=str(_TEMPLATE_BASE)).write_pdf()
        if not pdf_bytes:
            raise RuntimeError("WeasyPrint PDF 출력이 비어 있습니다.")
        return pdf_bytes

    @staticmethod
    def _configure_macos_weasyprint_library_path() -> None:
        if sys.platform != "darwin":
            return
        if not _MACOS_BREW_LIB_PATH.is_dir():
            return

        current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        parts = [p for p in current.split(":") if p]
        brew_path = str(_MACOS_BREW_LIB_PATH)
        if brew_path in parts:
            return
        parts.insert(0, brew_path)
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)

    @staticmethod
    async def _render_playwright(html: str) -> bytes:
        source = ComplaintEmailPdfService._prepare_html(html)
        if not source:
            raise ValueError("PDF로 변환할 HTML이 비어 있습니다.")

        browser = await ComplaintEmailPdfService._ensure_browser()
        page = await browser.new_page()
        try:
            await page.set_content(source, wait_until="load")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "18mm", "right": "20mm", "bottom": "18mm", "left": "20mm"},
            )
        finally:
            await page.close()

        if not pdf_bytes:
            raise RuntimeError("Playwright PDF 출력이 비어 있습니다.")
        return pdf_bytes

    @staticmethod
    def _korean_font_face_css() -> str:
        for font_path in _korean_font_candidates():
            if not font_path.is_file():
                continue
            uri = font_path.resolve().as_uri()
            logger.debug("PDF Korean font: %s", font_path)
            return f"""
                <style>
                @font-face {{
                  font-family: 'KoreanBody';
                  src: url('{uri}');
                }}
                body {{
                    font-family: 'KoreanBody', "Malgun Gothic", "Batang", sans-serif;
                }}
                </style>
            """
        return ""
