from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any
from xml.etree import ElementTree as ET

_POLICY_DATE_FMT = "%m/%d/%Y %H:%M:%S"
_POLICY_DATE_FMT_SHORT = "%m/%d/%Y"
_IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def validate_yyyymmdd(value: str, *, label: str) -> str:
    text = (value or "").strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"{label}는 YYYYMMDD 8자리여야 합니다 (받음: {value!r})")
    return text


def yyyymmdd_to_date(value: str) -> date:
    text = validate_yyyymmdd(value, label="date")
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def date_to_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def iter_date_chunks(
    start: str,
    end: str,
    *,
    max_days: int = 3,
) -> list[tuple[str, str]]:
    # 정책뉴스 API는 조회 기간이 최대 3일(THREE_DAYS_OVER_ERROR)
    start_d = yyyymmdd_to_date(start)
    end_d = yyyymmdd_to_date(end)
    if start_d > end_d:
        raise ValueError("start_date는 end_date보다 이후일 수 없습니다.")

    chunks: list[tuple[str, str]] = []
    cursor = start_d
    while cursor <= end_d:
        chunk_end = min(cursor + timedelta(days=max_days - 1), end_d)
        chunks.append((date_to_yyyymmdd(cursor), date_to_yyyymmdd(chunk_end)))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def strip_html(html: str) -> str:
    if not html:
        return ""
    text = _HTML_TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_image_urls_from_html(html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _IMG_SRC_RE.finditer(html or ""):
        url = match.group(1).strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


_CARDNEWS_GROUPING_KEYWORDS = ("card", "cardnews", "graphic", "infographic", "onecut", "one_cut", "한컷", "카드")


def is_cardnews_grouping(grouping_code: str) -> bool:
    code = (grouping_code or "").strip().lower()
    if not code:
        return False
    return any(keyword in code for keyword in _CARDNEWS_GROUPING_KEYWORDS)


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        url = (raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def classify_policy_images(
    *,
    original_img_url: str | None,
    thumbnail_url: str | None,
    data_contents: str | None,
    grouping_code: str = "",
) -> dict[str, list[str]]:
    original = (original_img_url or "").strip()
    thumbnail = (thumbnail_url or "").strip()
    inline_urls = extract_image_urls_from_html(data_contents or "")

    if is_cardnews_grouping(grouping_code):
        cardnews_candidates = _dedupe_urls([original, *inline_urls])
        original_urls = _dedupe_urls([thumbnail] if thumbnail and thumbnail not in cardnews_candidates else [])
        if not original_urls and thumbnail:
            original_urls = [thumbnail]
        cardnews_urls = [url for url in cardnews_candidates if url not in original_urls]
    else:
        original_urls = _dedupe_urls([original] if original else [])
        if thumbnail and thumbnail not in original_urls:
            original_urls.append(thumbnail)
        cardnews_urls = _dedupe_urls(
            [url for url in inline_urls if url not in original_urls],
        )

    merged = _dedupe_urls([*original_urls, *cardnews_urls])
    return {
        "original_image_urls": original_urls,
        "cardnews_image_urls": cardnews_urls,
        "image_urls": merged,
    }


def collect_image_urls(
    *,
    original_img_url: str | None,
    thumbnail_url: str | None,
    data_contents: str | None,
    grouping_code: str = "",
) -> list[str]:
    return classify_policy_images(
        original_img_url=original_img_url,
        thumbnail_url=thumbnail_url,
        data_contents=data_contents,
        grouping_code=grouping_code,
    )["image_urls"]


def merge_policy_image_urls(
    *,
    original_image_urls: list[str] | None,
    cardnews_image_urls: list[str] | None,
) -> list[str]:
    return _dedupe_urls([*(original_image_urls or []), *(cardnews_image_urls or [])])


def parse_policy_datetime(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in (_POLICY_DATE_FMT, _POLICY_DATE_FMT_SHORT):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def approve_date_to_yyyymmdd(raw: str | None) -> str | None:
    parsed = parse_policy_datetime(raw)
    if parsed is None:
        return None
    return parsed.strftime("%Y%m%d")


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def child_map(parent: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for child in parent:
        key = local_name(child.tag)
        out[key] = element_text(child)
    return out


def policy_result_ok(header: dict[str, str]) -> tuple[bool, str]:
    code = str(header.get("resultCode", "")).strip()
    msg = str(header.get("resultMsg", "")).strip()
    ok = code in {"0", "00"}
    return ok, f"{code} {msg}".strip()


def parse_policy_news_xml(xml_text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    root = ET.fromstring(xml_text)
    header_el = None
    body_el = None
    for child in root:
        name = local_name(child.tag)
        if name == "header":
            header_el = child
        elif name == "body":
            body_el = child

    header = child_map(header_el) if header_el is not None else {}
    items: list[dict[str, str]] = []
    if body_el is not None:
        for child in body_el:
            if local_name(child.tag) != "NewsItem":
                continue
            items.append(child_map(child))
    return header, items


def merge_subtitles(row: dict[str, str]) -> str:
    parts: list[str] = []
    for key in ("SubTitle1", "SubTitle2", "SubTitle3"):
        text = strip_html(row.get(key) or "")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def build_policy_document_row(item: dict[str, str]) -> dict[str, Any] | None:
    news_id = str(item.get("NewsItemId") or "").strip()
    title = strip_html(item.get("Title") or "")
    if not news_id or not title:
        return None

    contents_type = (item.get("ContentsType") or "T").strip().upper()
    raw_contents = (item.get("DataContents") or "").strip()
    if contents_type == "H":
        pin_content = strip_html(raw_contents)
    else:
        pin_content = clean_text(raw_contents)

    approve_yyyymmdd = approve_date_to_yyyymmdd(item.get("ApproveDate"))
    grouping_code = (item.get("GroupingCode") or "").strip()
    images = classify_policy_images(
        original_img_url=item.get("OriginalimgUrl"),
        thumbnail_url=item.get("ThumbnailUrl"),
        data_contents=raw_contents if contents_type == "H" else None,
        grouping_code=grouping_code,
    )

    return {
        "contentid": news_id,
        "pin_title": title,
        "pin_content": pin_content,
        "pin_content_raw": raw_contents,
        "minister": (item.get("MinisterCode") or "").strip(),
        "grouping_code": grouping_code,
        "contents_type": contents_type,
        "approve_date": (item.get("ApproveDate") or "").strip(),
        "event_start_time": approve_yyyymmdd,
        "event_end_time": approve_yyyymmdd,
        "original_image_urls": images["original_image_urls"],
        "cardnews_image_urls": images["cardnews_image_urls"],
        "image_urls": images["image_urls"],
        "source_url": (item.get("OriginalUrl") or "").strip(),
        "subtitles": merge_subtitles(item),
        "contents_status": (item.get("ContentsStatus") or "").strip(),
    }


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("_x000D_", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()
