# 프롬프트 패키지 + 서비스 레이어 리팩토링 상세 가이드

이 문서는 이번 리팩토링에서 변경된 내용을 **프롬프트 패키지 구조 + 서비스 레이어 동작 기준**으로 팀원이 바로 이해하고, 다음 작업(기능 추가/버그 수정/리뷰)을 안전하게 진행할 수 있도록 정리한 문서다.

---

## 0) 문서 대상

- 백엔드 API/서비스 레이어 작업자
- 프롬프트 튜닝 및 RAG 품질 개선 작업자
- PR 리뷰어(영향 범위 파악 목적)

---

## 1) 이번 리팩토링의 핵심 목표

기존에는 프롬프트 소스가 서비스 루트에 흩어져 있어 책임 경계가 모호했다.  
이번 변경으로 아래를 달성했다.

1. 프롬프트 소스를 `app/services/prompts`로 완전 통합
2. 서비스 코드의 프롬프트 import 진입점을 일관화
3. `IssueService`/`VLMService`에서 프롬프트와 스키마 상수의 결합 관계를 명시화
4. 이후 프롬프트 추가 시 모듈 단위 확장이 가능하도록 구조 고정

---

## 2) Before vs After

### Before (개념)

```text
app/services/
├── vlm_prompt.py
├── issue_pin_prompt.py
├── IssueService.py
└── VLMService.py (또는 관련 경로)
```

### After (현재)

```text
app/services/
├── IssueService.py
├── internal/
│   └── ai/
│       └── VLMService.py
└── prompts/
    ├── __init__.py
    ├── vlm.py
    ├── issue_pin.py
    └── rag_extraction.py
```

삭제된 파일:
- `app/services/vlm_prompt.py`
- `app/services/issue_pin_prompt.py`

즉, 프롬프트 원문은 이제 `app/services/prompts/*`만 수정하면 된다.

---

## 3) 폴더/모듈 책임 분리

## `app/services/prompts/vlm.py`

역할:
- 이미지 기반 민원 분석(VLM) 프롬프트 본문
- VLM 응답 JSON 스키마와 동기화해야 하는 enum성 상수 제공

주요 export:
- `VLM_CATEGORY_TYPES`
- `VLM_ADMIN_DOMAINS`
- `VLM_ERROR_CODES`
- `VLM_PRIVACY_NOTES`
- `VLM_LOCATION_VERIFICATION_STATUSES`
- `build_vlm_prompt(...)`

중요 포인트:
- `VLMService`의 `VLM_RESPONSE_SCHEMA`는 위 상수에 직접 의존한다.
- 상수/프롬프트 문구 수정 시 스키마 검증과 함께 변경해야 한다.

## `app/services/prompts/issue_pin.py`

역할:
- VLM 결과 + RAG 근거를 바탕으로 커뮤니티 핀 문구를 생성하는 프롬프트

주요 함수:
- `format_user_text_for_pin(title, content)`
- `format_retrieved_docs_for_pin(rag_hits, ...)`
- `build_issue_pin_prompt(...)`
- `build_issue_pin_prompt_from_pipeline_bundle(bundle, ...)`

중요 포인트:
- `IssueService`는 최종적으로 `bundle` 기반 빌더를 사용한다.
- 입력 계약(bundle key)이 깨지면 프롬프트 생성 품질이 바로 저하된다.

## `app/services/prompts/rag_extraction.py`

역할:
- 제목/본문만으로 RAG retrieval에 유리한 구조화 출력(쿼리/키워드/확장 질의)을 유도

주요 함수:
- `format_user_text_for_rag_extraction(title, content)`
- `build_rag_extraction_prompt(title, content)`

현재 상태:
- 패키지에 포함되어 재사용 가능
- 메인 파이프라인(IssueService)의 기본 경로에는 아직 직접 연결 전

## `app/services/prompts/__init__.py`

