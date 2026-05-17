from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComplaintEmailVlmInput(BaseModel):
    #VLM 분석 요청 (이미지 바이너리는 별도 ImageWithLocation 리스트로 전달)
    user_text: str
    user_location: str | None = None
    photo_address: str | None = None


class ComplaintEmailVlmOutput(BaseModel):
    #Gemini가 반환하는 JSON
    type: str
    domain: str
    subcategory: str
    summary: str = ""
    objects: list[str] = Field(default_factory=list)
    error_code: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query: str = ""


class ComplaintEmailVlmAnalyzeResult(BaseModel):
    #LLM 분석 + 백엔드 검증 필드를 합친 최종 결과
    type: str
    domain: str
    subcategory: str
    summary: str
    objects: list[str]
    error_code: str | None = None
    keywords: list[str]
    query: str

    model_config = ConfigDict(from_attributes=True)

    """def to_legacy_dict(self) -> dict[str, Any]:
        #기존 파이프라인(IssueService 등)이 기대하는 dict 형태.
        lv = self.location_verification
        return {
            "category": {"type": self.type, "domain": self.domain},
            "type": self.type,
            "domain": self.domain,
            "subcategory": self.subcategory,
            "scene_summary": self.summary,
            "summary": self.summary,
            "objects": self.objects,
            "retrieval_keywords": self.keywords,
            "keywords": self.keywords,
            "retrieval_query": self.query,
            "query": self.query,
            "location_context": self.location_context,
            "validity": self.validity,
            "error_code": self.error_code,
            "risk_note": self.risk_note,
            "privacy_note": self.privacy_note,
            "recommended_action": None,
            "confidence_score": self.confidence_score,
            "location_verification": {
                "status": lv.status,
                "message": lv.message,
                "user_location": lv.user_location,
                "photo_location": None,
                "photo_address": lv.photo_address,
            },
        }
"""