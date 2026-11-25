"""Публичные метаданные и запросы управления доступом без CRDT-байтов."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

Role = Literal["owner", "editor", "viewer"]
MemberRole = Literal["editor", "viewer"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CreateDocument(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"title": "Спецификация"}]},
    )
    title: Title = "Без названия"


class RenameDocument(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"title": "Спецификация v2"}]},
    )
    title: Title


class DocumentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "7a1b0f2e-9c3d-4e5f-8a1b-2c3d4e5f6a7b",
                    "title": "Спецификация",
                    "owner_id": "0b6a0a6f-6f2e-4f7b-8f5d-1c2d3e4f5061",
                    "generation": 1,
                    "state_revision": 12,
                    "created_at": "2026-11-20T10:15:30Z",
                    "updated_at": "2026-11-20T11:02:10Z",
                    "role": "owner",
                }
            ]
        },
    )
    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    generation: int
    state_revision: int
    created_at: datetime
    updated_at: datetime
    role: Role


class MemberRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"email": "reader@example.com", "role": "editor"}]},
    )
    email: EmailStr
    role: MemberRole

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class MemberResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "1c2d3e4f-5061-4a7b-9c8d-2e3f4a5b6c7d",
                    "email": "reader@example.com",
                    "display_name": "Читатель",
                    "role": "editor",
                    "notification": "queued",
                }
            ]
        }
    )
    user_id: uuid.UUID
    email: str
    display_name: str
    role: MemberRole
    notification: str = "not_configured"
