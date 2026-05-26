from __future__ import annotations

import re

# DB 스키마 이름은 유지하면서, department_name에 카테고리 값을 저장한다.
CURATED_CATEGORIES: tuple[str, ...] = (
    "건축허가",
    "경제",
    "공통",
    "교통",
    "농업_축산",
    "문화_체육_관광",
    "보건소",
    "복지",
    "산림",
    "상하수도",
    "세무",
    "안전건설",
    "위생",
    "자동차",
    "정보통신",
    "토지",
    "행정",
    "환경미화",
)
_NORMALIZE_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


def normalize_department_name(value: str) -> str:
    return _NORMALIZE_RE.sub("", (value or "").strip())


CURATED_CATEGORY_NAMES: tuple[str, ...] = tuple(sorted(CURATED_CATEGORIES))
CURATED_CATEGORY_NAME_SET: frozenset[str] = frozenset(CURATED_CATEGORIES)
CURATED_CATEGORY_NORMALIZED_MAP: dict[str, str] = {
    normalize_department_name(name): name
    for name in CURATED_CATEGORIES
}
