import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExportResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "9f8e7d6c-5b4a-4321-8765-4321fedcba98",
                    "status": "succeeded",
                    "error_code": None,
                    "created_at": "2026-11-20T11:20:00Z",
                    "finished_at": "2026-11-20T11:20:04Z",
                }
            ]
        },
    )
    id: uuid.UUID
    status: str
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


class ExportAccepted(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"task_id": "9f8e7d6c-5b4a-4321-8765-4321fedcba98"}]}
    )
    task_id: uuid.UUID
