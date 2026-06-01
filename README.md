# issueissyu-AI

issueissyu(이슈있슈) **AI 서비스**는 지역 기반 이슈·민원 처리를 돕는 **FastAPI 기반 Python API 서버**입니다.  
이미지·텍스트 분석, RAG 검색, 이슈 핀 신뢰도 평가, 민원 의견서 자동 생성·이메일 발송 등 **AI 파이프라인**을 담당합니다.  


## 👥 Team
|                                 AI (PartLeader)                                  |                                 AI                                  |
|:-----------------------------------------------------------------------:|:-------------------------------------------------------------------:|
| <img width="185" height="218" alt="스크린샷 2026-06-01 115013" src="https://github.com/user-attachments/assets/09308917-0f54-436b-88fc-5b2f80417c1b" /> | <img width="182" height="220" alt="스크린샷 2026-06-01 115047" src="https://github.com/user-attachments/assets/d323f8e6-0017-49fb-b5e3-1165fd2fcf53" /> |
|       양지우<br/><a href="https://github.com/qkwltkwkd1">@qkwltkwkd1</a>       |       전성환<br/><a href="https://github.com/selnem">@selnem</a>        |

## 💻 Tech Stack
- **Framework/Language**: FastAPI, Python 3.13, Uvicorn
- **Database/Cache**: PostgreSQL (PostGIS, pgvector), SQLAlchemy 2.0 async, Redis/Valkey
- **AI/ML**: Google Gemini (VLM, LLM, Embedding), LlamaIndex Vector Store
- **Auth**: JWT 검증만 (발급은 Spring Boot 백엔드)
- **External Services**: AWS S3, SMTP, Location Core API (역지오코딩·행정구역)
- **Docs/PDF**: Swagger (FastAPI OpenAPI), WeasyPrint, Playwright (Chromium)
- **Deploy**: AWS Elastic Beanstalk, GitHub Actions

## 📂 Project Structure
기능 단위 레이어 + RAG 오프라인 파이프라인

```
issueissyu-AI/
├── .github/                       # Issue/PR 템플릿, CI/CD
├── .ebextensions/                 # Elastic Beanstalk 설정
├── .platform/                     # EB hooks (PDF·Playwright 시스템 라이브러리)
├── app/
│   ├── main.py                    # FastAPI 앱, lifespan(벡터·Redis·S3 초기화)
│   ├── core/                      # 설정, DB, DI, 예외·응답 코드
│   ├── login/                     # JWT 검증 (액세스 토큰)
│   ├── routes/                    # HTTP API
│   │   ├── IssueRoute.py          # 이슈 핀 생성·신뢰도·수정
│   │   ├── ComplaintEmailRoute.py # 민원 의견서 AI 파이프라인
│   │   ├── ComplaintApplyRoute.py # 민원 접수·발송·스케줄러
│   │   ├── ImageGeoRoute.py       # EXIF 좌표 추출
│   │   └── VectorTestRoute.py     # 벡터 검색 테스트 (local)
│   ├── services/
│   │   ├── IssueService.py        # 이슈 핀 유스케이스
│   │   ├── ComplaintEmailService.py
│   │   ├── VectorStoreService.py  # pgvector + Gemini Embedding
│   │   ├── RagRetrievalService.py / RagRerankService.py
│   │   ├── prompts/               # LLM/VLM 프롬프트 패키지
│   │   └── internal/
│   │       ├── ai/                # VLM, IssuePin LLM, RAG Planner, Gemini retry
│   │       ├── geo/               # EXIF·역지오코딩 클라이언트
│   │       └── IssuePinBackgroundRunner.py  # 신뢰도 백그라운드 파이프라인
│   ├── repositories/              # SQLAlchemy AsyncSession CRUD
│   ├── models/                    # ORM 엔티티
│   ├── schemas/                   # Pydantic DTO
│   └── utils/                     # S3, Redis, geo, vector 유틸
├── rag/
│   ├── raw/                       # AI Hub 원본 JSON (tl1, qna)
│   ├── output/                    # 전처리 결과 JSONL
│   └── scripts/                   # 전처리·청킹·임베딩·벡터 적재
├── docs/                          # 레이어링, 전처리, 프롬프트 가이드
├── sql/                           # DB 초기 데이터
├── requirements.txt
└── Procfile                       # uvicorn app.main:app
```

## 🛠️ Architecture
<img width="1425" height="584" alt="Untitled-Page-2 (15) (2)" src="https://github.com/user-attachments/assets/f998a8e3-db38-4535-8b19-d9b591f7e040" />

## 🚀 Local Run

```bash
# 1. 가상환경 및 의존성
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 환경 변수 (.env)
# APP_ENV=local
# LOCAL_DB_HOST, LOCAL_DB_PORT, LOCAL_DB_NAME, LOCAL_DB_USER, LOCAL_DB_PASSWORD
# REDIS_LOCAL_HOST, REDIS_LOCAL_PORT
# JWT_SECRET, JWT_ALGORITHM
# GEMINI_API_KEY
# AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_BUCKET (이미지 업로드 시)
# LOCATION_CORE_BASE_URL=http://localhost:8080

# 3. 서버 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 문서: `http://localhost:8000/docs`
- 헬스체크: `GET /health`

RAG 데이터 전처리·벡터 적재는 [`docs/preprocessing.md`](docs/preprocessing.md)를 참고하세요.

## 📝 Commit Convention
| type | 의미 | 예시 |
| --- | --- | --- |
| ⭐ **feat** | 새로운 기능 | 이슈 핀 신뢰도 API 추가 |
| 🐞 **bug** | 버그 수정 | VLM 타임아웃 처리 수정 |
| 📖 **docs** | 문서 수정 | README 업데이트 |
| ⚙️ **setting** | 프로젝트/환경 설정 | EB hook, CI, 의존성 변경 |
| **♻️ refactor** | 기능 변화 없는 코드 리팩터링 | Service 분리 |
| 🎨 **style** | 포맷/세미콜론/네이밍 등 | 포맷팅, 공백 |
| 🧪 **test** | 테스트 코드 | 파이프라인 단위 테스트 |
| 🚀 **deploy** | 배포, dev→main | 배포 |
