from __future__ import annotations

import logging
from io import BytesIO

from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


class ComplaintEmailPdfService:
    # HTML → PDF (xhtml2pdf)

    @staticmethod
    async def html_to_pdf(html: str) -> bytes:
        return await run_in_threadpool(ComplaintEmailPdfService._render_sync, html)

    @staticmethod
    def _render_sync(html: str) -> bytes:
        try:
            from xhtml2pdf import pisa
        except ImportError as exc:
            raise RuntimeError(
                "xhtml2pdf 패키지가 필요합니다. requirements.txt에 xhtml2pdf를 추가하세요.",
            ) from exc

        source = (html or "").strip()
        if not source:
            raise ValueError("PDF로 변환할 HTML이 비어 있습니다.")

        buffer = BytesIO()
        result = pisa.CreatePDF(src=source, dest=buffer, encoding="utf-8")
        if result.err:
            raise RuntimeError(f"HTML→PDF 변환 실패 (err={result.err})")
        pdf_bytes = buffer.getvalue()
        if not pdf_bytes:
            raise RuntimeError("PDF 출력이 비어 있습니다.")
        return pdf_bytes
