"""Публичные метаданные и запросы управления доступом без CRDT-байтов."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

Role = Literal["owner", "editor", "viewer"]
MemberRole = Literal["editor", "viewer"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CreateDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title = "Без названия"


class RenameDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    generation: int
    state_revision: int
    created_at: datetime
    updated_at: datetime
    role: Role


class MemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: MemberRole

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: MemberRole
    notification: str = "not_configured"
