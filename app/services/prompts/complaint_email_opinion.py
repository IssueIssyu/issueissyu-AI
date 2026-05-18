from __future__ import annotations

import json

from app.schemas.ComplaintEmailDTO import ComplaintEmailLlmBundle


def complaint_opinion_prompt(bundle: ComplaintEmailLlmBundle) -> str:
    payload = bundle.model_dump(mode="json")
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"""
        [역할]
        서울시 민원·청원 의견서 양식에 맞는 HTML 문서를 작성한다.
        입력 JSON의 사실만 사용하고, 확인되지 않은 내용·법적 판단·과장 표현은 넣지 않는다.
        
        [입력 JSON]
        {json_text}
        
        [출력 규칙]
        - 반드시 완전한 HTML5 문서 한 덩어리만 출력한다 (<!DOCTYPE html> ~ </html>).
        - 인라인 CSS만 사용한다. 외부 스크립트·이미지 URL은 넣지 않는다.
        - 섹션: 제목, 민원 요지, 현장 상황, 관련 법령·유사 사례 요약(RAG), 개선 요청, 첨부 사진 설명.
        - 표·목록을 적절히 사용해 공무원이 읽기 쉽게 구성한다.
        - 개인정보(번호판 전체, 얼굴 식별 정보)는 마스킹하거나 생략한다.
        - 마크다운 코드펜스나 설명 문장 없이 HTML만 출력한다.
    """.strip()
