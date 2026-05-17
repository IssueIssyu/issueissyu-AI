from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

class ComplaintEmailVlmImageSlot(BaseModel):
    # 프롬프트,메타 설명용 이미지 슬롯 (바이너리는 별도 전달)
    index: int = Field(ge=1)
    filename: str
    photo_address: str | None = None


class ComplaintEmailVlmInput(BaseModel):
    #VLM 분석 요청. 업로드 이미지 바이너리는 서비스 images 인자로 전달
    user_text: str
    user_location: str | None = None
    photo_address: str | None = None
    image_slots: list[ComplaintEmailVlmImageSlot] = Field(default_factory=list)


class ComplaintEmailVlmOutput(BaseModel):
    #Gemini VLM이 반환하는 JSON (이미지 분석 결과)
    type: str
    domain: str
    subcategory: str | None = None
    summary: str = ""
    objects: list[str] = Field(default_factory=list)
    error_code: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query: str = ""


class ComplaintEmailVlmAnalyzeResult(BaseModel):
    """VLM 분석 + 백엔드 검증을 합친 최종 결과."""

    type: str
    domain: str
    subcategory: str | None = None
    summary: str
    objects: list[str]
    error_code: str | None = None
    keywords: list[str]
    query: str

    model_config = ConfigDict(from_attributes=True)

    def to_legacy_dict(
        self,
        *,
        user_location: str | None = None,
        photo_address: str | None = None,
        location_verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """IssueService 등 기존 dict 기반 호출부 호환."""
        lv = location_verification or {
            "status": "not_checked",
            "message": "메타데이터에 주소가 없습니다",
            "user_location": user_location,
            "photo_location": None,
            "photo_address": photo_address,
        }
        validity = self.error_code is None
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
            "error_code": self.error_code,
            "validity": validity,
            "privacy_note": (
                "주의) 개인정보 포함 가능성 있음"
                if self.error_code == "E007_PRIVACY_RISK"
                else "해당 없음"
            ),
            "recommended_action": None,
            "confidence_score": 0.5 if validity else 0.2,
            "risk_note": None,
            "location_verification": lv,
        }
