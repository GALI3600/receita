"""Pipeline de um vídeo: URL → metadados → transcrição → receita gerada, salvo em `Video`.

`Video` é compartilhado entre usuários: transcrição e receita canônica são geradas uma única
vez e reaproveitadas (a receita só é refeita quando `PROMPT_VERSION` muda).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import (
    ErrorCode,
    ImportTimeoutError,
    LLMInvalidOutputError,
    LLMRefusedError,
    NotARecipeError,
    NoTranscriptError,
    PipelineError,
    TranscriptionGaveUpError,
    YoutubeBlockedError,
)
from app.models import ImportStatus, LLMCall, Video
from app.services import quotas, recipe_llm, transcription, youtube
from app.services.youtube import VideoMetadata

logger = logging.getLogger(__name__)

StageCallback = Callable[[ImportStatus], Awaitable[None]]

MIN_DESCRIPTION_WORDS = 15

# Falhas do Claude que se repetem com a mesma entrada: depois de N chamadas pagas com o mesmo
# prompt, o vídeo não volta para o Claude (até PROMPT_VERSION mudar). Erros transitórios
# (indisponível, 5xx) não entram: não chegam a gerar cobrança.
LLM_FAILURE_LIMITS: dict[ErrorCode, tuple[type[PipelineError], int]] = {
    ErrorCode.LLM_REFUSED: (LLMRefusedError, 1),
    ErrorCode.LLM_INVALID_OUTPUT: (LLMInvalidOutputError, 2),
}

# Execuções do whisper por vídeo, somando todos os imports: as tentativas de um job (falhas
# transitórias) e uma margem para reinícios do worker, que também contam. Estourar o tempo não
# tem nova chance: com o mesmo áudio, demoraria o mesmo tanto de novo.
WHISPER_MAX_ATTEMPTS = 4


async def process_video(
    url: str,
    session: AsyncSession,
    *,
    skip_llm: bool = False,
    on_stage: StageCallback | None = None,
) -> Video:
    """Processa o vídeo de ponta a ponta e devolve o `Video` com transcrição e receita gerada.

    Levanta `PipelineError` (app.errors) com código estável em qualquer falha do domínio.
    A sessão precisa ter `expire_on_commit=False` (como `SessionLocal`): toda leitura termina
    com commit para que nenhuma transação fique aberta durante yt-dlp, whisper ou Claude.
    O worker usa as mesmas etapas separadamente, para mandar o whisper para a fila dele.
    """

    async def stage(status: ImportStatus) -> None:
        if on_stage is not None:
            await on_stage(status)

    youtube_id = youtube.extract_youtube_id(url)
    await stage(ImportStatus.FETCHING)
    video, meta = await fetch_video(session, youtube_id)
    if meta is not None:
        await stage(ImportStatus.TRANSCRIBING)
        await save_transcript(session, video, await transcription.transcribe(meta))

    if skip_llm:
        return video
    video, _ = await generate(session, video, on_stage=on_stage)
    return video


async def find_video(session: AsyncSession, youtube_id: str) -> Video | None:
    video = await _get_video(session, youtube_id)
    await session.commit()
    return video


async def fetch_video(session: AsyncSession, youtube_id: str) -> tuple[Video, VideoMetadata | None]:
    """Busca e valida os metadados (passo 1 do fluxo) e grava o `Video`.

    Devolve também os metadados quando o vídeo ainda precisa ser transcrito (eles trazem as
    legendas); para um vídeo já transcrito devolve `None` no lugar deles.
    """
    video = await find_video(session, youtube_id)
    if video is not None and video.transcript is not None:
        await _revalidate(session, video)
        logger.info("vídeo %s já transcrito; reaproveitando", youtube_id)
        return video, None

    meta = await youtube.fetch_metadata(youtube_id)
    youtube.validate_metadata(meta)
    return await _save_metadata(session, video, meta), meta


async def save_transcript(
    session: AsyncSession, video: Video, transcript: transcription.Transcript
) -> None:
    video.transcript = transcript.segments
    video.transcript_source = transcript.source
    await session.commit()
    logger.info(
        "vídeo %s transcrito (%s, %d palavras)",
        video.youtube_id,
        transcript.source,
        transcript.word_count,
    )


async def generate(
    session: AsyncSession, video: Video, *, on_stage: StageCallback | None = None
) -> tuple[Video, bool]:
    """Gera a receita canônica com o Claude, se ainda não houver uma com o prompt atual.

    Devolve o vídeo e se esta chamada gerou uma receita nova (só essas gastam a cota do
    usuário). Levanta `NotARecipeError`/`NoTranscriptError` quando o vídeo não traz receita e
    `LLMBudgetExceededError` quando o orçamento do dia acabou e a receita ainda não existe.
    """
    if video.transcript is None:
        raise ValueError(f"vídeo {video.youtube_id} ainda não foi transcrito")

    has_speech = transcription.is_useful_transcript(video.transcript, video.duration_s)
    generated = video.generated_recipe is None or video.prompt_version != recipe_llm.PROMPT_VERSION
    if generated:
        if not has_speech and len(video.description.split()) < MIN_DESCRIPTION_WORDS:
            raise NoTranscriptError(detail="sem fala útil e descrição curta")
        await _raise_if_llm_gave_up(session, video)
        await quotas.ensure_llm_budget(session)

        if on_stage is not None:
            await on_stage(ImportStatus.GENERATING)
        try:
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
        except PipelineError as exc:
            if exc.llm_usage is not None:
                _add_llm_call(session, video, exc.llm_model, exc.llm_usage, exc.code)
                await session.commit()
            raise

        _add_llm_call(session, video, generation.model, generation.usage, None)
        video.generated_recipe = generation.recipe.model_dump(mode="json")
        video.llm_model = generation.model
        video.llm_usage = generation.usage
        video.prompt_version = generation.prompt_version
        await session.commit()
    else:
        logger.info("vídeo %s já tem receita (prompt %s)", video.youtube_id, video.prompt_version)

    if not video.generated_recipe.get("is_recipe"):
        if not has_speech:
            raise NoTranscriptError(detail="sem fala útil e a descrição não traz a receita")
        raise NotARecipeError(detail=video.generated_recipe.get("summary"))
    return video, generated


async def _get_video(session: AsyncSession, youtube_id: str) -> Video | None:
    # populate_existing: com expire_on_commit=False, um Video já carregado na sessão ficaria com
    # os dados antigos (ex.: a transcrição que o worker do whisper gravou depois).
    return await session.scalar(
        select(Video)
        .where(Video.youtube_id == youtube_id)
        .execution_options(populate_existing=True)
    )


async def _revalidate(session: AsyncSession, video: Video) -> None:
    """Confere de novo os metadados de um vídeo já processado (passo 1 do fluxo do plano).

    Desde o primeiro import ele pode ter ficado privado, deixado de ser incorporável ou passado
    do limite de duração. Bloqueio do YouTube não impede o reaproveitamento: o problema é do
    acesso do servidor, o vídeo continua válido e o embed oficial não é afetado.
    """
    try:
        meta = await youtube.fetch_metadata(video.youtube_id)
    except YoutubeBlockedError as exc:
        logger.warning(
            "vídeo %s: metadados indisponíveis (%r); usando os salvos", video.youtube_id, exc
        )
        return
    youtube.validate_metadata(meta)
    await _save_metadata(session, video, meta)


async def _raise_if_llm_gave_up(session: AsyncSession, video: Video) -> None:
    rows = (
        await session.execute(
            select(LLMCall.error_code, func.count())
            .where(
                LLMCall.video_id == video.id,
                LLMCall.prompt_version == recipe_llm.PROMPT_VERSION,
                LLMCall.error_code.in_(list(LLM_FAILURE_LIMITS)),
            )
            .group_by(LLMCall.error_code)
        )
    ).all()
    await session.commit()
    for code, count in rows:
        error, limit = LLM_FAILURE_LIMITS[ErrorCode(code)]
        if count >= limit:
            raise error(
                detail=f"{count} falha(s) com o prompt {recipe_llm.PROMPT_VERSION}; "
                "o Claude não é chamado de novo"
            )


def raise_if_whisper_gave_up(video: Video) -> None:
    """Levanta `TranscriptionGaveUpError` se o vídeo não deve voltar para o whisper."""
    if video.whisper_error_code == ImportTimeoutError.code:
        raise TranscriptionGaveUpError(detail="o whisper já estourou o tempo com este vídeo")
    if video.whisper_attempts >= WHISPER_MAX_ATTEMPTS:
        raise TranscriptionGaveUpError(
            detail=f"{video.whisper_attempts} execuções do whisper sem transcrição "
            f"(último erro: {video.whisper_error_code})"
        )


def _add_llm_call(
    session: AsyncSession,
    video: Video,
    model: str | None,
    usage: dict[str, Any],
    error_code: ErrorCode | None,
) -> None:
    session.add(
        LLMCall(
            video_id=video.id,
            model=model or recipe_llm.MODEL,
            prompt_version=recipe_llm.PROMPT_VERSION,
            usage=usage,
            error_code=error_code,
        )
    )


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
