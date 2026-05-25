from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Playwright

logger = logging.getLogger(__name__)

_TEMPLATE_BASE = Path(__file__).resolve().parent.parent / "templates"
_CHROMIUM_LAUNCH_ARGS = ("--no-sandbox", "--disable-setuid-sandbox")
_playwright_lock = threading.Lock()
_playwright: Playwright | None = None
_browser: Browser | None = None

# Linux 서버, EB 기본 탐색 경로 (Windows는 PDF_KOREAN_FONT_PATHS 로 지정)
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
    # HTML을 PDF로 (WeasyPrint 우선, 실패 시 Playwright — HTML을 문자열로 찍지 않음)

    @staticmethod
    def start_playwright_browser() -> None:
        with _playwright_lock:
            ComplaintEmailPdfService._start_playwright_browser_unlocked()

    @staticmethod
    def stop_playwright_browser() -> None:
        with _playwright_lock:
            ComplaintEmailPdfService._shutdown_playwright_unlocked()

    @staticmethod
    def _start_playwright_browser_unlocked() -> None:
        global _playwright, _browser
        if _browser is not None and _browser.is_connected():
            return
        ComplaintEmailPdfService._shutdown_playwright_unlocked()
        from playwright.sync_api import sync_playwright

        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=list(_CHROMIUM_LAUNCH_ARGS),
        )
        logger.info("Playwright Chromium started (PDF fallback)")

    @staticmethod
    def _shutdown_playwright_unlocked() -> None:
        global _playwright, _browser
        if _browser is not None:
            try:
                _browser.close()
            except Exception:
                logger.debug("Playwright browser close failed", exc_info=True)
            _browser = None
        if _playwright is not None:
            try:
                _playwright.stop()
            except Exception:
                logger.debug("Playwright stop failed", exc_info=True)
            _playwright = None

    @staticmethod
    def _ensure_playwright_browser_unlocked() -> Browser:
        if _browser is not None and _browser.is_connected():
            return _browser
        ComplaintEmailPdfService._start_playwright_browser_unlocked()
        if _browser is None:
            raise RuntimeError("Playwright Chromium을 시작할 수 없습니다.")
        return _browser

    @staticmethod
    async def html_to_pdf(html: str) -> bytes:
        try:
            return await run_in_threadpool(ComplaintEmailPdfService._render_weasyprint, html)
        except Exception:
            logger.exception("WeasyPrint PDF 실패 — Playwright fallback")
            return await run_in_threadpool(ComplaintEmailPdfService._render_playwright, html)

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
    def _render_playwright(html: str) -> bytes:
        source = ComplaintEmailPdfService._prepare_html(html)
        if not source:
            raise ValueError("PDF로 변환할 HTML이 비어 있습니다.")

        with _playwright_lock:
            browser = ComplaintEmailPdfService._ensure_playwright_browser_unlocked()
            page = browser.new_page()
            try:
                page.set_content(source, wait_until="load")
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "18mm", "right": "20mm", "bottom": "18mm", "left": "20mm"},
                )
            finally:
                page.close()

        if not pdf_bytes:
            raise RuntimeError("Playwright PDF 출력이 비어 있습니다.")
        return pdf_bytes

    @staticmethod
    def _korean_font_face_css() -> str:
        for font_path in _korean_font_candidates():
            if not font_path.is_file():
                continue
            uri = font_path.resolve().as_uri()
            logger.info("PDF Korean font: %s", font_path)
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
