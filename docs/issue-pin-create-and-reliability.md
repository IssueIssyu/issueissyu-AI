# 이슈 핀 게시·비동기 신뢰도 — 변경 사항 전체 문서

> 브랜치: `fix/53-ai-auto-issue-write`  
> 작성 목적: 이번 작업에서 추가·수정된 **모든** API, 서비스, 모델, 설정, 프롬프트, 운영 이슈를 한 문서에 정리  
> 대상 독자: 백엔드·프론트·QA·운영

---

## 목차

1. [요약](#1-요약)
2. [배경 및 설계 원칙](#2-배경-및-설계-원칙)
3. [전체 흐름도](#3-전체-흐름도)
4. [API 명세](#4-api-명세)
5. [응답 DTO 및 상태 값](#5-응답-dto-및-상태-값)
6. [동기 게시 경로 (POST /issues/pin)](#6-동기-게시-경로-post-issuespin)
7. [비동기 신뢰도 파이프라인](#7-비동기-신뢰도-파이프라인)
8. [confidence_content (시민용 근거 문구)](#8-confidence_content-시민용-근거-문구)
9. [환경 변수 (.env)](#9-환경-변수-env)
10. [데이터베이스](#10-데이터베이스)
11. [신규 파일 목록 및 역할](#11-신규-파일-목록-및-역할)
12. [수정 파일 목록 및 변경 내용](#12-수정-파일-목록-및-변경-내용)
13. [Gemini 재시도·Fallback·타임아웃](#13-gemini-재시도fallback타임아웃)
14. [로깅 가이드](#14-로깅-가이드)
15. [에러·성공 코드](#15-에러성공-코드)
16. [의존성 (requirements.txt)](#16-의존성-requirementstxt)
17. [프론트엔드 연동 체크리스트](#17-프론트엔드-연동-체크리스트)
18. [트러블슈팅 (운영에서 겪은 이슈)](#18-트러블슈팅-운영에서-겪은-이슈)
19. [미구현·향후 작업](#19-미구현향후-작업)
20. [변경 파일 인덱스 (전체)](#20-변경-파일-인덱스-전체)

---

## 1. 요약

| 구분 | 내용 |
|------|------|
| **핵심 기능** | 이슈 핀 **실제 게시** (`POST /issues/pin`), **상세 조회**, **신뢰도 폴링** |
| **미리보기** | 기존 `POST /issues/pin/ai` 유지 (DB 저장 없음, AI 문구만) |
| **게시 정책** | 신뢰도가 낮아도 **항상 201** — `ISSUE_4221`로 게시 거절 **하지 않음** |
| **이미지** | 0~N장, S3 `issueimage/` 경로, **동기 업로드** 후 201 |
| **신뢰도** | **비동기** VLM + RAG → `issue_pin.issue_confidence`, `confidence_content` UPDATE |
| **근거 문구** | 일반 시민이 읽는 한국어 bullet, 줄바꿈 `\n` 유지 |
| **S3 ↔ 신뢰도** | 백그라운드는 **메모리 스냅샷이 아니라 DB `pin_image` → S3 다운로드** 로 이미지 로드 |

---

## 2. 배경 및 설계 원칙

### 2.1 사용자 여정 (2단계)

1. **미리보기**: `POST /issues/pin/ai` → AI가 제안한 `title` / `content`
2. **편집**: 프론트에서 사용자가 문구 수정
3. **게시**: `POST /issues/pin` → 최종 문구·좌표·(선택) 이미지 저장
4. **폴링**: `GET /issues/pin/{id}/reliability` 또는 상세 API로 신뢰도 완료 확인

### 2.2 서버가 하지 않는 일

- 게시 시 핀 LLM으로 문구 **재작성하지 않음** (`_tune_title` 등 미사용)
- 게시 API에서 `/pin/ai` **다시 호출하지 않음**
- 신뢰도 낮다고 게시 **거절하지 않음** (`ISSUE_4221` 미사용)

### 2.3 서버가 하는 일

- 최종 `title` / `content`를 **strip·길이 검증만** 하고 `pin`에 저장
- Spring 코어 `GET /api/location/resolve`로 `location_id`, `detail_address` 확보
- 이미지 S3 업로드 + `pin_image` INSERT (**동기**)
- `issue_pin_state = BEFORE_PROGRESS` 로 생성
- 백그라운드에서 신뢰도 분석 후 `issue_confidence`, `confidence_content` UPDATE

### 2.4 S3 동기화 변경의 이유 (중요)

**초기 설계**: S3 업로드를 백그라운드에서 처리하고, 같은 작업 안에서 VLM까지 수행.

**변경 후**: 사용자 요청으로 S3·`pin_image` 저장을 **동기(201 전)** 로 이동.

**발생했던 문제**: 백그라운드 신뢰도만 요청 시점 **메모리 스냅샷**에 의존 → `BackgroundTasks`·긴 바이트 배열·Gemini 503 재시도와 겹치며 `confidence_content`가 **NULL**로 남는 사례 다수.

**해결**: 백그라운드는 **`pin_image.pin_s3_key` → `S3Util.download_bytes`** 로 이미지를 다시 읽은 뒤 VLM에 전달. S3 업로드가 끝난 뒤에만 신뢰도 job이 의미 있게 동작.

---

## 3. 전체 흐름도

### 3.1 게시 + 신뢰도 (현재 구현)

```mermaid
sequenceDiagram
    participant FE as 프론트
    participant API as POST /issues/pin
    participant Core as Spring location/resolve
    participant S3 as AWS S3 issueimage/
    participant DB as PostgreSQL
    participant BG as BackgroundTasks 신뢰도

    FE->>API: title, content, tone, lat, lng, images[]
    API->>Core: resolve_wgs84(lat, lng)
    Core-->>API: locationId, address
    API->>DB: pin, issue_pin, pin_location (flush)
  Note over API,DB: issue_confidence=NULL
    API->>S3: upload_bytes (동기, 병렬 gather)
    API->>DB: pin_image rows
    API->>DB: commit
    API-->>FE: 201 IssuePinHomeDetailResponse
    API->>BG: IssuePinReliabilityJob (pin_id만, 이미지는 S3에서 로드)

    BG->>DB: pin_image 목록 조회
    BG->>S3: download_bytes per key
    BG->>BG: RAG (벡터 검색, planner 생략 가능)
    BG->>BG: EXIF + location resolve per image
    BG->>BG: VLM analyze_image / text_only
    BG->>DB: UPDATE issue_confidence, confidence_content
```

### 3.2 신뢰도 파이프라인 단계

| 순서 | 단계 | 타임아웃(기본) | 설명 |
|------|------|----------------|------|
| 1 | RAG | 45초 | planner 생략 시 title+content로 벡터 검색만 |
| 2 | S3 | (전체 한도 내) | `pin_image` 행 기준 S3 다운로드 |
| 3 | EXIF | (전체 한도 내) | 사진별 EXIF → 코어 주소 resolve |
| 4 | VLM | 150초 | 이미지 있으면 `analyze_image`, 없으면 `analyze_text_only` |
| 5 | PERSIST | - | 점수 + 시민용 `confidence_content` 저장 |
| - | **전체** | **240초** | 초과 시 실패 문구 저장 (`score=0.0`) |

---

## 4. API 명세

공통: `Authorization: Bearer {token}` (또는 쿠키), prefix `/issues`

### 4.1 `GET /issues/tone-types`

톤 enum 목록.

**응답 예**: `[{ "key": "NONE", "label": "없음" }, ...]`

---

### 4.2 `POST /issues/pin/ai` (기존, 유지)

AI 미리보기. **DB 저장 없음.**

| Form 필드 | 필수 | 설명 |
|-----------|------|------|
| title | O | 초안 제목 |
| content | O | 초안 본문 |
| tone | X | 기본 `없음` (한국어 value) |
| latitude | O | 위도 |
| longitude | O | 경도 |

**처리**: RAG planner → 벡터 검색 → `IssuePinLLMService` → `IssueAnalysisResult { title, content }`

---

### 4.3 `POST /issues/pin` (신규 핵심)

실제 게시.

| Form 필드 | 필수 | 설명 |
|-----------|------|------|
| title | O | **최종** 제목 (AI 초안 수정본 가능) |
| content | O | **최종** 본문 |
| tone | O | `ToneType` (한국어 value) |
| latitude | O | 위도 |
| longitude | O | 경도 |
| images | X | 0~N장 multipart 파일 |

**HTTP**: `201 Created`  
**성공 코드**: `COMMON_201`  
**응답 body**: `IssuePinHomeDetailResponse` (camelCase, Spring 홈 상세 형태)

**동기 처리 순서** (`IssueService.create_issue_pin`):

1. payload 검증 (제목/본문/이미지 개수)
2. 사용자 존재 확인
3. `LocationResolveClient.resolve_wgs84` → 실패 시 422
4. `_snapshot_upload_images` — multipart → `ImageSnapshot(bytes)` 
5. `Pin` INSERT
6. `IssuePin` INSERT (`issue_confidence=None`, `confidence_content=None`, `BEFORE_PROGRESS`)
7. `PinLocation` INSERT (`location_id`, `detail_address`, `pin_point` WKT)
8. `_upload_pin_images_sync` — S3 `issueimage/{timestamp}-{uuid}.{ext}` + `pin_image`
9. `commit`
10. `IssuePinBackgroundRunner.schedule(job, background_tasks=...)`
11. 홈 상세 응답 조립 (`reliabilityStatus=pending`)

---

### 4.4 `GET /issues/pin/{issue_pin_id}`

핀 홈 상세.

**성공 코드**: `ISSUE_2001`  
**응답**: `IssuePinHomeDetailResponse`

**로딩**: `IssuePinRepo.get_by_issue_pin_id` + `selectinload(pin, pin_images, pin_location, user)`

---

### 4.5 `GET /issues/pin/{issue_pin_id}/reliability`

신뢰도 전용 폴링.

**성공 코드**: `ISSUE_2002`  
**응답**: `IssuePinReliabilityResponse`

| 필드 | 설명 |
|------|------|
| issueConfidence | 0.0~1.0 또는 null (분석 전) |
| confidenceContent | 시민용 markdown bullet 문자열 |
| reliabilityStatus | pending / completed / failed |
| imageUploadStatus | none / completed 등 |

---

## 5. 응답 DTO 및 상태 값

### 5.1 `ReliabilityStatus`

| 값 | 의미 |
|----|------|
| `pending` | `issue_confidence`·`confidence_content` 모두 비어 있음 |
| `completed` | 분석 완료 (점수·근거 있음) |
| `failed` | 분석 실패 안내 문구 저장됨 (`FAILED_RELIABILITY_BASIS` 패턴) |

판별: `IssueService._derive_reliability_status` + `is_failed_reliability_content()`

### 5.2 `ImageUploadStatus`

| 값 | 의미 |
|----|------|
| `none` | 이미지 없이 게시 |
| `pending` | (레거시 호환) 이미지 없고 신뢰도 pending |
| `completed` | `pin_image` 1건 이상 |
| `failed` | (예약) |

현재 게시 API는 이미지 있으면 동기 업로드 후 바로 `completed`.

### 5.3 `IssuePinHomeDetailResponse` 주요 필드 (camelCase)

`pinId`, `issuePinId`, `pinTitle`, `pinContent`, `issuePinState`, `pinDetailAddress`, `pinImageUrls[]`, `reliabilityStatus`, `imageUploadStatus`, `issueConfidence`는 상세에 직접 넣지 않고 reliability API 사용 권장.

---

## 6. 동기 게시 경로 (`POST /issues/pin`)

### 6.1 이미지 스냅샷

- `_snapshot_upload_images`: `UploadFile.read()` → `ImageSnapshot(data, content_type, filename)`
- 빈 파일·비이미지 MIME → 422 / 415

### 6.2 S3 업로드

- prefix: **`issueimage`** (`S3_ISSUE_IMAGE_PREFIX`)
- 메서드: `S3Util.upload_bytes` (신규)
- 키 형식: `issueimage/{UTC timestamp}-{uuid}{ext}`
- 병렬: `asyncio.gather` per snapshot
- DB: `PinImageRepo.save` — `pin_s3_key`, `pin_s3_url`, `is_main` (첫 장 main)

### 6.3 위치

- `pin_location.location_id` = Spring resolve 응답 `locationId`
- `detail_address` = resolve `address` (최대 150자)
- `pin_point` = `wkt_point_from_wgs84` (`app/utils/geo.py`, SRID 4326)

### 6.4 tone_type DB 저장

- API: `ToneType` 한국어 **value** (Form)
- ORM/DB: enum **name** 저장 (`NONE`, `DISCOMFORT_COMPLAINT`, …)
- DB check constraint에 모든 name 허용 필요 (로컬·AWS 각각 마이그레이션 이슈 있었음)

---

## 7. 비동기 신뢰도 파이프라인

구현: `app/services/internal/IssuePinBackgroundRunner.py`

### 7.1 Job 스키마 (`IssuePinReliabilityJob`)

```python
@dataclass
class IssuePinReliabilityJob:
    issue_pin_id: int
    pin_id: int
    title: str
    content: str
    user_gps: str          # "lat,lng" 6자리
    user_address: str | None
```

**주의**: `image_snapshots` 필드 **제거됨** — 이미지는 `pin_id`로 S3에서 로드.

### 7.2 스케줄링

- FastAPI `BackgroundTasks.add_task(run_reliability_job, job)` **우선**
- fallback: `asyncio.create_task` + 모듈 레벨 `_RELIABILITY_PIPELINE_TASKS` set (GC 방지)

### 7.3 단계별 처리

1. **RAG** — `build_rag_context_block_for_reliability`
   - `ISSUE_PIN_RELIABILITY_SKIP_RAG_PLANNER=true`(기본): planner **생략**, `title:{title}\ncontent:{content}` 로 벡터 검색
   - planner 사용 시 Gemini 503 재시도로 **수분** 지연 가능 → 기본 생략 권장

2. **S3** — `_load_snapshots_from_s3(pin_id)`
   - `pin_image` ORDER BY `is_main DESC`, `pin_image_id ASC`
   - `S3Util.download_bytes(pin_s3_key)`

3. **EXIF** — `_build_vlm_inputs_from_snapshots` (이미지별 `asyncio.gather`)
   - `ImageExifLocationResolveService.extract_and_resolve`
   - `ImageWithLocation(image=UploadFile(BytesIO), address=...)`

4. **VLM** — `VLMService.analyze_image` 또는 `analyze_text_only`
   - primary: `GEMINI_VLM_MODEL` (기본 `gemini-2.5-flash`)
   - fallback: `GEMINI_VLM_FALLBACK_MODELS` 중 **1개만** (신뢰도 파이프라인)
   - `max_attempts`: `ISSUE_PIN_RELIABILITY_GEMINI_MAX_ATTEMPTS` (기본 2)

5. **근거 조립** — `resolve_confidence_basis_markdown` → `format_confidence_content_for_user`

6. **저장** — `IssuePinRepo.update_confidence` (SQL `UPDATE`, 별도 `AsyncSessionLocal`)

### 7.4 실패 시

- 예외·타임아웃·VLM 전체 실패 → `finally`에서 `_persist_failure_confidence`
- `issue_confidence = 0.0`
- `confidence_content = FAILED_RELIABILITY_BASIS` (시민용 문구)

---

## 8. confidence_content (시민용 근거 문구)

구현: `app/services/internal/issue_confidence_basis.py`

### 8.1 저장 형식

- Plain text + markdown bullet (`- `)
- 줄바꿈: **실제 `\n` 문자** (JSON 응답 시 `\\n`)
- 요약 한 줄 + bullet 목록

**성공 예시**:

```
제출하신 글·사진·위치 정보가 서로 잘 맞는 편으로 보여요.
- 무엇을 제보하셨는지 글만 봐도 이해하기 쉽습니다.
- 사진에서도 글과 같은 상황이 보입니다.
- 지도에 표시한 위치와 사진을 찍은 곳이 같은 동네 수준으로 보입니다.
```

### 8.2 실패 예시

```
- 지금은 이 제보에 대한 AI 검토 결과를 불러오지 못했어요.
- 잠시 후 다시 열어보시거나, 사진과 글이 잘 보이는지 확인해 주세요.
```

### 8.3 점수 구간별 요약 문장

| score | intro 문장 |
|-------|------------|
| ≥ 0.75 | 제출하신 글·사진·위치 정보가 서로 잘 맞는 편으로 보여요. |
| ≥ 0.45 | 전반적으로 이해하기 쉬운 제보예요. 아래 내용을 함께 참고해 주세요. |
| < 0.45 | 확인이 더 필요해 보이는 제보예요. 아래 내용을 참고해 주세요. |

### 8.4 프롬프트 규칙 (VLM / text-only)

- `app/services/prompts/confidence_basis.py` — `CONFIDENCE_BASIS_PROMPT_BLOCK`
- `app/services/prompts/vlm.py` — 이미지 VLM용 신뢰도 근거 섹션
- `app/services/prompts/issue_reliability_text.py` — 이미지 없을 때

금지: EXIF, RAG, 메타데이터, GPS, 핀, JSON, axis 이름 노출

### 8.5 후처리

- `sanitize_user_facing_basis_text`: **한 줄** 기술 용어 치환 (줄바꿈 유지)
- `normalize_display_line_breaks`: bullet마다 한 줄
- `render_confidence_basis_markdown`: 축 라벨(`제보 내용:`) **표시 안 함**

### 8.6 프론트 표시

`confidenceContent`는 **`\n`을 줄바꿈으로 렌더**해야 함.

- React: `white-space: pre-line` 또는 split `\n`
- Flutter: 문자열 그대로 `Text` with multiline

---

## 9. 환경 변수 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GEMINI_API_KEY` | - | 필수 (VLM·RAG·임베딩) |
| `GEMINI_VLM_MODEL` | `gemini-2.5-flash` | 신뢰도 VLM (3.1-pro는 503·지연 多) |
| `GEMINI_VLM_FALLBACK_MODELS` | `gemini-2.5-flash,gemini-2.5-pro` | 콤마 구분 |
| `GEMINI_PIN_TEXT_MODEL` | `gemini-2.5-flash` | /pin/ai 핀 LLM |
| `GEMINI_PIN_TEXT_FALLBACK_MODELS` | `gemini-2.5-flash-lite,gemini-2.0-flash-lite` | |
| `LOCATION_CORE_BASE_URL` | `http://localhost:8080` | Spring resolve |
| `LOCATION_RESOLVE_TIMEOUT_SECONDS` | `10.0` | |
| `AWS_BUCKET` | - | S3 버킷 |
| `AWS_ACCESS_KEY` / `AWS_SECRET_KEY` / `AWS_REGION` | - | S3 |
| `ISSUE_PIN_MAX_IMAGES` | `5` | 게시당 최대 이미지 |
| `ISSUE_CONFIDENCE_BASIS_MAX_CHARS` | `2000` | 근거 최대 길이 |
| `ISSUE_PIN_RELIABILITY_PIPELINE_TIMEOUT_SECONDS` | `240` | 전체 파이프라인 |
| `ISSUE_PIN_RELIABILITY_SKIP_RAG_PLANNER` | `true` | planner 생략 |
| `ISSUE_PIN_RELIABILITY_GEMINI_MAX_ATTEMPTS` | `2` | 모델당 재시도 |
| `ISSUE_PIN_RELIABILITY_RAG_TIMEOUT_SECONDS` | `45` | RAG 단계 |
| `ISSUE_PIN_RELIABILITY_VLM_TIMEOUT_SECONDS` | `150` | VLM 단계 |
| `PIN_TITLE_MAX_LENGTH` | `100` | |
| `PIN_CONTENT_MAX_LENGTH` | `10000` | |

---

## 10. 데이터베이스

### 10.1 관련 테이블

| 테이블 | 역할 |
|--------|------|
| `pin` | 제목·본문·톤·좋아요·조회수 |
| `issue_pin` | 상태·신뢰도·청원 수 |
| `pin_location` | `location_id`, `detail_address`, `pin_point` |
| `pin_image` | S3 key/url, `is_main` |
| `pin_like` | (모델/Repo 추가, 상세 응답 `isLike`용) |
| `community` | (모델/Repo 추가, `communityId`용) |

### 10.2 `issue_pin` 신뢰도 컬럼

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `issue_confidence` | `double precision` NULL | 0.0~1.0 |
| `confidence_content` | `text` NULL | 시민용 근거 (줄바꿈 포함) |

생성 시: 둘 다 `NULL`, `reliabilityStatus=pending`

### 10.3 `pin_location.detail_address`

- NOT NULL
- 게시 시 Spring resolve `address` 저장 (150자 truncate)

### 10.4 `pin_tone_type_check`

- DB에는 enum **name** (`NONE`, …) 저장
- API Form에는 한국어 **value** (`없음`, …)

---

## 11. 신규 파일 목록 및 역할

| 파일 | 역할 |
|------|------|
| `app/schemas/issue_pin_job.py` | `ImageSnapshot`, `IssuePinReliabilityJob` |
| `app/services/internal/IssuePinBackgroundRunner.py` | 비동기 신뢰도 파이프라인 전체 |
| `app/services/internal/ai/gemini_retry.py` | Gemini 공통 재시도·fallback·로깅 |
| `app/services/internal/issue_confidence_basis.py` | 근거 markdown 조립·시민용 문구·실패 상수 |
| `app/services/internal/issue_rag_context.py` | 신뢰도용 RAG 블록 (planner 생략 옵션) |
| `app/services/prompts/confidence_basis.py` | confidence_basis 축·프롬프트·JSON 예시 |
| `app/services/prompts/issue_reliability_text.py` | 이미지 없는 신뢰도 VLM 프롬프트 |
| `app/utils/geo.py` | `wkt_point_from_wgs84` |
| `app/repositories/PinImageRepo.py` | pin_image CRUD |
| `app/repositories/PinLocationRepo.py` | pin_location CRUD |
| `app/repositories/PinLikeRepo.py` | pin_like |
| `app/repositories/CommunityRepo.py` | community |
| `app/models/Community.py` | community ORM |
| `app/models/PinLike.py` | pin_like ORM |

---

## 12. 수정 파일 목록 및 변경 내용

### 12.1 `app/routes/IssueRoute.py`

- `POST /issues/pin` 추가 (`BackgroundTasks` 주입)
- `GET /issues/pin/{issue_pin_id}` 추가
- `GET /issues/pin/{issue_pin_id}/reliability` 추가

### 12.2 `app/services/IssueService.py`

- `create_issue_pin` 전체 구현
- `_snapshot_upload_images`, `_upload_pin_images_sync`
- `_build_issue_pin_home_response`, `get_issue_pin_detail`, `get_issue_pin_reliability`
- `_derive_reliability_status`, `_derive_image_upload_status`
- 의존성: PinLocationRepo, PinImageRepo, PinLikeRepo, CommunityRepo, S3Util, IssuePinBackgroundRunner

### 12.3 `app/core/deps.py`

- Repo·S3·BackgroundRunner DI
- `get_issue_pin_background_runner`: VLM, EXIF, S3, VectorStore, RAG planner 주입

### 12.4 `app/core/config.py`

- Gemini VLM/핀 텍스트 모델 분리
- 신뢰도 파이프라인 타임아웃·planner 생략·재시도 횟수 설정
- `issue_pin_max_images`, `pin_title_max_length`, `pin_content_max_length`

### 12.5 `app/core/codes.py`

- `ISSUE_PIN_GET_SUCCESS` (`ISSUE_2001`)
- `ISSUE_PIN_RELIABILITY_GET_SUCCESS` (`ISSUE_2002`)

### 12.6 `app/schemas/IssueDTO.py`

- `ReliabilityStatus`, `ImageUploadStatus`
- `IssuePinHomeDetailResponse`, `IssuePinReliabilityResponse`, `IssuePinHomeImageItem`
- `CreateIssuePinRequest`, `CreateIssuePinResponse` 등

### 12.7 `app/repositories/IssuePinRepo.py`

- `get_by_issue_pin_id` + `selectinload` (pin, images, location, user)
- `update_confidence`: SQL `UPDATE` (get+flush 대신)

### 12.8 `app/models/IssuePin.py`

- `issue_confidence`, `confidence_content` nullable
- `pin` relationship `selectin`

### 12.9 `app/models/Pin.py` / `PinLocation.py`

- relationship·`detail_address`·`Geometry` point 등 정리

### 12.10 `app/models/enum/ToneType.py`

- 톤 enum 확장 (한줄요약형, 상황설명형, …)

### 12.11 `app/utils/S3Util.py`

- `upload_bytes` (게시 동기 업로드)
- `download_bytes` (신뢰도 백그라운드)

### 12.12 `app/services/internal/ai/VLMService.py`

- `analyze_text_only` (이미지 없는 신뢰도)
- `confidence_basis` 스키마 연동
- `_generate_with_retry`: `max_attempts`, `fallback_models`, `log_context` 파라미터

### 12.13 `app/services/internal/ai/IssueRagPlannerService.py`

- `generate_content_with_retry` → `gemini_retry` 모듈 사용

### 12.14 `app/services/internal/ai/IssuePinLLMService.py`

- gemini_retry 연동 (기존 핀 LLM)

### 12.15 `app/services/prompts/vlm.py`

- `confidence_basis` 배열 스키마·프롬프트 (시민용 문구 규칙)

---

## 13. Gemini 재시도·Fallback·타임아웃

구현: `app/services/internal/ai/gemini_retry.py`

### 13.1 동작

1. `model_candidates = [primary, *fallbacks]`
2. 모델마다 `max_attempts_per_model` 회 시도
3. 429/503/504 등 → 지수 백오프 후 재시도
4. 모델 exhaust → **fallback switch** 로그 후 다음 모델
5. 전부 실패 → `all models failed` 로그 + 마지막 예외 raise

### 13.2 신뢰도 파이프라인만의 제한

- `max_attempts` = 2 (설정)
- fallback 모델 1개만 사용
- planner 기본 생략

### 13.3 타임아웃 계층

| 계층 | 초과 시 |
|------|---------|
| RAG 45s | `Reliability stage=RAG TIMEOUT` → 전체 실패 처리 |
| VLM 150s | `Reliability stage=VLM TIMEOUT` |
| 전체 240s | `Reliability pipeline TOTAL timeout` |

---

## 14. 로깅 가이드

모든 신뢰도 로그에 `[issue_pin_id=N pin_id=M]` 컨텍스트 포함.

### 14.1 파이프라인

- `Reliability pipeline job start` — 설정값 덤프
- `Reliability stage=RAG|S3|EXIF|VLM|PERSIST start/done`
- `Reliability pipeline TOTAL timeout`
- `Reliability pipeline persist failure fallback`

### 14.2 Gemini

- `VLM call start` — model chain
- `VLM attempt start` / `VLM retry scheduled` / `VLM model exhausted`
- `VLM fallback switch` / `VLM success` / `VLM all models failed`
- Planner도 동일 prefix `Planner`

### 14.3 RAG

- `Reliability RAG planner skipped`
- `Reliability RAG retrieve start/done`
- VectorStore: `aretrieve — returned N nodes`

---

## 15. 에러·성공 코드

### 15.1 게시 시 사용하는 에러

| 코드 | 상황 |
|------|------|
| `USER_4041` | 사용자 없음 |
| `COMMON_422` | 위치 resolve 실패, 빈 제목/본문, 길이 초과 |
| `FILE_4001` | S3 업로드 실패 |
| `FILE_4151` | 비이미지 파일 |

**미사용**: `ISSUE_4221` (신뢰도 낮아 게시 거절) — 정책상 게시는 항상 허용

### 15.2 성공

| 코드 | API |
|------|-----|
| `COMMON_201` | POST /issues/pin, /pin/ai |
| `ISSUE_2001` | GET /issues/pin/{id} |
| `ISSUE_2002` | GET /issues/pin/{id}/reliability |

---

## 16. 의존성 (requirements.txt)

- `GeoAlchemy2==0.18.0` — `pin_point` geometry
- `boto3-stubs==1.42.95` — S3 타입 힌트
- (기존) `google-genai`, `fastapi`, `sqlalchemy`, `asyncpg` 등

---

## 17. 프론트엔드 연동 체크리스트

- [ ] `POST /issues/pin/ai` → 편집 → `POST /issues/pin` 2단계
- [ ] 게시 응답 `reliabilityStatus === 'pending'` 이면 신뢰도 폴링
- [ ] `GET .../reliability` 또는 상세에서 `issueConfidence`, `confidenceContent` 표시
- [ ] `confidenceContent` 줄바꿈 (`\n`) 렌더링
- [ ] `reliabilityStatus === 'failed'` 시 재시도 안내 UI
- [ ] 이미지 0장 게시 지원
- [ ] `tone` Form 값은 한국어 label (`없음`, …)
- [ ] 게시 시 `latitude`/`longitude` 필수

---

## 18. 트러블슈팅 (운영에서 겪은 이슈)

### 18.1 `issue_confidence` / `confidence_content` 가 NULL

**원인 후보**:

1. 백그라운드 job 미실행 (서버 reload, task GC) → `BackgroundTasks` + task set 보강
2. S3 동기화 이후 메모리 스냅샷만 넘기던 시기 → **S3 download 방식으로 수정**
3. Gemini 503으로 240초 타임아웃 → 실패 문구는 저장되어야 함 (`finally`)
4. DB 다른 환경 조회 (APP_ENV local vs dev)

**확인 SQL**:

```sql
SELECT issue_pin_id, issue_confidence, LEFT(confidence_content, 80)
FROM issue_pin ORDER BY issue_pin_id DESC LIMIT 10;
```

### 18.2 `pin_tone_type_check` 위반

- API는 한국어 value, DB는 enum name → Spring Flyway로 check constraint 전체 name 허용 필요

### 18.3 `detail_address` NOT NULL

- 게시 시 resolve 주소 없으면 422 — 반드시 `PinLocation.detail_address` 채움

### 18.4 `MissingGreenlet`

- lazy load 제거: `selectinload`, 응답 빌더에서 relationship 직접 할당 금지
- `pin.pin_images = ...` 대입 시 lazy trigger → 저장된 list 변수만 사용

### 18.5 Gemini 503 High demand

- planner 재시도가 길면 전체 타임아웃 → `SKIP_RAG_PLANNER=true`, VLM flash, attempts=2

### 18.6 줄바꿈이 안 보임

- 과거 `sanitize`가 `\n`을 공백으로 합침 → `normalize_display_line_breaks`로 수정
- 프론트 `pre-line` 필요

---

## 19. 미구현·향후 작업

| 항목 | 상태 |
|------|------|
| `pinUserProfile` | 응답 null (DB 컬럼 없음) |
| `isReported` | hardcoded `false` |
| `ISSUE_4221` 게시 거절 | 정책상 사용 안 함 |
| 기존 issue_pin 백필 API | 수동 스크립트만 가능 |
| Spring Flyway `pin_tone_type_check` 전 환경 | 수동 적용 이슈 |
| 신뢰도 완료 푸시/웹소켓 | 없음 (폴링만) |

---

## 20. 변경 파일 인덱스 (전체)

아래는 이번 기능과 직접 관련된 **모든** 경로 (staged + unstaged 합집).

```
app/core/codes.py
app/core/config.py
app/core/deps.py
app/models/Community.py
app/models/IssuePin.py
app/models/Pin.py
app/models/PinLike.py
app/models/PinLocation.py
app/models/enum/ToneType.py
app/repositories/CommunityRepo.py
app/repositories/IssuePinRepo.py
app/repositories/PinImageRepo.py
app/repositories/PinLikeRepo.py
app/repositories/PinLocationRepo.py
app/routes/IssueRoute.py
app/schemas/IssueDTO.py
app/schemas/issue_pin_job.py
app/services/IssueService.py
app/services/internal/IssuePinBackgroundRunner.py
app/services/internal/ai/IssuePinLLMService.py
app/services/internal/ai/IssueRagPlannerService.py
app/services/internal/ai/VLMService.py
app/services/internal/ai/gemini_retry.py
app/services/internal/issue_confidence_basis.py
app/services/internal/issue_rag_context.py
app/services/prompts/confidence_basis.py
app/services/prompts/issue_reliability_text.py
app/services/prompts/vlm.py
app/utils/S3Util.py
app/utils/geo.py
requirements.txt
```

---

## 부록 A. `IssuePinBackgroundRunner` public 메서드

| 메서드 | 설명 |
|--------|------|
| `schedule(job, background_tasks?)` | job 큐잉 |
| `run_reliability_job(job)` | 전체 실행 (타임아웃·finally 포함) |

## 부록 B. `issue_confidence_basis` public 함수

| 함수 | 설명 |
|------|------|
| `resolve_confidence_basis_markdown` | VLM JSON → bullet markdown |
| `format_confidence_content_for_user` | 점수 intro + body |
| `is_failed_reliability_content` | failed 상태 판별 |
| `clamp_confidence_score` | 0.0~1.0 |
| `FAILED_RELIABILITY_BASIS` | 실패 시 DB 문자열 |

## 부록 C. 커밋 메시지 예시

```
feat: 이슈 핀 게시 API 및 비동기 신뢰도 파이프라인 구현

- POST /issues/pin: 핀·이슈핀·위치 동기 저장 후 201, 이미지는 S3(issueimage/) 동기 업로드
- 백그라운드 신뢰도: S3 pin_image 기준 이미지 로드 → RAG → VLM → issue_confidence/confidence_content UPDATE
- GET /issues/pin/{id}, /reliability 폴링 API 및 홈 상세·신뢰도 전용 DTO(camelCase) 추가
- 신뢰도 근거는 시민용 문장(존댓말·기술 용어 제거)으로 저장하고 줄바꿈(\n) 유지
- Gemini 503 재시도·fallback·단계별 타임아웃·상세 로그, 실패 시에도 DB에 안내 문구 저장
```

---

*문서 끝.*
