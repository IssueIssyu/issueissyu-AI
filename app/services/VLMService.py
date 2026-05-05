from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError

from google import genai
from google.genai import types

from app.services.vlm_prompt import build_vlm_prompt


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
    ],
    "properties": {
        "category": {
            "type": "object",
            "required": ["type", "domain"],
            "properties": {
                "type": {"type": "string"},
                "domain": {"type": "string"},
            },
        },
        "subcategory": {"type": ["string", "null"]},
        "scene_summary": {"type": "string"},
        "objects": {"type": "array", "items": {"type": "string"}},
        "location_context": {"type": ["string", "null"]},
        "validity": {"type": "boolean"},
        "error_code": {"type": ["string", "null"]},
        "risk_note": {"type": ["string", "null"]},
        "privacy_note": {"type": "string"},
        "retrieval_keywords": {"type": "array", "items": {"type": "string"}},
        "retrieval_query": {"type": "string"},
        "recommended_action": {"type": ["string", "null"]},
        "confidence_score": {"type": "number"},
    },
}


@dataclass(slots=True)
class VLMService:
    api_key: str
    model_name: str = "gemini-3.1-pro-preview"

    def __post_init__(self) -> None:
        self.client = genai.Client(api_key=self.api_key)

    def analyze_image(
        self,
        *,
        user_text: str,
        image_bytes: bytes,
        image_mime_type: str,
        location: str | None = None,
    ) -> dict:
        prompt = build_vlm_prompt(
            user_text=user_text,
            location=location,
        )
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=VLM_RESPONSE_SCHEMA,
        )

        response = self.client.models.generate_content(
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

        return self._normalize(parsed=parsed, location=location)

    @staticmethod
    def _normalize(*, parsed: dict, location: str | None) -> dict:
        # location 미입력 시 위치 생성 금지
        if location is None or not location.strip():
            parsed["location_context"] = None

        validity = bool(parsed.get("validity"))
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
