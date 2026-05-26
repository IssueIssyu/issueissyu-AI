from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from mimetypes import guess_type
from pathlib import Path
from typing import Any, Sequence

from fastapi import UploadFile
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from PIL import Image, UnidentifiedImageError

from app.schemas.ComplaintEmailDTO import ComplaintEmailLlmBundle
from app.schemas.IssueDTO import ImageWithLocation

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
logger = logging.getLogger(__name__)

_FORBIDDEN_PHRASES = ("서울시", "서울 특별시", "서울특별시", "www.wowform.com")
_ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"})


@dataclass(frozen=True, slots=True)
class OpinionAttachmentImage:
    data_uri: str
    caption: str


def nl2br(value: str | None) -> Markup:
    if not value:
        return Markup("&nbsp;")

    text = str(value)
    text = text.replace("\\r\\n", "\n")
    text = text.replace("\\n", "\n")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = _strip_forbidden_phrases(text)

    if not text.strip():
        return Markup("&nbsp;")

    return Markup("<br/>".join(escape(line) for line in text.split("\n")))


class ComplaintEmailOpinionRenderer:
    # 행정절차법 의견제출서 양식(의견제출서양식, hwp)과 동일한 HTML 레이아웃

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        )
        self._env.filters["nl2br"] = nl2br

    def render(
        self,
        bundle: ComplaintEmailLlmBundle,
        sections: dict[str, Any],
        *,
        attachment_images: Sequence[OpinionAttachmentImage] | None = None,
    ) -> str:
        template = self._env.get_template("complaint_opinion_form.html.j2")
        today = date.today()
        written = f"{today.year}년 {today.month:02d}월 {today.day:02d}일"
        return template.render(
            disposition_title=_normalize_plain_text(
                sections.get("disposition_title") or bundle.pin_title,
            ),
            opinion=_normalize_plain_text(sections.get("opinion", "")),
            other=_normalize_plain_text(sections.get("other", "")),
            attachment_images=list(attachment_images or ()),
            submitter_name=_normalize_plain_text(sections.get("submitter_name", "")),
            submitter_address=_normalize_plain_text(sections.get("submitter_address", "")),
            submitter_address_footer=_normalize_plain_text(
                sections.get("submitter_address", ""),
            ),
            submitter_phone=_normalize_plain_text(sections.get("submitter_phone", "")),
            submitter_name_footer=_normalize_plain_text(sections.get("submitter_name", "")),
            written_date=written,
        )

    @staticmethod
    async def encode_attachment_images(
        images: Sequence[ImageWithLocation],
    ) -> list[OpinionAttachmentImage]:
        encoded: list[OpinionAttachmentImage] = []
        for idx, row in enumerate(images, start=1):
            upload = row.image
            if upload is None:
                continue
            await upload.seek(0)
            raw = await upload.read()
            await upload.seek(0)
            if not raw:
                continue
            prepared = _prepare_attachment_bytes(raw, upload)
            if prepared is None:
                continue
            raw, mime = prepared
            data_uri = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            caption = (row.address or "").strip() or f"첨부 사진 {idx}"
            encoded.append(OpinionAttachmentImage(data_uri=data_uri, caption=caption))
        return encoded

    @staticmethod
    def parse_sections_json(raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("의견서 JSON이 객체가 아닙니다.")
        return data


def _resolve_upload_mime(upload: UploadFile) -> str:
    mime = (upload.content_type or "").split(";", 1)[0].strip().lower()
    if not mime or mime == "application/octet-stream":
        guessed, _ = guess_type(upload.filename or "")
        mime = (guessed or "").lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    return mime


def _prepare_attachment_bytes(raw: bytes, upload: UploadFile) -> tuple[bytes, str] | None:
    mime = _resolve_upload_mime(upload)
    if mime in _ALLOWED_IMAGE_MIMES:
        return raw, mime

    converted = _convert_image_to_jpeg_bytes(raw)
    if converted is not None:
        logger.info(
            "PDF 첨부 이미지를 JPEG로 변환했습니다 (filename=%s, declared_mime=%s)",
            upload.filename,
            mime or "(unknown)",
        )
        return converted, "image/jpeg"

    logger.warning(
        "PDF 첨부 이미지를 건너뜁니다: 지원하지 않거나 디코드할 수 없습니다 "
        "(filename=%s, mime=%s)",
        upload.filename,
        mime or "(unknown)",
    )
    return None


def _convert_image_to_jpeg_bytes(raw: bytes) -> bytes | None:
    try:
        with Image.open(BytesIO(raw)) as img:
            rgb = img.convert("RGB") if img.mode != "RGB" else img
            buf = BytesIO()
            rgb.save(buf, format="JPEG", quality=85, optimize=True)
            return buf.getvalue()
    except (UnidentifiedImageError, OSError):
        logger.debug("PDF 첨부 이미지 JPEG 변환 실패", exc_info=True)
        return None


def _strip_forbidden_phrases(text: str) -> str:
    cleaned = text
    for phrase in _FORBIDDEN_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    return cleaned


def _normalize_plain_text(text: str) -> str:
    normalized = str(text or "")
    normalized = re.sub(r'\\+(?:r\\n|[rn])', '\n', normalized)
    normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
    return _strip_forbidden_phrases(normalized)
