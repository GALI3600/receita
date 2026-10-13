import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ImportStatus, UserPlan
from app.schemas.recipes import RecipeOut


class UserExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    email_verified_at: datetime | None
    plan: UserPlan
    created_at: datetime


class ImportExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    youtube_id: str
    status: ImportStatus
    error_code: str | None
    recipe_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AccountExport(BaseModel):
    """Todos os dados da conta (LGPD): perfil, receitas do livro e histórico de imports."""

    exported_at: datetime
    user: UserExport
    recipes: list[RecipeOut]
    imports: list[ImportExport]
