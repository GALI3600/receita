"""Pipeline de um vídeo: URL → metadados → transcrição → receita gerada, salvo em `Video`.

`Video` é compartilhado entre usuários: transcrição e receita canônica são geradas uma única
vez e reaproveitadas (a receita só é refeita quando `PROMPT_VERSION` muda).
"""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotARecipeError, NoTranscriptError
from app.models import ImportStatus, Video
from app.services import recipe_llm, transcription, youtube
from app.services.youtube import VideoMetadata

logger = logging.getLogger(__name__)

StageCallback = Callable[[ImportStatus], Awaitable[None]]

MIN_DESCRIPTION_WORDS = 15


async def process_video(
    url: str,
    session: AsyncSession,
    *,
    skip_llm: bool = False,
    on_stage: StageCallback | None = None,
) -> Video:
    """Processa o vídeo e devolve o `Video` com transcrição e receita gerada.

    Levanta `PipelineError` (app.errors) com código estável em qualquer falha do domínio.
    A sessão precisa ter `expire_on_commit=False` (como `SessionLocal`).
    """

    async def stage(status: ImportStatus) -> None:
        if on_stage is not None:
            await on_stage(status)

    youtube_id = youtube.extract_youtube_id(url)
    video = await _get_video(session, youtube_id)

    if video is None or video.transcript is None:
        await stage(ImportStatus.FETCHING)
        meta = await youtube.fetch_metadata(youtube_id)
        youtube.validate_metadata(meta)
        video = await _save_metadata(session, video, meta)

        await stage(ImportStatus.TRANSCRIBING)
        transcript = await transcription.transcribe(meta)
        video.transcript = transcript.segments
        video.transcript_source = transcript.source
        await session.commit()
        logger.info(
            "vídeo %s transcrito (%s, %d palavras)",
            youtube_id,
            transcript.source,
            transcript.word_count,
        )
    else:
        logger.info("vídeo %s já transcrito; reaproveitando", youtube_id)

    if skip_llm:
        return video

    has_speech = transcription.is_useful_transcript(video.transcript)
    if video.generated_recipe is None or video.prompt_version != recipe_llm.PROMPT_VERSION:
        if not has_speech and len(video.description.split()) < MIN_DESCRIPTION_WORDS:
            raise NoTranscriptError(detail="sem fala útil e descrição curta")

        await stage(ImportStatus.GENERATING)
        generation = await recipe_llm.generate_recipe(
            recipe_llm.VideoContext(
                title=video.title,
                channel=video.channel,
                duration_s=video.duration_s,
                description=video.description,
                segments=video.transcript if has_speech else [],
                transcript_source=video.transcript_source if has_speech else None,
            )
        )
        video.generated_recipe = generation.recipe.model_dump(mode="json")
        video.llm_model = generation.model
        video.llm_usage = generation.usage
        video.prompt_version = generation.prompt_version
        await session.commit()
    else:
        logger.info("vídeo %s já tem receita (prompt %s)", youtube_id, video.prompt_version)

    if not video.generated_recipe.get("is_recipe"):
        if not has_speech:
            raise NoTranscriptError(detail="sem fala útil e a descrição não traz a receita")
        raise NotARecipeError(detail=video.generated_recipe.get("summary"))
    return video


async def _get_video(session: AsyncSession, youtube_id: str) -> Video | None:
    return await session.scalar(select(Video).where(Video.youtube_id == youtube_id))


def _apply_metadata(video: Video, meta: VideoMetadata) -> None:
    video.title = meta.title
    video.channel = meta.channel
    video.duration_s = meta.duration_s
    video.thumbnail_url = meta.thumbnail_url
    video.description = meta.description
    video.embeddable = meta.embeddable


async def _save_metadata(session: AsyncSession, video: Video | None, meta: VideoMetadata) -> Video:
    """Grava os metadados antes de transcrever, para que o vídeo já exista para outros imports."""
    if video is None:
        video = Video(youtube_id=meta.youtube_id)
        _apply_metadata(video, meta)
        session.add(video)
        try:
            await session.commit()
            return video
        except IntegrityError:
            # Outro processo criou o mesmo vídeo entre a busca e o insert.
            await session.rollback()
            video = await _get_video(session, meta.youtube_id)
            if video is None:
                raise

    _apply_metadata(video, meta)
    await session.commit()
    return video
