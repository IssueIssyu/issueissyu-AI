from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError

from google import genai
from google.genai import types
from starlette.datastructures import UploadFile

from app.services.vlm_prompt import (
    VLM_ADMIN_DOMAINS,
    VLM_CATEGORY_TYPES,
    VLM_ERROR_CODES,
    VLM_LOCATION_VERIFICATION_STATUSES,
    VLM_PRIVACY_NOTES,
    build_vlm_prompt,
)

_LOCATION_VERIFICATION_FALLBACK_MESSAGES: dict[str, str] = {
    "matched": "사용자 위치와 사진 메타데이터 위치가 일치합니다",
    "same_area": "사용자 위치와 사진 메타데이터 위치가 같은 동네 수준으로 보입니다",
    "different_area": "사용자 위치와 사진 메타데이터 위치가 다를 수 있습니다",
    "not_checked": "메타데이터에 주소가 없습니다",
    "unknown": "위치 일치 여부를 판단하기 어렵습니다",
}

# 위치 정보가 없을 때 지역 표현 제거에 사용하는 패턴
_LOCATION_PATTERN = re.compile(
    r"[가-힣0-9]+(?:특별자치도|특별자치시|특별시|광역시)(?:\s*[,\s]|$)+|"
    r"[가-힣0-9]+(?:시|군)(?:\s*[,\s]|$)+|"
    r"[가-힣0-9]+구(?:\s*[,\s]|$)+|"
    r"[가-힣0-9]+(?:읍|면|동|리)(?:\s*[,\s]|$)+"
)

_PURE_ADMIN_KEYWORD = re.compile(
    r"^[가-힣0-9]+(?:특별자치도|특별자치시|특별시|광역시|시|군|구|읍|면|동|리)$"
)


def _remove_location_terms(text: str) -> str:
    t = text.strip()
    if not t:
        return ""
    prev = None
    while prev != t:
        prev = t
        t = _LOCATION_PATTERN.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" ,·")


def _clean_location_query(
    query: str,
    *,
    model_location_context: str | None,
) -> str:
    t = query.strip() if query else ""
    if not t:
        return ""
    if model_location_context:
        mc = model_location_context.strip()
        if mc:
            t = t.replace(mc, " ")
    return _remove_location_terms(t)


def _clean_location_keywords(
    keywords: list,
    *,
    model_location_context: str | None,
) -> list:
    mc = (model_location_context or "").strip()
    out: list[str] = []
    seen: set[str] = set()
    for k in keywords:
        if not isinstance(k, str):
            continue
        t = k.strip()
        if not t:
            continue
        if mc and mc in t:
            t = t.replace(mc, " ").strip()
        t = _remove_location_terms(t)
        if not t or _PURE_ADMIN_KEYWORD.match(t):
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def normalize_validity(value: object) -> bool:
    """json.loads 직후 validity: bool만 신뢰하고, 문자열 true/false·0/1만 보조 인정. 그 외는 False."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s == "true":
            return True
        if s == "false":
            return False
    if isinstance(value, int):
        if value == 1:
            return True
        if value == 0:
            return False
    return False


def coerce_photo_address(value: object) -> str | None:
    """str·list·tuple 등을 단일 주소 문자열로 정규화. 여러 항목은 ', '로 연결."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts: list[str] = []
        for item in value:
            if item is None:
                continue
            t = str(item).strip()
            if t:
                parts.append(t)
        if not parts:
            return None
        return ", ".join(parts)
    s = str(value).strip()
    return s or None


VLM_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "category",
        "subcategory",
        "scene_summary",
        "objects",
        "location_context",
        "validity",
        "error_code",
        "risk_note",
        "privacy_note",
        "retrieval_keywords",
        "retrieval_query",
        "recommended_action",
        "confidence_score",
        "location_verification",
    ],
    "properties": {
        "category": {
            "type": "object",
            "required": ["type", "domain"],
            "properties": {
                "type": {"type": "string", "enum": list(VLM_CATEGORY_TYPES)},
                "domain": {"type": "string", "enum": list(VLM_ADMIN_DOMAINS)},
            },
        },
        "subcategory": {"type": ["string", "null"]},
        "scene_summary": {"type": "string"},
        "objects": {"type": "array", "items": {"type": "string"}},
        "location_context": {"type": ["string", "null"]},
        "validity": {"type": "boolean"},
        "error_code": {
            "type": ["string", "null"],
            "enum": [*VLM_ERROR_CODES, None],
        },
        "risk_note": {"type": ["string", "null"]},
        "privacy_note": {"type": "string", "enum": list(VLM_PRIVACY_NOTES)},
        "retrieval_keywords": {"type": "array", "items": {"type": "string"}},
        "retrieval_query": {"type": "string"},
        "recommended_action": {"type": ["string", "null"]},
        "confidence_score": {"type": "number"},
        "location_verification": {
            "type": "object",
            "required": [
                "status",
                "message",
                "user_location",
                "photo_location",
                "photo_address",
            ],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": list(VLM_LOCATION_VERIFICATION_STATUSES),
                },
                "message": {"type": "string"},
                "user_location": {"type": ["string", "null"]},
                "photo_location": {"type": ["string", "null"]},
                "photo_address": {"type": ["string", "null"]},
            },
        },
    },
}


