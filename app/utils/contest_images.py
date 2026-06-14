from __future__ import annotations

from typing import Any

from rag.scripts.fetch_visitkorea import normalize_pin_images_for_db

ATTACHMENT_PREFIX = "https://api.linkareer.com/attachments/"
MEDIA_CDN_MARKER = "media-cdn.linkareer.com"
CONTEST_IMAGE_S3_KEY = "contest"


def _is_attachment_url(url: str) -> bool:
    return url.startswith(ATTACHMENT_PREFIX)


def _is_media_cdn_url(url: str) -> bool:
    return MEDIA_CDN_MARKER in url


def collect_contest_pin_image_specs(image_urls: list[str]) -> list[dict[str, Any]]:
    """attachments 첫 URL만 is_main=True, 이후 attachments 스킵, media-cdn은 전부 is_main=False."""
    specs: list[dict[str, Any]] = []
    main_assigned = False

    for raw in image_urls:
        url = str(raw or "").strip()
        if not url:
            continue
        if _is_attachment_url(url):
            if main_assigned:
                continue
            main_assigned = True
            specs.append({"pin_image_url": url, "is_main": True})
        elif _is_media_cdn_url(url):
            specs.append({"pin_image_url": url, "is_main": False})

    return normalize_pin_images_for_db(specs)


def pin_images_for_db_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw_specs = row.get("pin_images")
    if isinstance(raw_specs, list) and raw_specs:
        return normalize_pin_images_for_db(raw_specs)
    image_urls = [str(url).strip() for url in row.get("image_urls") or [] if str(url).strip()]
    return collect_contest_pin_image_specs(image_urls)
