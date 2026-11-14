"""Письмо не предоставляет доступ: членство проверяется заново перед отправкой."""

import uuid
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentMember


async def send_invitation(
    session: AsyncSession,
    settings: Settings,
    document_id: str,
    user_id: str,
    inviter_id: str,
    message_id: str,
) -> None:
    document = await session.get(Document, uuid.UUID(document_id))
    member = await session.get(DocumentMember, (uuid.UUID(document_id), uuid.UUID(user_id)))
    user = await session.get(User, uuid.UUID(user_id))
    inviter = await session.get(User, uuid.UUID(inviter_id))
    if document is None or member is None or user is None or inviter is None:
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = user.email
    message["Subject"] = "Доступ к документу Cowrite"
    message["Message-ID"] = message_id
    message.set_content(
        f"{inviter.display_name} предоставил доступ к документу «{document.title}».\n"
        f"Роль: {member.role}.\n{str(settings.frontend_url).rstrip('/')}/documents/{document.id}\n"
        "Для открытия требуется вход в приложение."
    )
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        start_tls=settings.smtp_starttls,
        validate_certs=True,
        timeout=10,
    )
