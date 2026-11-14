"""Настройки приложения. Переменные окружения имеют приоритет над корневым .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Cowrite", min_length=1)
    debug: bool = False
    api_root_path: str = ""  # /api за Nginx; пустая строка при прямом запуске.
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://cowrite:cowrite-local@localhost:5432/cowrite"
    )
    redis_cache_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    test_database_url: PostgresDsn | None = None  # Отдельная БД, не данные приложения.
    jwt_secret: SecretStr | None = Field(default=None, min_length=32)
    github_client_id: str | None = Field(default=None, min_length=1)
    github_client_secret: SecretStr | None = Field(default=None, min_length=1)
    github_redirect_uri: HttpUrl | None = None
    frontend_url: HttpUrl = HttpUrl("http://localhost:8080")
    allowed_origins: list[str] = ["http://localhost:8080"]
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "Cowrite <noreply@cowrite.local>"
    smtp_starttls: bool = False
    exports_dir: Path = Path("exports")
    pdf_fonts_dir: Path = Path("/usr/share/fonts/truetype/dejavu")
    log_level: str = "INFO"

    @field_validator("github_client_id", "github_client_secret", mode="before")
    @classmethod
    def empty_github_credentials(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("frontend_url")
    @classmethod
    def frontend_origin_only(cls, value: HttpUrl) -> HttpUrl:
        if value.path not in (None, "/") or value.query or value.fragment or value.username:
            raise ValueError("FRONTEND_URL must be an origin without a path or credentials")
        return value


@lru_cache
def get_settings() -> Settings:
    # Читаем .env один раз на процесс, а не при каждом запросе.
    return Settings()
