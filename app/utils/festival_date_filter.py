from __future__ import annotations

from datetime import date, datetime


def current_year_festival_range(*, ref: date | None = None) -> tuple[str, str]:
    """올해 오늘~12/31 (매년 동일 패턴)."""
    today = ref or date.today()
    start = today.strftime("%Y%m%d")
    end = date(today.year, 12, 31).strftime("%Y%m%d")
    return start, end


def validate_yyyymmdd(value: str, *, label: str) -> str:
    text = (value or "").strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError:
        raise ValueError(
            f"{label}는 올바른 YYYYMMDD 형식의 날짜여야 합니다 (받음: {value!r})",
        ) from None
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
