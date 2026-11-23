import uuid

import pytest
from pycrdt import Doc
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import create_access_token
from app.models import Document, User

pytestmark = pytest.mark.integration


@pytest.fixture
async def accounts(db_session):
    users = [
        User(email=f"{name}@example.com", display_name=name, password_hash="test-hash")
        for name in ("owner", "editor", "viewer", "stranger")
    ]
    db_session.add_all(users)
    await db_session.flush()
    settings = Settings(
        _env_file=None, jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes")
    )
    return {
        user.display_name: (
            user,
            {"Authorization": f"Bearer {create_access_token(user.id, settings)}"},
        )
        for user in users
    }


async def test_document_lifecycle(api_client, accounts, db_session):
    owner, headers = accounts["owner"]
    result = await api_client.post("/documents", json={}, headers=headers)
    assert result.status_code == 201
    document = result.json()
    assert document["title"] == "Без названия"
    assert document["role"] == "owner"
    assert document["generation"] == 1
    assert "ydoc_state" not in document
    Doc().apply_update((await db_session.get(Document, uuid.UUID(document["id"]))).ydoc_state)
    path = f"/documents/{document['id']}"
    assert (await api_client.get(path, headers=headers)).json() == document
    assert (await api_client.get("/documents", headers=headers)).json() == [document]
    renamed = await api_client.patch(path, json={"title": "  Новый  "}, headers=headers)
    assert renamed.json()["title"] == "Новый"
    assert (await api_client.delete(path, headers=headers)).status_code == 204
    assert (await api_client.get(path, headers=headers)).status_code == 404
    assert (await api_client.get("/documents", headers=headers)).json() == []


@pytest.mark.parametrize("role", ["editor", "viewer"])
async def test_membership_matrix(api_client, accounts, role):
    owner, headers = accounts["owner"]
    member, member_headers = accounts[role]
    _, stranger_headers = accounts["stranger"]
    document = (
        await api_client.post("/documents", json={"title": "Доступ"}, headers=headers)
    ).json()
    path = f"/documents/{document['id']}"
    assert (await api_client.get(path, headers=stranger_headers)).status_code == 403
    assert (await api_client.get("/documents", headers=member_headers)).json() == []
    result = await api_client.post(
        path + "/members",
        json={"email": f"  {member.email.upper()}  ", "role": role},
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["role"] == role
    assert (await api_client.get(path, headers=member_headers)).json()["role"] == role
    assert len((await api_client.get("/documents", headers=member_headers)).json()) == 1
    assert len((await api_client.get(path + "/members", headers=headers)).json()) == 1
    for acting_headers in (member_headers, stranger_headers):
        assert (
            await api_client.patch(path, json={"title": "hacked"}, headers=acting_headers)
        ).status_code == 403
        assert (await api_client.delete(path, headers=acting_headers)).status_code == 403
        assert (await api_client.get(path + "/members", headers=acting_headers)).status_code == 403
        assert (
            await api_client.post(
                path + "/members",
                json={"email": member.email, "role": "editor"},
                headers=acting_headers,
            )
        ).status_code == 403
        assert (
            await api_client.delete(path + f"/members/{member.id}", headers=acting_headers)
        ).status_code == 403
    other_role = "viewer" if role == "editor" else "editor"
    assert (
        await api_client.post(
            path + "/members", json={"email": member.email, "role": other_role}, headers=headers
        )
    ).status_code == 200
    assert (await api_client.get(path, headers=member_headers)).json()["role"] == other_role
    assert len((await api_client.get(path + "/members", headers=headers)).json()) == 1
    assert (
        await api_client.delete(path + f"/members/{member.id}", headers=headers)
    ).status_code == 204
    assert (await api_client.get(path, headers=member_headers)).status_code == 403


async def test_membership_errors(api_client, accounts):
    owner, headers = accounts["owner"]
    path = (
        "/documents/" + (await api_client.post("/documents", json={}, headers=headers)).json()["id"]
    )
    assert (
        await api_client.post(
            path + "/members", json={"email": owner.email, "role": "viewer"}, headers=headers
        )
    ).status_code == 409
    assert (
        await api_client.delete(path + f"/members/{owner.id}", headers=headers)
    ).status_code == 409
    assert (
        await api_client.post(
            path + "/members",
            json={"email": "missing@example.com", "role": "editor"},
            headers=headers,
        )
    ).status_code == 404
    assert (
        await api_client.delete(path + f"/members/{uuid.uuid4()}", headers=headers)
    ).status_code == 404
    for invalid_role in ("owner", "admin", "", None):
        assert (
            await api_client.post(
                path + "/members",
                json={"email": owner.email, "role": invalid_role},
                headers=headers,
            )
        ).status_code == 422


@pytest.mark.parametrize("title", ["", "   ", "x" * 201, None])
async def test_invalid_titles(api_client, accounts, title):
    _, headers = accounts["owner"]
    assert (
        await api_client.post("/documents", json={"title": title}, headers=headers)
    ).status_code == 422


async def test_pagination_and_auth(api_client, accounts):
    _, headers = accounts["owner"]
    assert (await api_client.get("/documents")).status_code == 401
    assert (await api_client.post("/documents", json={})).status_code == 401
    for title in ("Первый", "Второй", "Третий"):
        assert (
            await api_client.post("/documents", json={"title": title}, headers=headers)
        ).status_code == 201
    all_docs = (await api_client.get("/documents", headers=headers)).json()
    assert len(all_docs) == 3
    assert (
        await api_client.get("/documents?limit=1&offset=1", headers=headers)
    ).json() == all_docs[1:2]
    for query in ("limit=0", "limit=101", "offset=-1"):
        assert (await api_client.get("/documents?" + query, headers=headers)).status_code == 422
    assert (await api_client.get(f"/documents/{uuid.uuid4()}", headers=headers)).status_code == 404
