# 공모전 핀 · 카드뉴스 핸드오프

## 흐름

| 순서 | API / 스크립트 | 결과 |
|------|----------------|------|
| 1 | `POST /contest-pins/crawl` | `rag/output/contest_documents.jsonl` |
| 2 | `POST /contest-pins/cardnews` | `rag/output/contest_cardnews/{contentid}/slide_XX.png` + `contest_pins_for_db.jsonl` |
| 3 | `GET /contest-pins/handoff` | DB UPSERT용 JSON 확인 |

CLI:

```bash
python -m rag.scripts.run_contest_cardnews --limit 1 --contentid 319419
python scripts/preview_contest_cardnews.py   # Gemini 없이 템플릿만 확인
```

## 2차 저작물 (이미지)

- Linkareer에서 가져온 **공고 이미지 URL은 카드뉴스에 넣지 않음**
- **공모전 전용** 브라우저형 Pillow 템플릿 (`app/contest_cardnews/template/`, 정책 템플릿과 분리)
- `app/assets/mascots/` **캐릭터 PNG**만 합성
- `template_palette`: `pastel_mint` / `pastel_pink` / `pastel_lavender` / `pastel_peach` / `pastel_sky` / `pastel_lemon` (1건당 1색)

## 핸드오프 JSONL 필드

| 필드 | 용도 |
|------|------|
| `contentid` | Linkareer activity ID |
| `title` | pin 제목 |
| `pin_content` | 인스타 캡션(기본) + 원문 URL |
| `cardnews_image_urls` | 슬라이드 상대 경로 |
| `source_url` | 원문 링크 |

환경변수: `GEMINI_API_KEY` (슬라이드 문구·캡션)
