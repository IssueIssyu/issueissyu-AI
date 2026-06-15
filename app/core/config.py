from dataclasses import dataclass
from functools import cached_property
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import AliasChoices
from pydantic import Field
from pydantic import field_validator
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True, slots=True)
class DbConnectionParams:
    host: str
    port: int
    name: str
    user: str | None
    password: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "dev", "prod"] = Field(default="local", alias="APP_ENV")

    # Database
    local_db_host: str | None = Field(default=None, alias="LOCAL_DB_HOST")
    local_db_port: int | None = Field(default=5432, alias="LOCAL_DB_PORT")
    local_db_name: str | None = Field(default=None, alias="LOCAL_DB_NAME")
    local_db_user: str | None = Field(default=None, alias="LOCAL_DB_USER")
    local_db_password: SecretStr | None = Field(default=None, alias="LOCAL_DB_PASSWORD")
    aws_db_host: str | None = Field(default=None, alias="AWS_DB_HOST")
    aws_db_port: int | None = Field(default=5432, alias="AWS_DB_PORT")
    aws_db_name: str | None = Field(default=None, alias="AWS_DB_NAME")
    aws_db_user: str | None = Field(default=None, alias="AWS_DB_USER")
    aws_db_password: SecretStr | None = Field(default=None, alias="AWS_DB_PASSWORD")

    # JWT 검증(디코딩)만 — 발급은 다른 서비스 (.env: JWT_SECRET, JWT_ALGORITHM)
    jwt_secret: SecretStr = Field(
        default=SecretStr("dev-secret"),
        validation_alias=AliasChoices("JWT_SECRET", "JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = Field(default="HS512", alias="JWT_ALGORITHM")
    jwt_timezone: str = Field(default="Asia/Seoul", alias="JWT_TIMEZONE")

    # S3
    aws_access_key: str | None = Field(default=None, alias="AWS_ACCESS_KEY")
    aws_secret_key: SecretStr | None = Field(default=None, alias="AWS_SECRET_KEY")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_bucket_name: str | None = Field(default=None, alias="AWS_BUCKET")
    cdn_enabled: bool = Field(default=False, alias="CDN_ENABLED")
    cdn_base_url: str | None = Field(default=None, alias="CDN_BASE_URL")

    # SMTP (민원 이메일 실제 송신)
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")
    smtp_timeout_seconds: float = Field(default=15.0, gt=0, alias="SMTP_TIMEOUT_SECONDS")
    smtp_skip_cert_verify: bool = Field(default=False, alias="SMTP_SKIP_CERT_VERIFY")
    smtp_send_concurrency: int = Field(default=5, ge=1, le=50, alias="SMTP_SEND_CONCURRENCY")

    redis_local_host: str | None = Field(default=None, alias="REDIS_LOCAL_HOST")
    redis_local_port: int | None = Field(default=6379, alias="REDIS_LOCAL_PORT")

    redis_aws_host: str | None = Field(default=None, alias="VALKEY_HOST")
    redis_aws_port: int | None = Field(default=6379, alias="VALKEY_PORT")
    redis_aws_db: int | None = Field(default=0, alias="VALKEY_DB")
    redis_aws_password: SecretStr | None = Field(default=None, alias="VALKEY_PASSWORD")
    # ElastiCache/Valkey TLS(인-트랜짓 암호화). `true`/`1`/`yes` 등은 pydantic이 bool로 파싱.
    redis_aws_tls: bool = Field(default=False, alias="VALKEY_TLS")

    # 코어(8080 등) 역지오코딩 겸 행정·location_id 매핑 — `/api/location/resolve?lat=&lng=`
    # 배포 시 .env 에 프로덕션 베이스 URL만 교체하면 됨(예: https://api.example.com).
    location_core_base_url: str | None = Field(
        default="http://localhost:8080",
        alias="LOCATION_CORE_BASE_URL",
    )
    location_resolve_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        alias="LOCATION_RESOLVE_TIMEOUT_SECONDS",
    )

    # Gemini/Vector DB
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    # 이슈 핀 신뢰도 VLM. 3.1-pro는 503·지연이 잦아 기본은 flash 계열.
    gemini_vlm_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_VLM_MODEL",
    )
    gemini_vlm_fallback_models: str = Field(
        default="gemini-2.5-flash,gemini-2.5-pro",
        alias="GEMINI_VLM_FALLBACK_MODELS",
    )
    gemini_pin_text_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_PIN_TEXT_MODEL",
    )
    rag_enable_rerank: bool = Field(
        default=False,
        alias="RAG_ENABLE_RERANK",
    )
    rag_vector_query_mode: str = Field(
        default="hybrid",
        alias="RAG_VECTOR_QUERY_MODE",
    )
    rag_retrieve_top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        alias="RAG_RETRIEVE_TOP_K",
    )
    rag_rerank_top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        alias="RAG_RERANK_TOP_K",
    )
    gemini_pin_text_fallback_models: str = Field(
        default="gemini-2.5-flash-lite,gemini-2.5-flash",
        alias="GEMINI_PIN_TEXT_FALLBACK_MODELS",
    )
    # RAG 질의 재작성(Planner) — 짧은 JSON 작업이므로 flash-lite 계열 권장
    gemini_rag_planner_model: str = Field(
        default="gemini-2.5-flash-lite",
        alias="GEMINI_RAG_PLANNER_MODEL",
    )
    gemini_rag_planner_fallback_models: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_RAG_PLANNER_FALLBACK_MODELS",
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-2",
        alias="GEMINI_EMBEDDING_MODEL",
    )
    # None이면 모델별 기본값(embedding-2 → 1, 그 외 → 10). 지정 시 LlamaIndex embed_batch_size로 전달.
    gemini_embedding_batch_size: int | None = Field(
        default=None,
        alias="GEMINI_EMBEDDING_BATCH_SIZE",
    )
    vector_table_name: str = Field(default="complaint_chunks", alias="VECTOR_TABLE_NAME")
    vector_embed_dim: int = Field(default=1536, alias="VECTOR_EMBED_DIM")
    vector_dim_check: bool = Field(
        default=False,
        alias="VECTOR_DIM_CHECK",
    )
    vector_hybrid_search: bool = Field(default=True, alias="VECTOR_HYBRID_SEARCH")
    vector_text_search_config: str = Field(
        default="simple",
        alias="VECTOR_TEXT_SEARCH_CONFIG",
    )

    # 문화체육관광부 정책브리핑 정책뉴스 OpenAPI (공공데이터포털)
    policy_news_service_key: SecretStr | None = Field(
        default=None,
        alias="POLICY_NEWS_SERVICE_KEY",
        description="정책뉴스 전용 API 키 (서비스별 독립 키, 필수)",
    )
    policy_news_api_base_url: str = Field(
        default="http://apis.data.go.kr/1371000/policyNewsService",
        alias="POLICY_NEWS_API_BASE_URL",
    )
    policy_news_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        alias="POLICY_NEWS_REQUEST_TIMEOUT_SECONDS",
    )
    policy_news_request_interval_seconds: float = Field(
        default=0.15,
        ge=0,
        alias="POLICY_NEWS_REQUEST_INTERVAL_SECONDS",
    )
    policy_sync_lookback_days: int = Field(
        default=3,
        ge=1,
        le=30,
        alias="POLICY_SYNC_LOOKBACK_DAYS",
        description="배치 수집 시 오늘 포함 N일 (API 3일 제한 고려)",
    )
    policy_sync_interval_days: int = Field(
        default=3,
        ge=1,
        le=30,
        alias="POLICY_SYNC_INTERVAL_DAYS",
        description="자동 sync 최소 간격(일)",
    )
    policy_sync_schedule_hour_kst: int = Field(
        default=1,
        ge=0,
        le=23,
        alias="POLICY_SYNC_SCHEDULE_HOUR_KST",
        description="정책 핀 sync 스케줄 확인 시각 (KST)",
    )
    policy_admin_user_name: str = Field(
        default="admin",
        validation_alias=AliasChoices("POLICY_ADMIN_USER_NAME", "POLICY_ADMIN_NICKNAME"),
        description="정책 핀 등록에 사용할 user.user_name",
    )
    policy_sync_batch_size: int = Field(
        default=5,
        ge=1,
        le=25,
        alias="POLICY_SYNC_BATCH_SIZE",
        description="sync/transform/import 1회 배치 건수",
    )
    policy_transform_concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="POLICY_TRANSFORM_CONCURRENCY",
        description="정책 pin_content·카드뉴스 Gemini 가공 동시 호출 수",
    )
    policy_prune_pipeline_after_import: bool = Field(
        default=True,
        alias="POLICY_PRUNE_PIPELINE_AFTER_IMPORT",
        description="DB INSERT 성공 후 JSONL·로컬 카드뉴스 캐시 제거",
    )
    policy_cardnews_keep_local_files: bool = Field(
        default=False,
        alias="POLICY_CARDNEWS_KEEP_LOCAL_FILES",
        description="True면 S3 업로드 후에도 rag/output/policy_cardnews 유지",
    )
    policy_sync_merge_documents: bool = Field(
        default=False,
        alias="POLICY_SYNC_MERGE_DOCUMENTS",
        description="False면 sync 수집 시 policy_documents.jsonl을 이번 구간으로 덮어씀",
    )
    policy_cardnews_s3_prefix: str = Field(
        default="policy-cardnews",
        alias="POLICY_CARDNEWS_S3_PREFIX",
        description="정책 카드뉴스 S3 object key prefix",
    )
    gemini_cardnews_image_model: str = Field(
        default="gemini-2.5-flash-image",
        alias="GEMINI_CARDNEWS_IMAGE_MODEL",
        description="정책 카드뉴스 슬라이드 이미지 생성 모델",
    )
    gemini_cardnews_image_fallback_models: str = Field(
        default="gemini-3-pro-image-preview,imagen-3.0-generate-002",
        alias="GEMINI_CARDNEWS_IMAGE_FALLBACK_MODELS",
    )
    policy_cardnews_pillow_fallback: bool = Field(
        default=True,
        alias="POLICY_CARDNEWS_PILLOW_FALLBACK",
        description="이미지 모델 실패 시 Pillow 템플릿 합성으로 폴백",
    )
    policy_cardnews_use_template: bool = Field(
        default=True,
        alias="POLICY_CARDNEWS_USE_TEMPLATE",
        description="고정 카드뉴스 템플릿(레퍼런스 형식) 사용",
    )
    policy_cardnews_use_image_model: bool = Field(
        default=False,
        alias="POLICY_CARDNEWS_USE_IMAGE_MODEL",
        description="True면 Gemini 이미지 모델, False면 Pillow SNS 템플릿",
    )
    policy_cardnews_font_dir: str = Field(
        default="../assets/fonts",
        alias="POLICY_CARDNEWS_FONT_DIR",
        description="Pretendard 등 폰트 폴더 (app/policy_cardnews 기준 상대 경로)",
    )

    # 한국관광공사 TourAPI (공공데이터포털 활용신청 키)
    visitkorea_service_key: SecretStr | None = Field(
        default=None,
        alias="VISITKOREA_SERVICE_KEY",
    )
    visitkorea_api_base_url: str = Field(
        default="https://apis.data.go.kr/B551011/KorService2",
        alias="VISITKOREA_API_BASE_URL",
    )
    visitkorea_mobile_os: str = Field(default="ETC", alias="VISITKOREA_MOBILE_OS")
    visitkorea_mobile_app: str = Field(default="issueissyu", alias="VISITKOREA_MOBILE_APP")
    visitkorea_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        alias="VISITKOREA_REQUEST_TIMEOUT_SECONDS",
    )
    visitkorea_request_interval_seconds: float = Field(
        default=0.15,
        ge=0,
        alias="VISITKOREA_REQUEST_INTERVAL_SECONDS",
    )
    festival_sync_lookahead_days: int = Field(
        default=120,
        ge=1,
        le=365,
        alias="FESTIVAL_SYNC_LOOKAHEAD_DAYS",
        description="배치 수집 시 오늘부터 N일 앞까지 행사 검색",
    )
    festival_sync_fetch_limit: int | None = Field(
        default=None,
        ge=1,
        alias="FESTIVAL_SYNC_FETCH_LIMIT",
        description="배치 fetch 최대 건수 (미설정 시 제한 없음)",
    )
    festival_sync_transform_limit: int | None = Field(
        default=None,
        ge=1,
        alias="FESTIVAL_SYNC_TRANSFORM_LIMIT",
        description="배치 transform 최대 건수 (미설정 시 fetch 건수 전체)",
    )
    festival_transform_concurrency: int = Field(
        default=5,
        ge=1,
        le=50,
        alias="FESTIVAL_TRANSFORM_CONCURRENCY",
        description="축제 pin_content Gemini 가공 동시 호출 수 (Cron/API 공통)",
    )
    festival_batch_size: int = Field(
        default=10,
        ge=1,
        le=50,
        alias="FESTIVAL_BATCH_SIZE",
        description="admin fetch/transform/import 기본 배치 크기",
    )
    policy_cardnews_mascot_dir: str | None = Field(
        default="../assets/mascots",
        alias="POLICY_CARDNEWS_MASCOT_DIR",
        description="핀 캐릭터 PNG 폴더 (app/policy_cardnews 기준 상대 경로). mascots.json files 목록에 있는 PNG만 사용",
    )
    contest_sync_schedule_hour_kst: int = Field(
        default=12,
        ge=0,
        le=23,
        alias="CONTEST_SYNC_SCHEDULE_HOUR_KST",
        description="공모전 핀 sync 스케줄 시각 (KST)",
    )
    contest_crawl_max_pages: int = Field(
        default=1,
        ge=1,
        le=50,
        alias="CONTEST_CRAWL_MAX_PAGES",
        description="sync/crawl 기본 목록 페이지 수",
    )
    contest_sync_batch_size: int = Field(
        default=5,
        ge=1,
        le=25,
        alias="CONTEST_SYNC_BATCH_SIZE",
        description="sync/transform/import 1회 배치 건수",
    )
    contest_transform_concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="CONTEST_TRANSFORM_CONCURRENCY",
        description="공모전 pin_content·카드뉴스 Gemini 가공 동시 호출 수",
    )
    contest_admin_user_name: str = Field(
        default="admin",
        validation_alias=AliasChoices("CONTEST_ADMIN_USER_NAME", "CONTEST_ADMIN_NICKNAME"),
        description="공모전 핀 등록에 사용할 user.user_name",
    )
    contest_prune_pipeline_after_import: bool = Field(
        default=True,
        alias="CONTEST_PRUNE_PIPELINE_AFTER_IMPORT",
        description="DB INSERT 성공 후 JSONL·로컬 카드뉴스 캐시 제거",
    )
    contest_cardnews_keep_local_files: bool = Field(
        default=False,
        alias="CONTEST_CARDNEWS_KEEP_LOCAL_FILES",
        description="True면 S3 업로드 후에도 rag/output/contest_cardnews 유지",
    )
    contest_cardnews_s3_prefix: str = Field(
        default="contest-cardnews",
        alias="CONTEST_CARDNEWS_S3_PREFIX",
        description="공모전 카드뉴스 S3 object key prefix",
    )

    @field_validator("policy_cardnews_font_dir", mode="before")
    @classmethod
    def _empty_string_policy_cardnews_font_dir(cls, value: object) -> object:
        if value == "":
            return "../assets/fonts"
        return value

    @field_validator("policy_cardnews_mascot_dir", mode="before")
    @classmethod
    def _empty_string_policy_cardnews_mascot_dir(cls, value: object) -> object:
        if value == "":
            return "../assets/mascots"
        return value

    @field_validator("gemini_embedding_batch_size", mode="before")
    @classmethod
    def _empty_string_gemini_embed_batch(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("cdn_base_url", mode="before")
    @classmethod
    def _empty_cdn_base_url_to_none(cls, value: object) -> object | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator(
        "local_db_port",
        "aws_db_port",
        "redis_local_port",
        "redis_aws_port",
        "redis_aws_db",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none_for_int_fields(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("location_core_base_url", mode="before")
    @classmethod
    def _empty_location_core_url_to_none(cls, value: object) -> object | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("pdf_korean_font_paths", mode="before")
    @classmethod
    def _empty_pdf_korean_font_paths_to_none(cls, value: object) -> object | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    # 의견서 PDF @font-face (쉼표 구분). 미설정 시 Linux 일반 경로만 자동 탐색.
    pdf_korean_font_paths: str | None = Field(
        default=None,
        alias="PDF_KOREAN_FONT_PATHS",
    )
    issue_pin_max_images: int = Field(default=5, ge=0, le=20, alias="ISSUE_PIN_MAX_IMAGES")
    ai_pin_generation_daily_limit: int = Field(
        default=10,
        ge=1,
        le=1000,
        alias="AI_PIN_GENERATION_DAILY_LIMIT",
        description="uid당 이슈 핀 AI 글 생성(미리보기) 일일 성공 허용 횟수",
    )
    ai_pin_generation_rate_limit_enabled: bool = Field(
        default=True,
        alias="AI_PIN_GENERATION_RATE_LIMIT_ENABLED",
        description="false면 AI 글 생성 일일 제한 비활성화",
    )
    issue_pin_create_daily_limit: int = Field(
        default=10,
        ge=1,
        le=1000,
        alias="ISSUE_PIN_CREATE_DAILY_LIMIT",
        description="uid당 이슈 핀 게시 일일 성공 허용 횟수",
    )
    issue_pin_create_rate_limit_enabled: bool = Field(
        default=True,
        alias="ISSUE_PIN_CREATE_RATE_LIMIT_ENABLED",
        description="false면 이슈 핀 게시 일일 제한 비활성화",
    )
    issue_pin_edit_daily_limit: int = Field(
        default=10,
        ge=1,
        le=1000,
        alias="ISSUE_PIN_EDIT_DAILY_LIMIT",
        description="pin_id(글)당 이슈 핀 수정 일일 성공 허용 횟수",
    )
    issue_pin_edit_rate_limit_enabled: bool = Field(
        default=True,
        alias="ISSUE_PIN_EDIT_RATE_LIMIT_ENABLED",
        description="false면 이슈 핀 수정 일일 제한 비활성화",
    )
    issue_confidence_basis_max_chars: int = Field(
        default=2000,
        ge=200,
        le=10000,
        alias="ISSUE_CONFIDENCE_BASIS_MAX_CHARS",
    )
    issue_pin_reliability_pipeline_timeout_seconds: float = Field(
        default=420.0,
        gt=0,
        alias="ISSUE_PIN_RELIABILITY_PIPELINE_TIMEOUT_SECONDS",
    )
    issue_pin_reliability_skip_rag_planner: bool = Field(
        default=False,
        alias="ISSUE_PIN_RELIABILITY_SKIP_RAG_PLANNER",
    )
    issue_pin_reliability_gemini_max_attempts: int = Field(
        default=2,
        ge=1,
        le=10,
        alias="ISSUE_PIN_RELIABILITY_GEMINI_MAX_ATTEMPTS",
    )
    issue_pin_reliability_rag_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        alias="ISSUE_PIN_RELIABILITY_RAG_TIMEOUT_SECONDS",
    )
    issue_pin_reliability_vlm_timeout_seconds: float = Field(
        default=180.0,
        gt=0,
        alias="ISSUE_PIN_RELIABILITY_VLM_TIMEOUT_SECONDS",
    )
    pin_title_max_length: int = Field(default=100, ge=1, le=200, alias="PIN_TITLE_MAX_LENGTH")
    pin_content_max_length: int = Field(
        default=10000,
        ge=1,
        le=50000,
        alias="PIN_CONTENT_MAX_LENGTH",
    )

    # 기타
    debug: bool = Field(default=True, alias="DEBUG")

    @property
    def pdf_korean_font_path_list(self) -> list[Path]:
        raw = (self.pdf_korean_font_paths or "").strip()
        if not raw:
            return []
        return [Path(part.strip()) for part in raw.split(",") if part.strip()]

    def _selected_db_values(
        self,
    ) -> tuple[str | None, int | None, str | None, str | None, SecretStr | None]:
        # local이면 LOCAL DB, dev/prod면 AWS DB 사용
        if self.env == "local":
            return (
                self.local_db_host,
                self.local_db_port,
                self.local_db_name,
                self.local_db_user,
                self.local_db_password,
            )
        return (
            self.aws_db_host,
            self.aws_db_port,
            self.aws_db_name,
            self.aws_db_user,
            self.aws_db_password,
        )

    @cached_property
    def _db_connection(self) -> DbConnectionParams:
        host, port, db_name_raw, db_user_raw, password_secret = self._selected_db_values()

        if host is None or not host.strip():
            raise ValueError("Database host is required.")

        if db_name_raw is None or not db_name_raw.strip():
            raise ValueError("Database name is required.")
        if "://" in db_name_raw:
            raise ValueError(
                "Database name must be plain name only (e.g. 'app'), not a full DSN.",
            )
        db_name = db_name_raw.strip().lstrip("/")
        if not db_name or "/" in db_name or "?" in db_name or "#" in db_name:
            raise ValueError(
                "Database name must be plain value (no path/query/fragment).",
            )

        if db_user_raw is None or not db_user_raw.strip():
            if self.env == "local":
                db_user: str | None = None
            else:
                raise ValueError("Database user is required.")
        else:
            db_user = db_user_raw.strip()

        password = (
            password_secret.get_secret_value() if password_secret is not None else ""
        )
        return DbConnectionParams(
            host=host,
            port=port if port is not None else 5432,
            name=db_name,
            user=db_user,
            password=password,
        )

    @property
    def db_name(self) -> str:
        return self._db_connection.name

    @property
    def db_host(self) -> str:
        return self._db_connection.host

    @property
    def db_port(self) -> int:
        return self._db_connection.port

    @property
    def db_user(self) -> str | None:
        return self._db_connection.user

    @property
    def db_password(self) -> str:
        return self._db_connection.password

    def build_database_url(
        self,
        *,
        async_mode: bool,
        db_host: str,
        db_port: int,
        db_name: str,
        db_user: str | None,
        db_password: str,
    ) -> str:
        drivername = "postgresql+asyncpg" if async_mode else "postgresql+psycopg"
        if db_user:
            if db_password:
                authority = (
                    f"{quote_plus(db_user)}:{quote_plus(db_password)}"
                    f"@{db_host}:{db_port}"
                )
            else:
                authority = f"{quote_plus(db_user)}@{db_host}:{db_port}"
        else:
            authority = f"{db_host}:{db_port}"
        return f"{drivername}://{authority}/{db_name}"

    @property
    def sync_database_url(self) -> str:
        conn = self._db_connection
        return self.build_database_url(
            async_mode=False,
            db_host=conn.host,
            db_port=conn.port,
            db_name=conn.name,
            db_user=conn.user,
            db_password=conn.password,
        )

    @property
    def async_database_url(self) -> str:
        conn = self._db_connection
        return self.build_database_url(
            async_mode=True,
            db_host=conn.host,
            db_port=conn.port,
            db_name=conn.name,
            db_user=conn.user,
            db_password=conn.password,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # .env + 환경변수 기반으로 로드


settings = get_settings()
