from __future__ import annotations


def validate_yyyymmdd(value: str, *, label: str) -> str:
    text = (value or "").strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"{label}는 YYYYMMDD 8자리여야 합니다 (받음: {value!r})")
    return text


def normalize_event_range(
    event_start: str | None,
    event_end: str | None,
) -> tuple[str, str] | None:
    start = (event_start or "").strip()
    end = (event_end or "").strip()
    if start and end:
        return (min(start, end), max(start, end))
    if start:
        return (start, start)
    if end:
        return (end, end)
    return None


def festival_overlaps_range(
    *,
    event_start: str | None,
    event_end: str | None,
    query_start: str,
    query_end: str,
) -> bool:
    # 행사 기간 [event_start, event_end]가 조회 기간과 하루라도 겹치면 True
    fest = normalize_event_range(event_start, event_end)
    if fest is None:
        return False
    fest_start, fest_end = fest
    return fest_start <= query_end and fest_end >= query_start
