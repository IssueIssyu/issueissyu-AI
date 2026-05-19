from __future__ import annotations

import json

from app.schemas.ComplaintEmailDTO import ComplaintEmailLlmBundle

_OPINION_SECTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "disposition_title": {
            "type": "string",
            "description": "1. 예정된 처분의 제목 칸에 들어갈 내용(민원 대상·쟁점 요약)",
        },
        "opinion": {
            "type": "string",
            "description": (
                "3. 의견 본문. 서두 인사 후 반드시 "
                "1. 사실관계 / 2. 근거 / 3. 유사사례 / 4. 요청사항(가·나·다) 순서"
            ),
        },
        "other": {
            "type": "string",
            "description": "4. 기타(첨부·참고 사항)",
        },
        "submitter_name": {"type": "string", "description": "성명(명칭), 모르면 빈 문자열"},
        "submitter_address": {"type": "string", "description": "주소, 모르면 빈 문자열"},
        "submitter_phone": {"type": "string", "description": "전화, 모르면 빈 문자열"},
    },
    "required": ["disposition_title", "opinion", "other"],
    "additionalProperties": False,
}


def complaint_opinion_prompt(bundle: ComplaintEmailLlmBundle) -> str:
    payload = bundle.model_dump(mode="json")
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    schema_text = json.dumps(_OPINION_SECTIONS_SCHEMA, ensure_ascii=False, indent=2)
    return f"""
[역할]
「의견제출서」(행정절차법 양식) 각 칸에 들어갈 문장만 JSON으로 작성한다.
HTML·마크다운은 출력하지 않는다.

[양식 구조 — 반드시 이 항목만 채움]
- disposition_title → 표 「1. 예정된 처분의 제목」
- opinion → 표 「3. 의견」(아래 [opinion 본문 형식]을 반드시 따름)
- other → 「4. 기타」(첨부·참고 문구만. 업로드 사진은 서버가 같은 칸에 자동 삽입)
- submitter_name / submitter_address / submitter_phone → 알 때만(없으면 "")

[opinion 본문 형식 — 필수]
opinion 필드는 아래 순서·제목을 그대로 사용한다. 번호·제목 문구를 생략·변경하지 않는다.

1) 서두(1~2문장, 줄바꿈 후 본문 시작):
   귀 부서의 무궁한 발전을 기원합니다. 본 의견제출자는 다음과 같은 사유로 의견을 제출합니다.

2) 본문 4개 절 — 각 절은 「번호. 제목」 한 줄 다음에 내용(2문장 이상 권장):
   1. 사실관계
   (이슈 핀·사진·VLM 분석에 근거한 객관적 사실만. 현장 상황·피해·지속성 등)

   2. 근거
   (관련 법령·조례·행정 원칙 등 근거. rag_hits·입력 맥락을 활용. 확정적 판결 표현은 피함)

   3. 유사사례
   (rag_hits 또는 일반적 행정 사례 형태로 서술. 구체적 판례번호·미확인 사건명은 쓰지 않음)

   4. 요청사항
   (행정기관에 구체적으로 요청. 하위 항목은 반드시 가·나·다 로 구분, 각 1문장 이상)
   가. (신속 수거·처리 등 1차 조치)
   나. (재발 방지·계도·단속 등 2차 조치)
   다. (주민 생활·통행·환경 보장 등 총괄 요청)

3) 줄바꿈: 절 사이·서두와 「1. 사실관계」 사이는 실제 엔터로 구분한다.

4) opinion 안에 「4. 기타」 내용·첨부 사진 안내는 넣지 않는다(기타 칸·서버 첨부 담당).

[opinion 작성 예시 — 형식만 참고, 내용은 입력에 맞게 새로 작성]
귀 부서의 무궁한 발전을 기원합니다. 본 의견제출자는 다음과 같은 사유로 의견을 제출합니다.
1. 사실관계
(해당 민원의 사실관계)
2. 근거
(법령·행정상 근거)
3. 유사사례
(유사 민원·조치 사례)
4. 요청사항
가. (요청 1)
나. (요청 2)
다. (요청 3)

[금지]
- 서울시·서울특별시 등 특정 지자체명
- 확인되지 않은 사실·법적 확정 판단
- 문자열에 리터럴 "\\n" 금지 — 줄바꿈은 실제 엔터
- wowform 등 워터마크 문구

[입력 JSON]
{json_text}

[출력 JSON 스키마]
{schema_text}
""".strip()
