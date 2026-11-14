import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


class ExportAccepted(BaseModel):
    task_id: uuid.UUID
