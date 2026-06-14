from __future__ import annotations

CONTEST_CARDNEWS_SLIDE_PROMPT = """
[역할]
공모전·대외활동 공고를 브라우저형 카드뉴스 템플릿 문구로 작성한다.
원문에 없는 정보는 만들지 않는다. 크롤 이미지는 사용하지 않는다.

[출력]
JSON 배열 **정확히 3개**만.

[3장 구성 — 필수]
1. contest_cover — 표지
2. contest_table **또는** contest_checklist — 한눈 요약 (둘 중 하나만)
3. contest_cta — 원문 링크 유도

[사용 금지]
contest_headline, contest_body, contest_three_col 및 그 외 layout

[필드]
slide, layout_type, eyebrow, headline, highlight, body, items[{label,text}],
cta, speech, point, use_image, template_palette

[규칙]
- use_image: false
- template_palette: 전 슬라이드 동일 1개
  pastel_mint, pastel_pink, pastel_lavender, pastel_peach, pastel_sky, pastel_lemon
- cover: eyebrow, headline+highlight(제목), body(하단 한 줄), speech 8~12자
- contest_table: items 3~4개 (주최·대상·접수·혜택 등), point 1줄
- contest_checklist: items 3~4개(짧은 확인 문장), point 1줄
- cta: headline, highlight, body 1줄, cta(버튼), speech 8~12자 (원문 URL은 렌더 시 자동 표기 — JSON에 넣지 않음)
- 문장은 짧고 큼직하게

[예시]
[
  {
    "slide": 1,
    "layout_type": "contest_cover",
    "eyebrow": "대외활동",
    "headline": "OO",
    "highlight": "공모전",
    "body": "지금 바로 확인해 보세요",
    "speech": "놓치지 마!",
    "use_image": false,
    "template_palette": "pastel_mint"
  },
  {
    "slide": 2,
    "layout_type": "contest_table",
    "items": [
      {"label": "주최", "text": "OO재단"},
      {"label": "대상", "text": "대학생"},
      {"label": "접수", "text": "6월 30일"},
      {"label": "혜택", "text": "상금"}
    ],
    "point": "마감 전 꼭 확인",
    "use_image": false
  },
  {
    "slide": 3,
    "layout_type": "contest_cta",
    "headline": "자세한 공고는",
    "highlight": "원문에서",
    "body": "링크에서 확인하세요",
    "cta": "공고 보러가기",
    "speech": "링크 확인!",
    "use_image": false
  }
]
"""

_CONTEST_INPUT = """
[입력]
제목: {pin_title}
주최: {host_org}
접수 시작: {event_start_time}
접수 마감: {event_end_time}
원문 URL: {source_url}
본문:
{pin_content_raw}
"""


def build_contest_cardnews_slide_prompt(
    *,
    pin_title: str,
    pin_content_raw: str,
    host_org: str = "",
    event_start_time: str | None = None,
    event_end_time: str | None = None,
    source_url: str = "",
) -> str:
    return CONTEST_CARDNEWS_SLIDE_PROMPT + _CONTEST_INPUT.format(
        pin_title=(pin_title or "").strip(),
        pin_content_raw=(pin_content_raw or "").strip(),
        host_org=(host_org or "").strip(),
        event_start_time=(event_start_time or "").strip() or "미상",
        event_end_time=(event_end_time or "").strip() or "미상",
        source_url=(source_url or "").strip(),
    )


CONTEST_CARDNEWS_CAPTION_PROMPT = """
[역할]
인스타그램 카드뉴스 캡션 2~4문장 작성.

[규칙]
- 친근한 톤, 이모지 1~2개
- 마지막 줄에 해시태그 3~5개
- 원문에 없는 정보 금지
- 본문만 출력

[입력]
제목: {pin_title}
주최: {host_org}
원문: {source_url}
요약 본문:
{pin_content_raw}
"""


def build_contest_cardnews_caption_prompt(
    *,
    pin_title: str,
    pin_content_raw: str,
    host_org: str = "",
    source_url: str = "",
) -> str:
    return CONTEST_CARDNEWS_CAPTION_PROMPT.format(
        pin_title=(pin_title or "").strip(),
        pin_content_raw=(pin_content_raw or "").strip()[:2000],
        host_org=(host_org or "").strip(),
        source_url=(source_url or "").strip(),
    )
