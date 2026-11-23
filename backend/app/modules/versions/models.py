"""Полные снапшоты документов: ручные, по расписанию и для экспорта."""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint("kind IN ('manual', 'scheduled', 'export')", name="valid_kind"),
        CheckConstraint("source_revision >= 0", name="nonnegative_revision"),
        UniqueConstraint("document_id", "id", name="uq_document_versions_document_id_id"),
        # Повтор задачи не создаст второй периодический снапшот той же ревизии.
        Index(
            "uq_document_versions_scheduled_revision",
            "document_id",
            "source_revision",
            unique=True,
            postgresql_where=text("kind = 'scheduled'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[bytes] = mapped_column(LargeBinary)
    source_revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[Literal["manual", "scheduled", "export"]] = mapped_column(String(9))
