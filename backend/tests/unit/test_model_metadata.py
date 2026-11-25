from pycrdt import Doc

from app.core.db import Base
from app.models import Document, DocumentMember, DocumentVersion, ExportJob, User
from app.modules.documents.models import empty_document_state


def test_model_registry_and_empty_document_state():
    assert {
        model.__tablename__
        for model in (User, Document, DocumentMember, DocumentVersion, ExportJob)
    } == set(Base.metadata.tables)
    doc = Doc()
    doc.apply_update(empty_document_state())
    assert doc.get_update() == Doc().get_update()


def test_user_email_is_normalized_on_assignment():
    user = User(email="  TEST@EXAMPLE.COM  ", display_name="Test", password_hash="hash")
    assert user.email == "test@example.com"
