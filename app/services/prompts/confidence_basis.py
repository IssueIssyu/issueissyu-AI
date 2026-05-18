from __future__ import annotations

CONFIDENCE_BASIS_AXES = ("content", "image", "location", "reference", "caution")
CONFIDENCE_BASIS_STATUSES = ("ok", "warn", "skip")

CONFIDENCE_BASIS_ITEM_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["axis", "status", "text"],
    "properties": {
        "axis": {
            "type": "string",
            "enum": list(CONFIDENCE_BASIS_AXES),
        },
        "status": {
            "type": "string",
            "enum": list(CONFIDENCE_BASIS_STATUSES),
        },
        "text": {"type": "string"},
    },
}

CONFIDENCE_BASIS_ARRAY_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": CONFIDENCE_BASIS_ITEM_SCHEMA,
    "minItems": 3,
    "maxItems": 5,
}

CONFIDENCE_BASIS_PROMPT_BLOCK = """
[신뢰도 근거 — confidence_basis]
이 근거는 제보를 올린 일반 시민이 앱에서 읽습니다. 개발자·관리자용 설명이 아닙니다.

고정 축만 사용한다. 배열 3~5개, 각 항목은 axis·status·text 필드만 가진다.
- content: 제목·본문이 무엇에 대한 제보인지 읽는 사람이 이해할 수 있는지
- image: 사진이 글과 같은 상황인지 (사진 없으면 status=skip, text="")
- location: 지도에 찍은 위치와 사진·글에 나온 장소가 맞아 보이는지
- reference: 비슷한 민원 사례와 주제가 통하는지 (없으면 skip)
- caution: 사진이 흐리거나 위치 확인이 어려운 점 등 (해당 없으면 skip)

status 규칙:
- ok: 잘 맞거나 확인된 점
- warn: 애매하거나 한번 더 보면 좋은 점 (비난·단정 금지)
- skip: 해당 없음 (text는 빈 문자열)

text 규칙 (매우 중요):
- 존댓말, 쉬운 말, 1문장, 80자 이내 권장
- "~해 보입니다", "~확인됩니다" 등 부드러운 표현
- 점수·퍼센트·AI·모델·RAG·EXIF·메타데이터·GPS·JSON·축(axis) 같은 기술 용어 금지
- "핀", "역지오코딩", "검색 결과" 같은 내부 용어 금지 → "지도에 표시한 위치", "사진을 찍은 곳" 등으로 쓴다
- 낮은 신뢰도여도 게시는 유지되므로, 왜 조심스러운지 친절히 설명한다
- skip이면 text=""
""".strip()

CONFIDENCE_BASIS_JSON_EXAMPLE_WITH_IMAGE = """
"confidence_basis": [
  { "axis": "content", "status": "ok", "text": "무엇을 제보하셨는지 글만 봐도 이해하기 쉽습니다." },
  { "axis": "image", "status": "ok", "text": "사진에서도 글과 같은 쓰레기 투기 상황이 보입니다." },
  { "axis": "location", "status": "warn", "text": "사진을 찍은 곳과 지도에 표시한 위치가 완전히 같지는 않아 보입니다." },
  { "axis": "reference", "status": "skip", "text": "" },
  { "axis": "caution", "status": "skip", "text": "" }
]
""".strip()

CONFIDENCE_BASIS_JSON_EXAMPLE_TEXT_ONLY = """
"confidence_basis": [
  { "axis": "content", "status": "ok", "text": "언제, 어디서, 어떤 문제인지 글에 잘 적혀 있습니다." },
  { "axis": "image", "status": "skip", "text": "" },
  { "axis": "location", "status": "ok", "text": "지도에 표시한 위치와 글에 적은 장소가 잘 맞아 보입니다." },
  { "axis": "reference", "status": "skip", "text": "" },
  { "axis": "caution", "status": "skip", "text": "" }
]
""".strip()
