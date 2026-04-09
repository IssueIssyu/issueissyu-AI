from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic import computed_field
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
    db_scheme: Literal["postgresql", "postgres+asyncpg"] = Field(
        default="postgresql", alias="DB_SCHEME"
    )
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: SecretStr = Field(default=SecretStr("postgres"), alias="DB_PASSWORD")
    db_name: str = Field(default="app", alias="DB_NAME")

    # JWT
    jwt_secret_key: SecretStr = Field(default=SecretStr("dev-secret"), alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expires_minutes: int = Field(
        default=60 * 24, alias="JWT_ACCESS_TOKEN_EXPIRES_MINUTES"
    )

    # 기타
    debug: bool = Field(default=True, alias="DEBUG")

    @computed_field
    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:"
            f"{self.db_password.get_secret_value()}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field
    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:"
            f"{self.db_password.get_secret_value()}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # .env + 환경변수 기반으로 로드


settings = get_settings()
