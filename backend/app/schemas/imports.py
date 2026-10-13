import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import Import, ImportStatus
from app.schemas.text import NoNul


class ImportCreate(BaseModel):
    url: Annotated[str, Field(min_length=1, max_length=2048), NoNul]


class ImportFailure(BaseModel):
    code: str
    message: str


class ImportOut(BaseModel):
    id: uuid.UUID
    url: str
    youtube_id: str
    status: ImportStatus
    recipe_id: uuid.UUID | None
    error: ImportFailure | None
    queue_position: int | None = Field(
        description="Posição aproximada na fila (1 = próximo); só enquanto espera."
    )
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_import(cls, imp: Import, queue_position: int | None = None) -> "ImportOut":
        error = (
            ImportFailure(code=imp.error_code, message=imp.error_message or "")
            if imp.error_code
            else None
        )
        return cls(
            id=imp.id,
            url=imp.url,
            youtube_id=imp.youtube_id,
            status=imp.status,
            recipe_id=imp.recipe_id,
            error=error,
            queue_position=queue_position,
            created_at=imp.created_at,
            updated_at=imp.updated_at,
        )
