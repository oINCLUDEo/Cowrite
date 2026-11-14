import uuid

import pytest
from pycrdt import Doc
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentMember, DocumentVersion, ExportJob, User

pytestmark = pytest.mark.integration


async def make_user(session: AsyncSession, **kwargs) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Test user",
        password_hash="test-hash-not-a-real-password",
    )
    for key, value in kwargs.items():
        setattr(user, key, value)
    session.add(user)
    await session.flush()
    return user


async def test_migrations_create_all_tables(db_session):
    connection = await db_session.connection()
    tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    assert set(tables) == {
        "alembic_version",
        "users",
        "documents",
        "document_members",
        "document_versions",
        "export_jobs",
    }


async def test_document_defaults_are_valid_crdt_and_utc(db_session):
    owner = await make_user(db_session)
    document = Document(owner_id=owner.id)
    db_session.add(document)
    await db_session.flush()

    assert document.title == "Без названия"
    assert document.generation == 1
    assert document.state_revision == 0
    assert document.created_at.utcoffset().total_seconds() == 0
    restored = Doc()
    restored.apply_update(document.ydoc_state)
    assert restored.get_update() == Doc().get_update()


async def test_email_is_normalized_and_unique(db_session):
    user = await make_user(db_session, email="  EXAMPLE@Example.COM  ")
    assert user.email == "example@example.com"
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await make_user(db_session, email="example@example.com")


async def test_user_requires_login_method(db_session):
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await make_user(db_session, password_hash=None)


@pytest.mark.parametrize("role", ["owner", "admin", "bad"])
async def test_membership_rejects_invalid_roles(db_session, role):
    owner = await make_user(db_session)
    member = await make_user(db_session)
    document = Document(owner_id=owner.id)
    db_session.add(document)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(DocumentMember(document_id=document.id, user_id=member.id, role=role))
            await db_session.flush()


async def test_membership_is_unique(db_session):
    owner = await make_user(db_session)
    member = await make_user(db_session)
    document = Document(owner_id=owner.id)
    db_session.add(document)
    await db_session.flush()
    db_session.add(DocumentMember(document_id=document.id, user_id=member.id, role="editor"))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO document_members (document_id, user_id, role) "
                    "VALUES (:document_id, :user_id, 'viewer')"
                ),
                {"document_id": document.id, "user_id": member.id},
            )


async def test_scheduled_snapshot_is_idempotent_by_revision(db_session):
    owner = await make_user(db_session)
    document = Document(owner_id=owner.id)
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        DocumentVersion(
            document_id=document.id, state=document.ydoc_state, source_revision=0, kind="scheduled"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                DocumentVersion(
                    document_id=document.id,
                    state=document.ydoc_state,
                    source_revision=0,
                    kind="scheduled",
                )
            )
            await db_session.flush()


async def test_export_cannot_reference_another_documents_version(db_session):
    owner = await make_user(db_session)
    first, second = Document(owner_id=owner.id), Document(owner_id=owner.id)
    db_session.add_all([first, second])
    await db_session.flush()
    version = DocumentVersion(
        document_id=first.id, state=first.ydoc_state, source_revision=0, kind="export"
    )
    db_session.add(version)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ExportJob(document_id=second.id, version_id=version.id, requested_by=owner.id)
            )
            await db_session.flush()


async def test_document_delete_cascades_to_members_versions_exports(db_session):
    owner = await make_user(db_session)
    member = await make_user(db_session)
    document = Document(owner_id=owner.id)
    db_session.add(document)
    await db_session.flush()
    db_session.add(DocumentMember(document_id=document.id, user_id=member.id, role="viewer"))
    version = DocumentVersion(
        document_id=document.id, state=document.ydoc_state, source_revision=0, kind="export"
    )
    db_session.add(version)
    await db_session.flush()
    job = ExportJob(document_id=document.id, version_id=version.id, requested_by=owner.id)
    db_session.add(job)
    await db_session.flush()
    assert job.status == "queued"

    await db_session.execute(delete(Document).where(Document.id == document.id))
    for model in (DocumentMember, DocumentVersion, ExportJob):
        count = await db_session.scalar(
            select(func.count()).select_from(model).where(model.document_id == document.id)
        )
        assert count == 0
    assert await db_session.get(User, owner.id) is not None