역할:
- 모듈별 함수/상수를 한 곳에서 재-export
- 서비스 레이어에서는 가급적 `from app.services.prompts import ...` 사용

---

## 4) 서비스 레이어 변경 상세

## 4-1) `IssueService` 변경점

현재 import:
- `from app.services.prompts import build_issue_pin_prompt_from_pipeline_bundle`
- 내부 AI/Geo 서비스는 `app.services.internal.*` 경로 사용

핵심 동작 흐름 (`issue_pin_ai_make`):

1. 입력 검증
- 이미지가 없으면 `VALIDATION_ERROR`

2. 사용자 텍스트 표준화
- `_user_content_from_request`로 아래 고정 포맷 생성
  - `title:{...}\ncontent:{...}\n`

3. 이미지 위치 메타 준비
- `_extract_locations_from_images`에서 이미지별 EXIF/역지오코딩 주소 추출

4. VLM 분석 호출
- `self._vlm_service.analyze_image(...)`
- 결과: `vlm_result` (`category`, `retrieval_query`, `confidence_score` 등)

5. RAG 질의 결정
- 1순위: `vlm_result["retrieval_query"]`
- fallback: `title/content` 원문

6. RAG 필터 생성
- `_build_rag_metadata_filters`
- `category.domain`이 유효하고 `"공통"`이 아니면 metadata filter 적용

7. 벡터 검색
- `VectorDomain.COMPLAINT`
- `similarity_top_k=10`
- filters 포함 가능

8. RAG 결과 직렬화
- `_rag_hits_to_dicts`로 LLM 프롬프트에 주입 가능한 형태로 변환

9. 핀 프롬프트 조립 + 생성
- `bundle` 구성 후 `build_issue_pin_prompt_from_pipeline_bundle(bundle)`
- `IssuePinLLMService.generate_pin_text(...)` 호출

10. 응답 조립
- `IssueAnalysisResult`
- `reliability`, `reliability_basis`는 `vlm_result` 기준으로 계산

### 왜 중요한가

- 프롬프트 생성이 서비스 로직의 후반부(검색 결과 반영 단계)에 위치하므로,  
  프롬프트 모듈 변경이 실제 사용자 결과 문장에 직접 반영된다.
- 특히 `bundle` 스키마는 `IssueService`와 `issue_pin.py` 사이의 계약이다.

---

## 4-2) `internal/ai/VLMService` 변경점

현재 import:
- `from app.services.prompts import ... build_vlm_prompt`

변경의 의미:
- 프롬프트 본문/상수의 소스가 `prompts.vlm`로 통합되어  
  응답 스키마 enum과 프롬프트 규칙의 기준점이 일치한다.

핵심 동작:

1. 업로드 이미지별 MIME/바이트 검증
2. 이미지별 사진 메타 주소 문자열 정규화 (`coerce_photo_address`)
3. `build_vlm_prompt(...)` 호출
4. Gemini JSON schema 강제 응답 (`response_schema=VLM_RESPONSE_SCHEMA`)
5. 파싱/정규화 (`_normalize`)
   - validity/에러코드 보정
   - location_verification 기본값 보정
   - 위치 정보 없을 때 retrieval_query/keywords 위치어 제거

### 왜 중요한가

- VLM 품질 이슈의 상당수는 프롬프트/스키마 불일치에서 발생한다.
- 이제 상수 기준이 한 모듈에 모여 있어 drift를 줄일 수 있다.

---

## 4-3) `app/core/deps.py` 관점 (DI 연결)

현재 `deps.py` 기준:
- `IssueService`는 `get_issue_service`에서 조립
- `VLMService`, `IssuePinLLMService`, `ImageExifLocationResolveService`, `VectorStoreService`를 주입

즉, 이번 리팩토링은 DI 시그니처를 깨지 않고 **import 경로와 책임 구조만 정리**한 성격이다.

---

## 5) 실제 데이터 흐름 예시 (엔드투엔드)

아래는 이해를 위한 예시 시나리오다.

