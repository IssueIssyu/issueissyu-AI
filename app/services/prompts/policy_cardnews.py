from __future__ import annotations

POLICY_CARDNEWS_SLIDE_PROMPT = """
[역할]
정책 내용을 고정 카드뉴스 템플릿에 넣을 문구만 작성한다.

[출력]
JSON 배열만. 2~3장.
- 1장: template_cover (표지)
- 중간(있으면): template_numbered / items 4개 이하, template_three_col / items 3개, template_grid / items 4개
- 마지막: template_cta

[필드]
slide, layout_type, eyebrow, headline, highlight, subtext, body, items[{label,text}], term_guides[{term,plain}], cta, speech, use_image

[규칙]
- 어려운 정책·법률 용어는 쉬운 말로 바꿔 쓰기 (예: 개인정보→내 정보, 실태조사→현장 점검)
- 본문에 꼭 필요한 전문 용어가 있으면 term_guides에 최대 2개 (term+plain 한 줄 설명)
- cover: eyebrow(짧은 질문/카테고리), headline+highlight(핵심 키워드), speech 10~18자
- 정책에 관련 사진·이미지가 있으면 1장 cover의 use_image=true (표지에 사진 크게 표시)
- 이미지가 없을 때만 cover에 speech(캐릭터 말풍선용) 작성
- theme: cream_warm|mint_fresh|slate_modern|peach_soft|lavender_light|snow_clean 중 **카드뉴스 전체에 하나** (1장만 넣어도 됨, 모든 슬라이드 동일 색)
- 중간: headline(한 줄 제목), items 3~4개(라벨+짧은 설명), body 비우기
- cta: headline, cta(버튼 문구), body(1줄 안내), term_guides(선택), speech 10~18자(캐릭터 말풍선, 친근하게)
- 입력에 없는 정보 생성 금지
- PPT/보도자료체 금지

[예시 3장]
[
  {
    "slide": 1,
    "layout_type": "template_cover",
    "eyebrow": "청년 정책",
    "headline": "정부 지원",
    "highlight": "월 20만원",
    "body": "",
    "items": [],
    "cta": "",
    "speech": "이거 꼭 봐!",
    "use_image": false,
    "theme": "mint_fresh"
  },
  {
    "slide": 2,
    "layout_type": "template_grid",
    "eyebrow": "한 장 요약",
    "headline": "이렇게 지원해요",
    "highlight": "",
    "body": "",
    "items": [
      {"label": "대상", "text": "만 19~34세 무주택 청년"},
      {"label": "지원금", "text": "월 20만원"},
      {"label": "기간", "text": "2025년 하반기~"},
      {"label": "신청", "text": "온라인 접수"}
    ],
    "cta": "",
    "speech": "",
    "use_image": false
  },
  {
    "slide": 3,
    "layout_type": "template_cta",
    "eyebrow": "마무리",
    "headline": "자세한 조건은 원문에서",
    "highlight": "",
    "body": "소득·재산 기준은 공식 뉴스를 확인해 주세요.",
    "items": [],
    "cta": "원문 뉴스 보기",
    "speech": "원문 확인해!",
    "use_image": false
  }
]
"""

_POLICY_INPUT = """
[입력]
제목: {pin_title}
부처: {minister}
본문: {pin_content}
"""


def build_policy_cardnews_slide_prompt(
    *,
    pin_title: str,
    pin_content: str,
    minister: str = "",
) -> str:
    return POLICY_CARDNEWS_SLIDE_PROMPT + _POLICY_INPUT.format(
        pin_title=(pin_title or "").strip(),
        pin_content=(pin_content or "").strip(),
        minister=(minister or "").strip(),
    )


def build_policy_cardnews_image_prompt(
    *,
    pin_title: str,
    minister: str,
    slide: dict,
    slide_index: int,
    slide_total: int,
) -> str:
    return (
        f"Policy cardnews slide {slide_index}/{slide_total}. "
        f"Title: {pin_title}. Minister: {minister}. "
        f"Layout: {slide.get('layout_type')}. "
        f"Copy: {slide}"
    )
