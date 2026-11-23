"""Входные данные регистрации и входа; отдельные схемы безопасных ответов API."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

# Пробелы в пароле значимы: в отличие от имени и email, его не обрезаем.
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: Password

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(Credentials):
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]


class UserResponse(BaseModel):
    # Хеш пароля и внутренние данные входа в ответ не включаем.
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    display_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 1800


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[
        str, StringConstraints(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")
    ]


class GitHubProfile(BaseModel):
    id: int = Field(gt=0, strict=True)
    login: str = Field(min_length=1, max_length=80)
    name: str | None = None


class GitHubEmail(BaseModel):
    email: EmailStr = Field(max_length=254)
    primary: bool = Field(strict=True)
    verified: bool = Field(strict=True)
