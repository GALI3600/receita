"""Dados de teste: usuários, vídeos com receita gerada e cópias no livro."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CSRF_HEADER
from app.models import Recipe, User, Video
from app.schemas.transcript import Segment, TranscriptSource
from app.services import recipe_llm, security
from app.services.imports import recipe_fields

GENERATED: dict[str, Any] = {
    "is_recipe": True,
    "title": "Bolo de cenoura",
    "summary": "Bolo fofinho de liquidificador.",
    "servings": "12 fatias",
    "prep_time_min": 15,
    "cook_time_min": 40,
    "difficulty": "fácil",
    "ingredients": [
        {"name": "cenoura", "quantity": "3", "unit": None, "note": "média", "group": "massa"},
        {"name": "açúcar", "quantity": "2", "unit": "xícara", "note": None, "group": "massa"},
    ],
    "steps": [
        {"order": 1, "text": "Bata as cenouras com os ovos.", "video_timestamp_s": 65},
        {"order": 2, "text": "Asse por 40 minutos.", "video_timestamp_s": 300},
    ],
    "tips": ["Use cenouras bem laranjas."],
    "tags": ["bolo", "sobremesa"],
}

SPEECH = [Segment(start=float(i), end=i + 1.0, text="bata os ovos com o açúcar") for i in range(6)]


# Clientes da API mandam o header anti-CSRF em todo pedido que muda estado.
CSRF = {CSRF_HEADER: "XMLHttpRequest"}


def headers(user: User) -> dict[str, str]:
    """Pedido autenticado como `user`: cookie de sessão válido e header anti-CSRF."""
    token = security.create_session_token(user.id, user.password_hash)
    return {"Cookie": f"{security.SESSION_COOKIE}={token}", **CSRF}


def youtube_id(n: int) -> str:
    return f"vid{n:08d}"


async def make_user(
    session: AsyncSession, name: str = "Ana", *, verified: bool = True, password_hash: str = "!"
) -> User:
    """Usuário sem senha utilizável (o hash "!" nunca confere); `headers(user)` loga como ele."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"{user_id}@example.com",
        password_hash=password_hash,
        name=name,
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    session.add(user)
    await session.commit()
    return user


async def make_video(
    session: AsyncSession,
    yt_id: str = "abcdefghijk",
    *,
    generated: dict[str, Any] | None = GENERATED,
    prompt_version: str | None = recipe_llm.PROMPT_VERSION,
    transcript: list[Segment] | None = SPEECH,
    **overrides: Any,
) -> Video:
    video = Video(
        youtube_id=yt_id,
        title=overrides.pop("title", "Bolo de cenoura fofinho"),
        channel="Receitas",
        duration_s=600,
        thumbnail_url=f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg",
        embeddable=True,
        transcript=transcript,
        transcript_source=TranscriptSource.MANUAL if transcript is not None else None,
        generated_recipe=generated,
        llm_model=recipe_llm.MODEL if generated else None,
        prompt_version=prompt_version if generated else None,
        **overrides,
    )
    session.add(video)
    await session.commit()
    return video


async def make_recipe(session: AsyncSession, user: User, video: Video, **overrides: Any) -> Recipe:
    assert video.generated_recipe is not None
    fields = recipe_fields(video.generated_recipe) | overrides
    recipe = Recipe(user_id=user.id, video_id=video.id, **fields)
    session.add(recipe)
    await session.commit()
    return recipe
