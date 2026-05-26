"""정책 카드뉴스 템플릿 전용 메트릭(수치) 모음.

공통 상수(`policy_cardnews_constants.py`)는 템플릿/레거시 렌더러가 같이 쓰는 값만 두고,
템플릿 레이아웃의 비율/예약 높이 같은 값은 여기로 분리한다.
"""

from __future__ import annotations

# mascot / layout separation
GAP_MASCOT = 20
MIN_MASCOT_ZONE_H = 220

# cover
COVER_MASCOT_MIN_H = 420
COVER_MASCOT_ZONE_RATIO = 0.52
COVER_TEXT_RATIO_WITH_HERO = 0.34

# CTA (template)
CTA_MIN_MASCOT_ZONE = 300

