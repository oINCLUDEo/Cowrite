"""Общие публичные ошибки REST без внутренних исключений."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"code": "access_denied", "message": "Недостаточно прав"}]}
    )
    code: str
    message: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": {"code": "not_found", "message": "Не найдено"}}]}
    )
    detail: ErrorDetail


def error_response(description: str) -> dict[str, Any]:
    """Описание кода ошибки с сохранением схемы ErrorResponse в OpenAPI.

    FastAPI при переопределении кода полностью заменяет ответ, поэтому модель
    передаём явно. Код 422 здесь не описываем: его схему HTTPValidationError
    генерирует FastAPI, а переопределение потеряло бы эту схему.
    """
    return {"model": ErrorResponse, "description": description}
