from __future__ import annotations

from enum import StrEnum


class ToneType(StrEnum):
    """API·프롬프트는 value(한글), DB pin.tone_type은 Spring enum name."""

    NONE = "없음"
    ONE_LINE_SUMMARY = "한줄요약형"
    SITUATION_DESCRIPTION = "상황설명형"
    IMPROVEMENT_REQUEST = "개선요청형"
    URGENT_REQUEST = "긴급요청형"
    DISCOMFORT_COMPLAINT = "불편호소형"

    def to_db(self) -> str:
        return self.name

    @classmethod
    def from_db(cls, value: str | None) -> ToneType:
        if not value:
            return cls.NONE
        try:
            return cls[value]
        except KeyError:
            return cls.NONE