@dataclass(slots=True)
class VLMService:
    api_key: str
    model_name: str = "gemini-3.1-pro-preview"
    client: genai.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    async def analyze_image(
        self,
        *,
        user_text: str,
        upload: UploadFile,
        user_location: str | None = None,
        photo_address: str | Sequence[str] | None = None,
        location: str | None = None,
    ) -> dict:
        image_bytes = await upload.read()
        if not image_bytes:
            raise RuntimeError("업로드 이미지가 비어 있습니다.")

        mime = (upload.content_type or "").split(";")[0].strip().lower()
        if not mime:
            guessed, _ = mimetypes.guess_type(upload.filename or "")
            mime = (guessed or "image/jpeg").split(";")[0].strip().lower()
        if not mime.startswith("image/"):
            mime = "image/jpeg"

        eff_user_location = user_location
        if (eff_user_location is None or not str(eff_user_location).strip()) and (
            location is not None and str(location).strip()
        ):
            eff_user_location = location
        photo_address_str = coerce_photo_address(photo_address)
        prompt = build_vlm_prompt(
            user_text=user_text,
            user_location=eff_user_location,
            photo_address=photo_address_str,
        )
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=VLM_RESPONSE_SCHEMA,
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[image_part, prompt],
            config=config,
        )

        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini VLM 응답 텍스트가 비어 있습니다.")

        try:
            parsed = json.loads(text)
        except JSONDecodeError as exc:
            raise RuntimeError(f"Gemini JSON 파싱 실패: {exc}") from exc

        return self._normalize(
            parsed=parsed,
            user_location=eff_user_location,
            photo_address=photo_address_str,
        )

    @staticmethod
    def _normalize(
        *,
        parsed: dict,
        user_location: str | None,
        photo_address: str | None,
    ) -> dict:
        ul = user_location.strip() if isinstance(user_location, str) and user_location.strip() else None
        pa = photo_address.strip() if isinstance(photo_address, str) and photo_address.strip() else None

        # 사용자 위치·사진 메타 주소가 모두 없을 때: location_context 삭제, 쿼리/키워드에서 지명·행정구역 조각 제거
        if ul is None and pa is None:
            lc_raw = parsed.get("location_context")
            model_lc = lc_raw.strip() if isinstance(lc_raw, str) else ""
            rq = parsed.get("retrieval_query")
            rq_s = rq if isinstance(rq, str) else ""
            parsed["retrieval_query"] = _clean_location_query(
                rq_s,
                model_location_context=model_lc or None,
            )
            kw = parsed.get("retrieval_keywords")
            if isinstance(kw, list):
                parsed["retrieval_keywords"] = _clean_location_keywords(
                    kw,
                    model_location_context=model_lc or None,
                )
            parsed["location_context"] = None

        lv = parsed.get("location_verification")
        if not isinstance(lv, dict):
            lv = {}
        if pa is None:
            default_lv_status = "not_checked"
            default_lv_message = "메타데이터에 주소가 없습니다"
        else:
            default_lv_status = "unknown"
            default_lv_message = "위치 일치 여부를 판단하기 어렵습니다"
        st = lv.get("status")
        status_was_invalid = not isinstance(st, str) or st not in VLM_LOCATION_VERIFICATION_STATUSES
        if status_was_invalid:
            lv["status"] = default_lv_status
        msg = lv.get("message")
        if not isinstance(msg, str) or not msg.strip():
            if status_was_invalid:
                lv["message"] = default_lv_message
            else:
                st_ok = lv.get("status")
                lv["message"] = (
                    _LOCATION_VERIFICATION_FALLBACK_MESSAGES[st_ok]
                    if isinstance(st_ok, str) and st_ok in _LOCATION_VERIFICATION_FALLBACK_MESSAGES
                    else default_lv_message
                )
        lv["user_location"] = ul
        lv["photo_location"] = None
        lv["photo_address"] = pa
        parsed["location_verification"] = lv

        validity = normalize_validity(parsed.get("validity"))
        parsed["validity"] = validity
        if validity:
            parsed["error_code"] = None
        elif not parsed.get("error_code"):
            parsed["error_code"] = "E004_CATEGORY_UNCLEAR"

        query = parsed.get("retrieval_query")
        if not isinstance(query, str):
            parsed["retrieval_query"] = ""

        keywords = parsed.get("retrieval_keywords")
        if not isinstance(keywords, list):
            parsed["retrieval_keywords"] = []

        if "confidence_score" in parsed:
            try:
                score = float(parsed["confidence_score"])
            except (TypeError, ValueError):
                score = 0.0
            parsed["confidence_score"] = max(0.0, min(1.0, score))
        else:
            parsed["confidence_score"] = 0.0

        return parsed
