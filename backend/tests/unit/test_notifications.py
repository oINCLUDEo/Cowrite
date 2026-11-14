import uuid
from email.message import EmailMessage
from unittest.mock import AsyncMock

from app.core.config import Settings
from app.models import Document, DocumentMember, User
from app.modules.notifications.service import send_invitation


async def test_invitation_checks_membership_and_uses_stable_message_id(monkeypatch):
    document_id, user_id, inviter_id = (uuid.uuid4() for _ in range(3))
    session = AsyncMock()
    session.get.side_effect = [
        Document(id=document_id, title="Текст", owner_id=inviter_id),
        DocumentMember(document_id=document_id, user_id=user_id, role="viewer"),
        User(id=user_id, email="reader@example.com", display_name="Читатель"),
        User(id=inviter_id, display_name="Автор"),
    ]
    smtp = AsyncMock()
    monkeypatch.setattr("app.modules.notifications.service.aiosmtplib.send", smtp)
    await send_invitation(
        session,
        Settings(_env_file=None),
        str(document_id),
        str(user_id),
        str(inviter_id),
        "<same@cowrite>",
    )
    message = smtp.call_args.args[0]
    assert isinstance(message, EmailMessage)
    assert message["Message-ID"] == "<same@cowrite>"
    assert str(document_id) in message.get_content()
    assert smtp.call_args.kwargs["timeout"] == 10
    session.get.side_effect = [None, None, None, None]
    smtp.reset_mock()
    await send_invitation(
        session,
        Settings(_env_file=None),
        str(document_id),
        str(user_id),
        str(inviter_id),
        "<same@cowrite>",
    )
    smtp.assert_not_awaited()
