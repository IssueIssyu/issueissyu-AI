# 축제 핀 DB 핸드오프

## 역할 분리

| 환경 | 방식 |
|------|------|
| **개발·검증** | Swagger `search` → `transform` → `handoff` |
| **실서비스** | Cron이 배치 스크립트 실행 (사람이 Swagger 안 누름) |

## 실서비스 배치 (권장)

```
매일 03:00 Cron
  → python -m rag.scripts.run_festival_pipeline
      ① TourAPI 수집 → festival_documents.jsonl
      ② Gemini 가공 → festival_pins_for_db.jsonl
  → (백엔드/DB) JSONL 또는 내부 API로 pin / event_pin / pin_image UPSERT
```

### Cron 예시 (Linux)

```cron
0 3 * * * cd /path/to/issueissyu-AI && /path/to/venv/bin/python -m rag.scripts.run_festival_pipeline >> /var/log/festival-pipeline.log 2>&1
```

### 수동·기간 지정

```bash
python -m rag.scripts.run_festival_pipeline --start-date 20260501 --end-date 20261231 --fetch-limit 100
```

환경변수:

- `VISITKOREA_SERVICE_KEY`, `GEMINI_API_KEY` (필수)
- `FESTIVAL_SYNC_LOOKAHEAD_DAYS` (기본 120, 날짜 미지정 시 오늘~+N일)
- `FESTIVAL_SYNC_FETCH_LIMIT`, `FESTIVAL_SYNC_TRANSFORM_LIMIT` (선택)

## Swagger (로컬/dev)

| 순서 | API | 저장 |
|------|-----|------|
| 1 | `GET /festival-pins/search` | `festival_documents.jsonl` |
| 2 | `POST /festival-pins/transform` | `festival_pins_for_db.jsonl` |
| 3 | `GET /festival-pins/handoff` | 조회만 |

## DB INSERT

이 AI 서비스는 **JSONL까지** 담당. PostgreSQL INSERT는 **백엔드 코어** 또는 DB팀이 수행 (중복은 `contentid`로 UPSERT 권장).

## JSONL → 테이블

| JSONL | 테이블 |
|-------|--------|
| `pin_title`, `pin_content`, `pin_type` | `pin` |
| `event_start_time`, `event_end_time` | `event_pin` |
| `image_urls[]` | `pin_image` |
| `longitude`, `latitude` | `pin_location` |

## 반려동물·숙박

수집 시 TourAPI → transform 프롬프트 → `pin_content` 본문 반영.
