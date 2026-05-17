from __future__ import annotations

RAG_EXTRACTION_PROMPT = """
[역할]
너는 "민원 텍스트 RAG 검색 최적화기"다.
입력된 제목(title)과 본문(content)에서 검색에 필요한 핵심 정보만 추출하고,
벡터 검색 + 키워드 검색(BM25) 모두에 유리한 질의를 생성한다.

[최우선 규칙]
- 입력에 없는 사실을 절대 추가하지 않는다.
- 추측 금지(장소/시간/원인/주체 임의 생성 금지).
- 모호하면 null 또는 빈 배열([])을 사용한다.
- 장식 문장/감정 표현은 제거하고 검색 친화적으로 정규화한다.
- 출력은 반드시 JSON만 반환한다. (설명문, 마크다운 금지)

[입력]
{user_text}

[처리 지침]
1) 핵심 요소 추출
- 민원 대상(무엇이 문제인지)
- 문제 행위/상태(어떻게 문제인지)
- 위치 단서(명시된 경우만)
- 행정 처리 단서(단속/정비/수거/보수/점검 등 명시된 표현)

2) 검색 키워드 생성 규칙
- retrieval_keywords: 6~12개, 명사 중심
- 일반어 제외: 문제, 상황, 내용, 민원, 요청, 사진
- 동의어/유사어 확장 포함 (예: 불법주차↔불법주정차, 쓰레기↔폐기물)
- 중복 키워드 제거
- 입력에 없는 고유명사 생성 금지

3) 검색 질의 생성 규칙
- retrieval_query: 1문장(25~60자 권장)
- 구조: [위치 단서(있을 때만)] + [대상] + [문제 상태] + [행정 조치 의도]
- keyword_query: BM25용 짧은 키워드열(띄어쓰기 구분)
- expansion_queries: 의미는 같고 표현만 다른 질의 2~3개
- 위치가 없으면 위치 표현을 넣지 않는다.

4) 필터 힌트
- domain_hint는 입력 근거가 충분할 때만 제안, 아니면 "공통"
- confidence는 0~1 범위 (입력 명확성 기준)

[출력 JSON 스키마]
{{
  "intent_summary": "핵심 민원 의도 1문장",
  "entities": {{
    "target": ["민원 대상"],
    "issue_state": ["문제 상태/행위"],
    "location_clues": ["입력에 명시된 위치 단서"],
    "action_clues": ["처리 관련 단서"]
  }},
  "retrieval_keywords": ["키워드"],
  "synonym_keywords": ["동의어/유사어"],
  "must_keywords": ["빠지면 안 되는 핵심어"],
  "optional_keywords": ["있으면 좋은 보조어"],
  "keyword_query": "BM25용 키워드열",
  "retrieval_query": "하이브리드 검색용 대표 질의 1문장",
  "expansion_queries": ["대체 질의1", "대체 질의2", "대체 질의3"],
  "domain_hint": "교통 | 환경미화 | 안전건설 | ... | 공통",
  "confidence": 0.0
}}
""".strip()


def format_user_text_for_rag_extraction(*, title: str, content: str) -> str:
    return f"title:{title.strip()}\ncontent:{content.strip()}"


def build_rag_extraction_prompt(*, title: str, content: str) -> str:
    user_text = format_user_text_for_rag_extraction(title=title, content=content)
    return RAG_EXTRACTION_PROMPT.format(user_text=user_text)
