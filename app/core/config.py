from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import AliasChoices
from pydantic import Field
from pydantic import field_validator
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    gemini_vlm_model: str = Field(
        default="gemini-3.1-pro-preview",
        alias="GEMINI_VLM_MODEL",
    )
    gemini_pin_text_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_PIN_TEXT_MODEL",
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
    # True면 lifespan에서 Gemini embed API로 차원 검증
    vector_dim_check: bool = Field(
        default=False,
        alias="VECTOR_DIM_CHECK",
    )

    @field_validator("gemini_embedding_batch_size", mode="before")
    @classmethod
    def _empty_string_gemini_embed_batch(cls, value: object) -> object:
        if value == "":
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

    # 기타
    debug: bool = Field(default=True, alias="DEBUG")

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

    @property
    def db_name(self) -> str:
        _, _, db_name_raw, _, _ = self._selected_db_values()
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
        return db_name

    @property
    def db_host(self) -> str:
        host, _, _, _, _ = self._selected_db_values()
        if host is None or not host.strip():
            raise ValueError("Database host is required.")
        return host

    @property
    def db_port(self) -> int:
        _, port, _, _, _ = self._selected_db_values()
        if port is not None:
            return port
        return 5432

    @property
    def db_user(self) -> str | None:
        _, _, _, db_user, _ = self._selected_db_values()
        if db_user is None or not db_user.strip():
            if self.env == "local":
                return None
            raise ValueError("Database user is required.")
        return db_user.strip()

    @property
    def db_password(self) -> str:
        _, _, _, _, password_secret = self._selected_db_values()
        if password_secret is not None:
            return password_secret.get_secret_value()
        return ""

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
        return self.build_database_url(
            async_mode=False,
            db_host=self.db_host,
            db_port=self.db_port,
            db_name=self.db_name,
            db_user=self.db_user,
            db_password=self.db_password,
        )

    @property
    def async_database_url(self) -> str:
        return self.build_database_url(
            async_mode=True,
            db_host=self.db_host,
            db_port=self.db_port,
            db_name=self.db_name,
            db_user=self.db_user,
            db_password=self.db_password,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # .env + 환경변수 기반으로 로드


settings = get_settings()
