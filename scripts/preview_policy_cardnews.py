from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.policy_cardnews import parse_cardnews_slides_json, render_policy_cardnews_slides

SAMPLE = [
    {
        "slide": 1,
        "layout_type": "template_cover",
        "theme": "cream_warm",
        "eyebrow": "청년 정책",
        "headline": "정부가 지켜줄게!",
        "highlight": "월 20만원",
        "subtext": "올 하반기 시행",
        "body": "무주택 청년 대상 생활비 지원 프로그램입니다.",
        "items": [],
        "cta": "",
        "speech": "이거 꼭 봐!",
        "use_image": True,
    },
    {
        "slide": 2,
        "layout_type": "template_grid",
        "theme": "mint_fresh",
        "eyebrow": "한 장 요약",
        "headline": "이렇게 지원해요",
        "highlight": "",
        "body": "아래 조건을 모두 확인해 주세요.",
        "items": [
            {"label": "대상", "text": "만 19~34세 무주택 청년"},
            {"label": "지원금", "text": "월 20만원"},
            {"label": "기간", "text": "2025년 하반기~"},
            {"label": "신청", "text": "온라인 접수"},
            {"label": "문의", "text": "주민센터 또는 복지로"},
        ],
        "cta": "",
        "speech": "",
        "use_image": True,
    },
    {
        "slide": 3,
        "layout_type": "template_cta",
        "theme": "slate_modern",
        "eyebrow": "",
        "headline": "자세한 조건은 원문에서",
        "highlight": "",
        "body": "소득·재산 기준 등 세부 내용은 공식 정책뉴스를 확인해 주세요.",
        "items": [],
        "cta": "원문 확인",
        "speech": "원문 확인해!",
        "use_image": False,
    },
]


async def main() -> None:
    slides = parse_cardnews_slides_json(json.dumps(SAMPLE, ensure_ascii=False))
    paths = await render_policy_cardnews_slides(
        contentid="_preview_brand",
        slides=slides,
        output_dir=Path("rag/output/policy_cardnews"),
        minister="기획재정부",
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    asyncio.run(main())
