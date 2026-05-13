from __future__ import annotations

from enum import StrEnum


class ToneType(StrEnum):
    NONE = "없음"
    ONE_LINE_SUMMARY = "한줄요약형"
    SITUATION_DESCRIPTION = "상황설명형"
    IMPROVEMENT_REQUEST = "개선요청형"
    URGENT_REQUEST = "긴급요청형"
    DISCOMFORT_COMPLAINT = "불편호소형"
