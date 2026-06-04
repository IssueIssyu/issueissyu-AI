from __future__ import annotations

from typing import Any


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()

_UNKNOWN = "정보 없음"

_PET_INTRO_KEYWORDS = ("반려동물", "반려견", "애견", "pet")
_STAY_KEYWORDS = ("숙박", "숙소", " lodging", "stay")


def _yn_to_label(value: object) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text in {"Y", "YES", "1", "가능", "O"}:
        return "가능"
    if text in {"N", "NO", "0", "불가", "X"}:
        return "불가"
    if len(text) <= 20:
        return text
    return None


def _intro_items(intro_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(intro_payload, dict):
        return []
    response = intro_payload.get("response")
    if not isinstance(response, dict):
        return []
    body = response.get("body")
    if not isinstance(body, dict):
        return []
    items_dict = body.get("items")
    if not isinstance(items_dict, dict):
        return []
    raw = items_dict.get("item")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _pick_intro_field(items: list[dict[str, Any]], *, keywords: tuple[str, ...]) -> str | None:
    for item in items:
        name = _clean_text(str(item.get("infoname") or ""))
        text = _clean_text(str(item.get("infotext") or ""))
        haystack = f"{name} {text}".lower()
        if any(k.lower() in haystack for k in keywords):
            if name and text:
                return f"{name}: {text}"
            return text or name or None
    return None


def _pick_direct_field(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> str | None:
    for item in items:
        for key in keys:
            raw = item.get(key)
            if raw is None:
                continue
            text = _clean_text(str(raw))
            if text:
                return text
    return None


def extract_pet_friendly(
    *,
    pet_tour_payload: dict[str, Any] | None,
    intro_payload: dict[str, Any] | None,
) -> str:
    if pet_tour_payload:
        body_items = _intro_items(pet_tour_payload)
        if body_items:
            item = body_items[0]
            for key in (
                "chkpetfriendly",
                "chkpet",
                "chkpetsize",
                "chkpetplace",
                "chkpetleash",
            ):
                label = _yn_to_label(item.get(key))
                if label:
                    return f"반려동물 동반 {label}"

            detail_parts: list[str] = []
            for key, value in sorted(item.items()):
                key_lower = str(key).lower()
                if not key_lower.startswith(("chkpet", "pet")):
                    continue
                if value is None:
                    continue
                text = _clean_text(str(value))
                if text and text.upper() not in {"Y", "N"}:
                    detail_parts.append(text)
            if detail_parts:
                return "; ".join(detail_parts)

    intro_hint = _pick_intro_field(
        _intro_items(intro_payload),
        keywords=_PET_INTRO_KEYWORDS,
    )
    if intro_hint:
        return intro_hint

    return _UNKNOWN


def extract_stay_available(*, intro_payload: dict[str, Any] | None) -> str:
    items = _intro_items(intro_payload)
    intro_hint = _pick_intro_field(items, keywords=_STAY_KEYWORDS)
    if intro_hint:
        return intro_hint

    direct = _pick_direct_field(
        items,
        keys=("stayinfo", "lodgment", "accommodation", "roominfo", "lodging"),
    )
    if direct:
        return direct

    return _UNKNOWN
