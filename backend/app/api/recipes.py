import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import ColumnElement, Select, Text, cast, func, select, tuple_
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, SessionDep
from app.errors import InvalidCursorError, NoOriginalRecipeError, RecipeNotFoundError
from app.models import Recipe, User, Video
from app.schemas.errors import ErrorResponse
from app.schemas.recipes import RecipeOut, RecipePage, RecipeSummary, RecipeUpdate
from app.services.imports import recipe_fields

router = APIRouter(prefix="/recipes", tags=["recipes"])

_NOT_FOUND = {404: {"model": ErrorResponse}}

# Só as colunas do vídeo que a API mostra (a transcrição pode ter centenas de KB).
_WITH_VIDEO = joinedload(Recipe.video).load_only(
    Video.youtube_id, Video.title, Video.channel, Video.thumbnail_url, Video.duration_s
)

# Texto em que a busca procura: título, tags e nomes dos ingredientes.
_SEARCH_DOCUMENT = func.concat_ws(
    " ",
    Recipe.title,
    func.array_to_string(Recipe.tags, " "),
    cast(func.jsonb_path_query_array(Recipe.ingredients, cast("$[*].name", JSONPATH)), Text),
)
MAX_SEARCH_TERMS = 8


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _matches(term: str) -> ColumnElement[bool]:
    """Contém o termo, sem diferenciar maiúsculas nem acentos."""
    pattern = func.unaccent(f"%{_escape_like(term)}%")
    return func.unaccent(_SEARCH_DOCUMENT).ilike(pattern, escape="\\")


def _encode_cursor(recipe: Recipe) -> str:
    raw = f"{recipe.created_at.isoformat()}|{recipe.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, recipe_id = raw.split("|")
        return datetime.fromisoformat(created_at), uuid.UUID(recipe_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError(detail=cursor) from exc


def _user_recipes(user: User) -> Select[tuple[Recipe]]:
    return select(Recipe).where(Recipe.user_id == user.id).options(_WITH_VIDEO)


async def _get_recipe(session: AsyncSession, user: User, recipe_id: uuid.UUID) -> Recipe:
    recipe = await session.scalar(_user_recipes(user).where(Recipe.id == recipe_id))
    if recipe is None:
        raise RecipeNotFoundError()
    return recipe


@router.get("", response_model=RecipePage, responses={422: {"model": ErrorResponse}})
async def list_recipes(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[
        str | None, Query(max_length=200, description="Busca no título, ingredientes e tags")
    ] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    favorite: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> RecipePage:
    """Livro do usuário, das receitas mais recentes para as mais antigas."""
    stmt = _user_recipes(user)
    if favorite is not None:
        stmt = stmt.where(Recipe.is_favorite.is_(favorite))
    if tag and tag.strip():
        stmt = stmt.where(Recipe.tags.contains([tag.strip().lstrip("#").lower()]))
    for term in (q or "").split()[:MAX_SEARCH_TERMS]:
        stmt = stmt.where(_matches(term))
    if cursor:
        created_at, recipe_id = _decode_cursor(cursor)
        stmt = stmt.where(tuple_(Recipe.created_at, Recipe.id) < tuple_(created_at, recipe_id))

    stmt = stmt.order_by(Recipe.created_at.desc(), Recipe.id.desc()).limit(limit + 1)
    recipes = list(await session.scalars(stmt))
    await session.commit()

    has_more = len(recipes) > limit
    recipes = recipes[:limit]
    return RecipePage(
        items=[RecipeSummary.model_validate(recipe) for recipe in recipes],
        next_cursor=_encode_cursor(recipes[-1]) if has_more else None,
    )


@router.get("/{recipe_id}", response_model=RecipeOut, responses=_NOT_FOUND)
async def get_recipe(recipe_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RecipeOut:
    recipe = await _get_recipe(session, user, recipe_id)
    await session.commit()
    return RecipeOut.model_validate(recipe)


@router.patch(
    "/{recipe_id}",
    response_model=RecipeOut,
    responses={**_NOT_FOUND, 422: {"model": ErrorResponse}},
)
async def update_recipe(
    recipe_id: uuid.UUID, body: RecipeUpdate, user: CurrentUser, session: SessionDep
) -> RecipeOut:
    recipe = await _get_recipe(session, user, recipe_id)
    for name, value in body.changes().items():
        setattr(recipe, name, value)
    await session.commit()
    return RecipeOut.model_validate(recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND)
async def delete_recipe(recipe_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    recipe = await _get_recipe(session, user, recipe_id)
    await session.delete(recipe)
    await session.commit()


@router.post(
    "/{recipe_id}/reset",
    response_model=RecipeOut,
    responses={**_NOT_FOUND, 409: {"model": ErrorResponse}},
)
async def reset_recipe(recipe_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RecipeOut:
    """Descarta as edições e volta à receita gerada para o vídeo.

    Favorito, notas e avaliação são do usuário, não da receita: continuam como estão.
    """
    recipe = await _get_recipe(session, user, recipe_id)
    generated = await session.scalar(
        select(Video.generated_recipe).where(Video.id == recipe.video_id)
    )
    if not generated or not generated.get("is_recipe"):
        raise NoOriginalRecipeError()
    for name, value in recipe_fields(generated).items():
        setattr(recipe, name, value)
    await session.commit()
    return RecipeOut.model_validate(recipe)
