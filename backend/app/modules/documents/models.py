"""Документы и участники. Владелец хранится в Document, остальные роли — в DocumentMember."""

import uuid
from datetime import datetime
from typing import Literal

from pycrdt import Doc
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def empty_document_state() -> bytes:
    # Пустой документ тоже должен содержать корректное CRDT-состояние, а не b"".
    return Doc().get_update()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) BETWEEN 1 AND 200", name="title_length"),
        CheckConstraint("generation >= 1", name="positive_generation"),
        CheckConstraint("state_revision >= 0", name="nonnegative_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), default="Без названия")
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    ydoc_state: Mapped[bytes] = mapped_column(LargeBinary, default=empty_document_state)
    # generation меняется при откате; revision — при сохранении нового состояния.
    generation: Mapped[int] = mapped_column(Integer, server_default="1")
    state_revision: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )


class DocumentMember(Base):
    # Составной первичный ключ не даёт добавить одного участника дважды.
    __tablename__ = "document_members"
    __table_args__ = (CheckConstraint("role IN ('editor', 'viewer')", name="valid_role"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[Literal["editor", "viewer"]] = mapped_column(String(6))
