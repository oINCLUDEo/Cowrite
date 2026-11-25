import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VersionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "5e4d3c2b-1a09-4876-9584-7362514f0e1d",
                    "document_id": "7a1b0f2e-9c3d-4e5f-8a1b-2c3d4e5f6a7b",
                    "source_revision": 11,
                    "created_at": "2026-11-20T10:55:00Z",
                    "created_by": "0b6a0a6f-6f2e-4f7b-8f5d-1c2d3e4f5061",
                    "kind": "manual",
                }
            ]
        },
    )
    id: uuid.UUID
    document_id: uuid.UUID
    source_revision: int
    created_at: datetime
    created_by: uuid.UUID | None
    kind: str
