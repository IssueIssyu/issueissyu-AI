from __future__ import annotations

import logging
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TEMPLATE_BASE = Path(__file__).resolve().parent.parent / "templates"

# Linux 서버, EB 기본 탐색 경로 (Windows는 PDF_KOREAN_FONT_PATHS 로 지정)
_DEFAULT_KOREAN_FONT_CANDIDATES: tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf"),
)


def _korean_font_candidates() -> tuple[Path, ...]:
    configured = get_settings().pdf_korean_font_path_list
    if configured:
        return tuple(configured) + _DEFAULT_KOREAN_FONT_CANDIDATES
    return _DEFAULT_KOREAN_FONT_CANDIDATES


class ComplaintEmailPdfService:
    # HTML을 PDF로 (WeasyPrint 우선, 실패 시 Playwright — HTML을 문자열로 찍지 않음)

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
        from weasyprint import HTML

        source = ComplaintEmailPdfService._prepare_html(html)
        if not source:
            raise ValueError("PDF로 변환할 HTML이 비어 있습니다.")

        pdf_bytes = HTML(string=source, base_url=str(_TEMPLATE_BASE)).write_pdf()
        if not pdf_bytes:
            raise RuntimeError("WeasyPrint PDF 출력이 비어 있습니다.")
        return pdf_bytes

    @staticmethod
    def _render_playwright(html: str) -> bytes:
        from playwright.sync_api import sync_playwright

        source = ComplaintEmailPdfService._prepare_html(html)
        if not source:
            raise ValueError("PDF로 변환할 HTML이 비어 있습니다.")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
            try:
                page = browser.new_page()
                page.set_content(source, wait_until="load")
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "18mm", "right": "20mm", "bottom": "18mm", "left": "20mm"},
                )
            finally:
                browser.close()

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
