"""Учётные записи. Пароль и GitHub ID допускают вход двумя разными способами."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Учётная запись не должна остаться без единого способа входа.
        CheckConstraint("password_hash IS NOT NULL OR github_id IS NOT NULL", name="login_method"),
        CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 0", name="email_normalized"
        ),
        CheckConstraint("length(btrim(display_name)) BETWEEN 1 AND 80", name="display_name_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    github_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        return value.strip().lower()
