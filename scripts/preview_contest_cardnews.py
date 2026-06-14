"""Gemini 없이 공모전 3장 템플릿 미리보기 (표지·요약·CTA)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.contest_cardnews import render_contest_cardnews_slides

SAMPLE_DECK = [
    {
        "slide": 1,
        "layout_type": "contest_cover",
        "eyebrow": "대외활동",
        "headline": "귀여운",
        "highlight": "카드뉴스",
        "body": "다양한 홍보에 활용해 보세요",
        "speech": "한번 봐!",
        "use_image": False,
        "template_palette": "pastel_mint",
    },
    {
        "slide": 2,
        "layout_type": "contest_table",
        "items": [
            {"label": "주최", "text": "OO재단"},
            {"label": "지원자격", "text": "대학생·대학원생"},
            {"label": "접수", "text": "6월 30일"},
            {"label": "혜택", "text": "상금 500만"},
        ],
        "point": "마감 전 꼭 확인하세요",
        "use_image": False,
    },
    {
        "slide": 3,
        "layout_type": "contest_cta",
        "headline": "자세한 공고는",
        "highlight": "원문에서",
        "body": "링크에서 확인하세요",
        "cta": "공고 보러가기",
        "speech": "링크 확인!",
        "use_image": False,
    },
]


async def main() -> None:
    paths = await render_contest_cardnews_slides(
        contentid="_preview_3deck",
        slides=SAMPLE_DECK,
        output_dir=Path("rag/output/contest_cardnews"),
        source_url="https://linkareer.com/activity/319419",
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    asyncio.run(main())
