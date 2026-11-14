import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Cowrite environment")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@postgres:5432/test")
    monkeypatch.setenv("REDIS_CACHE_URL", "redis://redis:6379/1")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Cowrite environment"
    assert settings.debug is True
    assert str(settings.database_url) == "postgresql+asyncpg://user:pass@postgres:5432/test"
    assert str(settings.redis_cache_url) == "redis://redis:6379/1"


def test_settings_read_utf8_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=Совместный редактор\nPOSTGRES_USER=cowrite\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "Совместный редактор"


def test_environment_overrides_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=From file\n", encoding="utf-8")
    monkeypatch.setenv("APP_NAME", "From environment")

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "From environment"


@pytest.mark.parametrize(
    "values",
    [
        {"database_url": "not-a-url"},
        {"redis_cache_url": "https://example.com"},
        {"app_name": ""},
        {"jwt_secret": "short"},
        {"frontend_url": "https://example.com/path"},
        {"frontend_url": "https://user:pass@example.com"},
    ],
)
def test_settings_reject_invalid_values(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_settings_are_cached():
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


def test_empty_github_credentials_disable_oauth():
    settings = Settings(_env_file=None, github_client_id="", github_client_secret="")
    assert settings.github_client_id is None
    assert settings.github_client_secret is None
