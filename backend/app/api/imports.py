import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, RedisDep, SessionDep
from app.errors import ImportNotFoundError
from app.models import Import
from app.schemas.errors import ErrorResponse
from app.schemas.imports import ImportCreate, ImportOut
from app.services import imports

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "",
    response_model=ImportOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": ImportOut, "description": "Concluído na hora (receita já disponível)"},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def create_import(
    body: ImportCreate,
    user: CurrentUser,
    session: SessionDep,
    redis: RedisDep,
    response: Response,
) -> ImportOut:
    """Valida o link e enfileira o vídeo. Se a receita já existe, conclui na hora (200)."""
    imp, queued = await imports.create_import(session, redis, user, body.url)
    if not queued:
        response.status_code = status.HTTP_200_OK
    return ImportOut.from_import(imp, await imports.queue_position(redis, imp))


@router.get("/{import_id}", response_model=ImportOut, responses={404: {"model": ErrorResponse}})
async def get_import(
    import_id: uuid.UUID, user: CurrentUser, session: SessionDep, redis: RedisDep
) -> ImportOut:
    imp = await session.scalar(
        select(Import).where(Import.id == import_id, Import.user_id == user.id)
    )
    await session.commit()
    if imp is None:
        raise ImportNotFoundError()
    return ImportOut.from_import(imp, await imports.queue_position(redis, imp))
