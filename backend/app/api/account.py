"""Dados da conta (LGPD): exportar tudo e apagar a conta."""

from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.auth import clear_session_cookie
from app.api.deps import CurrentUser, RedisDep, SessionClaimsDep, SessionDep, ip_rate_limit
from app.api.recipes import WITH_VIDEO
from app.models import Import, Recipe
from app.schemas.account import AccountExport, ImportExport, UserExport
from app.schemas.auth import PasswordIn
from app.schemas.errors import ErrorResponse
from app.schemas.recipes import RecipeOut
from app.services import auth

router = APIRouter(prefix="/account", tags=["account"])

EXPORT_FILENAME = "receita-meus-dados.json"


@router.get("/export", response_model=AccountExport, responses={401: {"model": ErrorResponse}})
async def export_account(
    user: CurrentUser, session: SessionDep, response: Response
) -> AccountExport:
    """Perfil, receitas do livro (com as edições) e histórico de imports, em JSON."""
    recipes = await session.scalars(
        select(Recipe)
        .where(Recipe.user_id == user.id)
        .options(WITH_VIDEO)
        .order_by(Recipe.created_at, Recipe.id)
    )
    imports = await session.scalars(
        select(Import).where(Import.user_id == user.id).order_by(Import.created_at, Import.id)
    )
    export = AccountExport(
        exported_at=datetime.now(UTC),
        user=UserExport.model_validate(user),
        recipes=[RecipeOut.model_validate(recipe) for recipe in recipes],
        imports=[ImportExport.model_validate(imp) for imp in imports],
    )
    await session.commit()
    response.headers["Content-Disposition"] = f'attachment; filename="{EXPORT_FILENAME}"'
    response.headers["Cache-Control"] = "no-store"
    return export


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ip_rate_limit("delete-account", lambda s: s.rate_limit_login)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_account(
    body: PasswordIn,
    user: CurrentUser,
    claims: SessionClaimsDep,
    session: SessionDep,
    redis: RedisDep,
    response: Response,
) -> None:
    """Apaga a conta, as receitas e os imports (exige a senha). Os vídeos compartilhados ficam."""
    await auth.check_password(user, body.password)
    await auth.delete_account(session, user)
    await auth.revoke_session(redis, claims)
    clear_session_cookie(response)
