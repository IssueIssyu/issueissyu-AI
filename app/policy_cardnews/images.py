# 정책 카드뉴스 원문·커버 이미지 다운로드

from __future__ import annotations

import logging
from io import BytesIO

import httpx
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


async def download_cardnews_image(
    url: str,
    *,
    timeout: float = 20.0,
    referer: str = "",
) -> Image.Image | None:
    if not url.startswith(("http://", "https://")):
        return None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as img:
                return img.convert("RGBA")
    except (httpx.HTTPError, UnidentifiedImageError, OSError):
        logger.warning("카드뉴스 배경 이미지 다운로드 실패: %s", url)
        return None


async def download_cardnews_images(
    urls: list[str],
    *,
    timeout: float = 20.0,
    referer: str = "",
) -> list[Image.Image]:
    import asyncio

    unique_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        url = (url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)

    if not unique_urls:
        return []

    tasks = [
        download_cardnews_image(url, timeout=timeout, referer=referer) for url in unique_urls
    ]
    results = await asyncio.gather(*tasks)
    return [img for img in results if img is not None]