입력:
- title: `횡단보도 앞 불법주차`
- content: `차량이 횡단보도 진입부를 막고 있어요`
- image: 1장
- user GPS: `37.566500,126.978000`

흐름:

1. `IssueService._user_content_from_request`
```text
title:횡단보도 앞 불법주차
content:차량이 횡단보도 진입부를 막고 있어요
```

2. `VLMService.analyze_image` 수행 후 예시 결과(요약)
```json
{
  "category": { "type": "불법주정차", "domain": "교통" },
  "retrieval_query": "횡단보도 앞 불법주차 차량 이동 조치 요청",
  "retrieval_keywords": ["횡단보도", "불법주정차", "주차위반", "보행안전"],
  "confidence_score": 0.86
}
```

3. `IssueService._build_rag_metadata_filters`
- domain = `교통`이므로 category filter 적용

4. `VectorStoreService.aretrieve(...)`
- 교통 카테고리 민원 문서 우선 검색

5. `bundle` 생성 후 `build_issue_pin_prompt_from_pipeline_bundle(bundle)` 호출

6. 최종 핀 문구 생성
- 커뮤니티 톤/금지 규칙/입력 기반 원칙을 반영한 단문 출력

---

## 6) 팀원이 자주 헷갈리는 포인트

1. "프롬프트 어디서 고치나?"
- 무조건 `app/services/prompts/*`

2. "RAG 추출 프롬프트는 어디?"
- `app/services/prompts/rag_extraction.py`

3. "IssueService에서 프롬프트 함수 뭘 쓰나?"
- 현재는 `build_issue_pin_prompt_from_pipeline_bundle`

4. "VLM enum 값 바꿔도 되나?"
- 가능하나 `VLMService.VLM_RESPONSE_SCHEMA`와 같이 검토해야 함

---

## 7) 협업 규칙 (강력 권장)

## import 규칙

- 권장:
  - `from app.services.prompts import ...`
- 필요 시 모듈 직접 import:
  - `from app.services.prompts.vlm import ...`
  - `from app.services.prompts.issue_pin import ...`
  - `from app.services.prompts.rag_extraction import ...`

지양:
- 서비스 코드 내 프롬프트 문자열 하드코딩
- 프롬프트 파일을 `app/services` 루트로 재추가

## 커밋 규칙

- 프롬프트 텍스트 변경과 서비스 로직 변경은 가능한 분리 커밋
- PR 설명에 최소 포함:
  - 변경한 프롬프트 파일
  - 입력/출력 계약 변화(JSON 키 변화 포함)
  - 품질 기대 효과(예: 검색 재현율, 오탐 감소)

---

## 8) 장애 대응 체크리스트

- [ ] `rg "issue_pin_prompt|vlm_prompt"` 결과가 구 경로 import를 포함하지 않는가
- [ ] `app/services/prompts/__init__.py`에 export 누락이 없는가
- [ ] `IssueService` bundle key 변경 시 `issue_pin.py` 빌더가 같은 key를 읽는가
- [ ] `VLM_CATEGORY_TYPES` 등 enum 변경 시 `VLM_RESPONSE_SCHEMA`와 일치하는가
- [ ] lint/compile 통과 여부

---

## 9) 다음 확장 작업 가이드

다음 단계로 추천되는 작업:

1. `rag_extraction.py`를 `IssueService` 검색 쿼리 생성 경로에 옵션 연결
2. A/B 방식으로
   - 기존: VLM retrieval_query
   - 신규: rag_extraction 기반 retrieval_query
   를 비교 측정
3. `rag/scripts/test_*` 스크립트에 회귀 확인 케이스 추가

---

## 10) 한 줄 결론

이번 리팩토링 이후 기준은 단순하다:

- **프롬프트는 `app/services/prompts`에서만 관리**
- **서비스는 그 패키지를 import해서 조립만 수행**
- **품질 튜닝은 프롬프트 모듈 단위로 안전하게 반복**

