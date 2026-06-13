# 정책 핀 DB 핸드오프

## Swagger (로컬/dev)

| 순서 | API | 저장 |
|------|-----|------|
| 1 | `GET /policy-pins/search` | `policy_documents.jsonl` (원문·메타 전체) |
| 2 | `POST /policy-pins/transform` | `policy_pins_for_db.jsonl` |
| 3 | `GET /policy-pins/handoff` | 조회만 |

### Swagger 테스트 예시

1. `GET /policy-pins/search`
   - `start_date=20260522`, `end_date=20260524`, `limit=5`
2. `POST /policy-pins/transform`
   - `limit=5` (미지정 시 원문 전체)
3. `GET /policy-pins/handoff`
   - DB용 JSONL 확인 (`limit`만 적용, **날짜 필터 없음**)

## 파이프라인 (기간 필터는 1단계만)

```
GET /search (승인일 start_date~end_date)
    → policy_documents.jsonl   ← contentid, minister, approve_date, 원문 등 전체
POST /transform
    → policy_pins_for_db.jsonl  ← DB용 4필드만
GET /handoff
    → 위 파일 조회
```

**기간을 바꾸려면** `search`를 원하는 날짜로 다시 호출한 뒤 `transform`을 실행하세요.

### transform 응답 vs JSONL vs handoff

| | 내용 |
|--|------|
| `POST /transform` → `pins` | 방금 쓴 `policy_pins_for_db.jsonl`과 **동일** |
| `policy_pins_for_db.jsonl` | DB팀이 읽는 파일 |
| `GET /handoff` → `pins` | 같은 파일을 다시 읽음 (`limit`만 다를 수 있음) |

handoff는 transform을 다시 돌리지 않고 파일만 확인하는 API입니다.

### 승인일은 결과(JSONL)에 꼭 있어야 하나?

| 용도 | 승인일 위치 |
|------|-------------|
| **기간 필터** (어떤 기사를 가져올지) | `GET /search`의 `start_date`/`end_date` → API 조회 시 적용. 이미 걸러진 건만 transform 됨 |
| **DB `event_pin` 등** (승인일 컬럼 저장) | 필요하면 JSONL에 `event_start_time`/`event_end_time`을 **추가**할 수 있음 (현재 4필드만 전달) |
| **handoff에서 다시 날짜 필터** | 하지 않음 (파일 = transform 결과 그대로) |

정리: **필터링 때문에** 결과에 승인일이 있을 필요는 없습니다. **DB 스키마에 승인일 컬럼이 있으면** 그때만 JSONL 필드에 넣는 게 맞습니다.

## DB 전달 JSONL (`policy_pins_for_db.jsonl`)

**한 줄(한 핀)당 아래 4필드만** 포함합니다.

| 필드 | 설명 |
|------|------|
| `title` | 핀 제목 → `pin.pin_title` |
| `pin_content` | AI 가공 본문 → `pin.pin_content` |
| `cardnews_image_urls` | 카드뉴스 슬라이드 경로/URL 배열 → `pin_image` |
| `source_url` | 정책뉴스 원문 기사 URL |

```json
{
  "title": "올 하반기부터 개인정보 침해 위험 실태 점검",
  "pin_content": "개인정보, 이제 위험도에 따라...\n\n#정책",
  "cardnews_image_urls": [
    "rag/output/policy_cardnews/148965005/slide_01.png",
    "rag/output/policy_cardnews/148965005/slide_02.png"
  ],
  "source_url": "https://www.korea.kr/news/policyNewsView.do?newsId=148965005"
}
```

`contentid`, `minister`, `original_image_urls` 등은 **원문 JSONL**(`policy_documents.jsonl`)에만 있습니다. DB팀이 NewsItemId 등이 필요하면 `source_url` 또는 search 원문 파일을 참고하세요.

## DB INSERT

이 AI 서비스는 **JSONL까지** 담당. PostgreSQL INSERT는 **백엔드 코어** 또는 DB팀이 수행합니다.

### pin_image 업로드

| URL 형태 | 처리 |
|----------|------|
| `https://...` | 다운로드 후 S3 업로드 |
| `rag/output/policy_cardnews/...` | AI 서비스 로컬 PNG → S3 업로드 |

## 환경변수

- `POLICY_NEWS_SERVICE_KEY` 또는 `VISITKOREA_SERVICE_KEY` (search)
- `GEMINI_API_KEY` (transform)
- `GEMINI_CARDNEWS_IMAGE_MODEL` (선택, 기본 `gemini-2.5-flash-image`)
