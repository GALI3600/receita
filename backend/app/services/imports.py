"""Regras do import compartilhadas pela API e pelo worker.

A receita canônica fica em `Video.generated_recipe`; cada usuário recebe uma cópia em `Recipe`
que pode editar à vontade. Um vídeo que já tem receita com o prompt atual é copiado na hora,
sem fila, sem transcrição e sem nova chamada ao Claude (e sem gastar a cota do usuário).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from arq.connections import ArqRedis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.errors import AppError, LLMBudgetExceededError, QueueUnavailableError
from app.models import UNFINISHED_IMPORT_STATUSES, Import, ImportStatus, Recipe, User, Video
from app.schemas.recipe_llm import RecipeLLM
from app.services import quotas, recipe_llm, youtube

logger = logging.getLogger(__name__)

RECIPE_FIELDS = (
    "title",
    "summary",
    "servings",
    "prep_time_min",
    "cook_time_min",
    "difficulty",
    "ingredients",
    "steps",
    "tips",
    "tags",
)


def recipe_fields(generated: dict[str, Any]) -> dict[str, Any]:
    """Campos de `Recipe` a partir da receita canônica do vídeo (validada pelo schema do LLM)."""
    data = RecipeLLM.model_validate(generated).model_dump(mode="json")
    return {name: data[name] for name in RECIPE_FIELDS}


def is_ready(video: Video) -> bool:
    """O vídeo já tem uma receita válida gerada com o prompt atual."""
    return (
        video.generated_recipe is not None
        and video.prompt_version == recipe_llm.PROMPT_VERSION
        and bool(video.generated_recipe.get("is_recipe"))
    )


async def find_user_recipe_id(
    session: AsyncSession, user_id: uuid.UUID, youtube_id: str
) -> uuid.UUID | None:
    return await session.scalar(
        select(Recipe.id)
        .join(Video, Recipe.video_id == Video.id)
        .where(Recipe.user_id == user_id, Video.youtube_id == youtube_id)
    )


async def find_ready_video(session: AsyncSession, youtube_id: str) -> Video | None:
    video = await session.scalar(select(Video).where(Video.youtube_id == youtube_id))
    return video if video is not None and is_ready(video) else None


async def copy_recipe(session: AsyncSession, user_id: uuid.UUID, video: Video) -> uuid.UUID:
    """Cria a cópia do usuário; se outro import já criou (UNIQUE user+vídeo), devolve a existente.

    Não faz commit.
    """
    assert video.generated_recipe is not None
    recipe_id = await session.scalar(
        insert(Recipe)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            video_id=video.id,
            **recipe_fields(video.generated_recipe),
        )
        .on_conflict_do_nothing(index_elements=[Recipe.user_id, Recipe.video_id])
        .returning(Recipe.id)
    )
    if recipe_id is None:
        recipe_id = await session.scalar(
            select(Recipe.id).where(Recipe.user_id == user_id, Recipe.video_id == video.id)
        )
    assert recipe_id is not None
    return recipe_id


async def existing_recipe_id(
    session: AsyncSession, user_id: uuid.UUID, youtube_id: str
) -> uuid.UUID | None:
    """Receita do vídeo no livro do usuário, copiando a canônica se o vídeo já está pronto.

    Não faz commit.
    """
    recipe_id = await find_user_recipe_id(session, user_id, youtube_id)
    if recipe_id is None:
        video = await find_ready_video(session, youtube_id)
        if video is not None:
            recipe_id = await copy_recipe(session, user_id, video)
    return recipe_id


async def complete_from_existing(session: AsyncSession, imp: Import) -> bool:
    """Conclui o import sem processar quando o usuário já tem a receita ou o vídeo está pronto.

    Faz commit e devolve True se concluiu.
    """
    recipe_id = await existing_recipe_id(session, imp.user_id, imp.youtube_id)
    if recipe_id is not None:
        mark_done(imp, recipe_id)
    await session.commit()
    return recipe_id is not None


def mark_done(imp: Import, recipe_id: uuid.UUID, *, charged: bool = False) -> None:
    """Conclui o import; `charged` quando ele gerou uma receita nova com o Claude (gasta cota)."""
    imp.status = ImportStatus.DONE
    imp.recipe_id = recipe_id
    imp.error_code = None
    imp.error_message = None
    imp.charged_at = datetime.now(UTC) if charged else None


def mark_cost_incurred(imp: Import) -> None:
    """O import gastou Claude ou whisper: se falhar, conta no limite diário de falhas caras."""
    if imp.cost_incurred_at is None:
        imp.cost_incurred_at = datetime.now(UTC)


def mark_failed(imp: Import, error: AppError) -> None:
    imp.status = ImportStatus.FAILED
    imp.error_code = error.code
    imp.error_message = error.message


def mark_deferred(imp: Import, reason: LLMBudgetExceededError) -> None:
    """Adia o import; o motivo fica em `error_*` para o usuário até ele voltar para a fila."""
    imp.status = ImportStatus.DEFERRED
    imp.error_code = reason.code
    imp.error_message = reason.message
    if imp.deferred_at is None:
        imp.deferred_at = datetime.now(UTC)


def mark_resumed(imp: Import) -> None:
    imp.status = ImportStatus.PENDING
    imp.error_code = None
    imp.error_message = None


async def _lock_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Trava o usuário até o fim da transação: pedidos simultâneos dele passam um de cada vez."""
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def create_import(
    session: AsyncSession, redis: ArqRedis, user: User, url: str
) -> tuple[Import, bool]:
    """Valida a URL e cria o import. Devolve o import e se ele foi para a fila.

    Antes de enfileirar, tenta concluir na hora: receita já no livro do usuário, vídeo já
    processado por outra pessoa (cópia) ou um import do mesmo vídeo ainda em andamento
    (devolve esse mesmo import). Nenhum desses gasta cota; só um import que vai para a fila
    precisa de cota livre (`QuotaExceededError`) e de não ter estourado o limite de falhas caras
    do dia (`TooManyFailedImportsError`). Os pedidos do mesmo usuário são serializados
    para que dois imports simultâneos não passem juntos do limite nem dupliquem o mesmo vídeo.
    """
    youtube_id = youtube.extract_youtube_id(url)
    await _lock_user(session, user.id)

    in_flight = await session.scalar(
        select(Import)
        .where(
            Import.user_id == user.id,
            Import.youtube_id == youtube_id,
            Import.status.in_(list(UNFINISHED_IMPORT_STATUSES)),
        )
        .order_by(Import.created_at.desc())
        .limit(1)
    )
    if in_flight is not None:
        await session.commit()
        return in_flight, False

    imp = Import(user_id=user.id, url=url.strip(), youtube_id=youtube_id)
    recipe_id = await existing_recipe_id(session, user.id, youtube_id)
    if recipe_id is not None:
        mark_done(imp, recipe_id)
        session.add(imp)
        await session.commit()
        logger.info("import %s concluído sem fila (vídeo %s)", imp.id, youtube_id)
        return imp, False

    await quotas.ensure_import_quota(session, user.id)
    session.add(imp)
    await session.commit()

    try:
        await queue.enqueue_import(redis, imp.id)
    except (RedisError, OSError) as exc:
        logger.error("falha ao enfileirar import %s: %r", imp.id, exc)
        error = QueueUnavailableError(detail=repr(exc))
        mark_failed(imp, error)
        await session.commit()
        raise error from exc
    return imp, True


async def queue_position(redis: ArqRedis, imp: Import) -> int | None:
    """Posição aproximada na fila: a padrão enquanto pendente, a do whisper ao transcrever."""
    try:
        if imp.status is ImportStatus.PENDING:
            return await queue.queue_position(
                redis, queue.DEFAULT_QUEUE, queue.import_job_id(imp.id)
            )
        if imp.status is ImportStatus.TRANSCRIBING:
            return await queue.queue_position(
                redis, queue.WHISPER_QUEUE, queue.whisper_job_id(imp.youtube_id)
            )
    except RedisError as exc:
        logger.warning("posição na fila indisponível para %s: %r", imp.id, exc)
    return None
