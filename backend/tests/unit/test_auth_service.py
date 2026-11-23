from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.modules.auth.schemas import RegisterRequest
from app.modules.auth.service import register


async def test_concurrent_duplicate_registration_rolls_back():
    session = MagicMock()
    session.commit = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("duplicate")))
    session.rollback = AsyncMock()
    session.scalar = AsyncMock(return_value=object())
    data = RegisterRequest(
        email="test@example.com", password="long password 123", display_name="Test"
    )
    with pytest.raises(HTTPException) as error:
        await register(session, data)
    assert error.value.status_code == 409
    session.rollback.assert_awaited_once()
