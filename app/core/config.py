from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices
from pydantic import Field
from pydantic import computed_field
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
    local_db_url: str | None = Field(default=None, alias="LOCAL_DB_URL")
    local_db_username: str | None = Field(default=None, alias="LOCAL_DB_USERNAME")
    local_db_password: SecretStr | None = Field(default=None, alias="LOCAL_DB_PASSWORD")
    aws_db_url: str | None = Field(default=None, alias="AWS_DB_URL")
    aws_db_username: str | None = Field(default=None, alias="AWS_DB_USERNAME")
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

    # Gemini
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_vlm_model: str = Field(
        default="gemini-3.1-pro-preview",
        alias="GEMINI_VLM_MODEL",
    )

    @field_validator("redis_local_port", "redis_aws_port", "redis_aws_db", mode="before")
    @classmethod
    def _empty_string_to_none_for_int_fields(cls, value: object) -> object:
        if value == "":
            return None
        return value

    # 기타
    debug: bool = Field(default=True, alias="DEBUG")

    def _selected_db_values(self) -> tuple[str | None, str | None, SecretStr | None]:
        # local이면 LOCAL DB, dev/prod면 AWS DB 사용
        if self.env == "local":
            return self.local_db_url, self.local_db_username, self.local_db_password
        return self.aws_db_url, self.aws_db_username, self.aws_db_password

    def _build_database_url(self, *, async_mode: bool) -> str:
        base_url, username, password_secret = self._selected_db_values()
        password = password_secret.get_secret_value() if password_secret else ""
        auth_url = (base_url or "").replace(
            "postgresql://", f"postgresql://{username}:{password}@", 1
        )

        if async_mode:
            return (
                auth_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
                .replace("postgresql://", "postgresql+asyncpg://", 1)
            )
        return (
            auth_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
            .replace("postgresql://", "postgresql+psycopg://", 1)
        )

    @computed_field
    @property
    def sync_database_url(self) -> str:
        return self._build_database_url(async_mode=False)

    @computed_field
    @property
    def async_database_url(self) -> str:
        return self._build_database_url(async_mode=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # .env + 환경변수 기반으로 로드


settings = get_settings()
