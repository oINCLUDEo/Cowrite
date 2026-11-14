import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    source_revision: int
    created_at: datetime
    created_by: uuid.UUID | None
    kind: str
