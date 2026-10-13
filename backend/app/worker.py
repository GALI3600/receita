"""Workers arq do pipeline de import.

    arq app.worker.WorkerSettings --custom-log-dict app.worker.LOG_CONFIG
    arq app.worker.WhisperWorkerSettings --custom-log-dict app.worker.LOG_CONFIG

O primeiro atende a fila padrão: metadados, legendas e Claude (`process_import`), além da
varredura periódica de imports parados. O segundo atende só a fila do whisper
(`transcribe_whisper`), com concorrência `WHISPER_MAX_JOBS` e o modelo carregado no startup.

Fluxo de um import: pending → fetching → transcribing → generating → done | failed.
Sem legenda, o import fica em `transcribing` enquanto o job do whisper (um por vídeo) roda;
ao terminar, ele reenfileira todos os imports que esperavam aquele vídeo, que seguem para o
Claude. Um lock por vídeo no Redis garante que só um import por vez processa o mesmo vídeo; os
outros esperam (o arq reagenda o job) e, quando a receita fica pronta, só copiam.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from arq import Retry, cron, func
from arq.connections import ArqRedis
from arq.logs import default_log_config
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import select, update
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.config import get_settings
from app.db import SessionLocal, engine
from app.errors import ImportTimeoutError, InternalError, PipelineError
from app.models import ACTIVE_IMPORT_STATUSES, Import, ImportStatus
from app.services import imports, pipeline, transcription
from app.services.locks import VideoLock

logger = logging.getLogger(__name__)

Ctx = dict[str, Any]

LOG_CONFIG = default_log_config(verbose=False)
LOG_CONFIG["formatters"]["arq.standard"]["format"] = (
    "%(asctime)s %(levelname)s %(name)s: %(message)s"
)
LOG_CONFIG["loggers"]["app"] = {"handlers": ["arq.standard"], "level": "INFO"}

# Espera pelo lock do vídeo: o arq reagenda o job com intervalos crescentes até este teto.
LOCK_WAIT_MAX_S = 15
# Cada espera pelo lock conta como uma tentativa para o arq; as falhas transitórias têm um
# contador próprio no Redis (IMPORT_MAX_RETRIES).
PROCESS_IMPORT_MAX_TRIES = 1000
RETRY_COUNTER_TTL_S = 24 * 3600
STALE_CHECK_AFTER = timedelta(minutes=5)

_TRANSIENT_ERRORS = (
    ConnectionError,
    RedisConnectionError,
    RedisTimeoutError,
    OperationalError,
    InterfaceError,
)


def classify_failure(exc: Exception) -> tuple[PipelineError, bool]:
    """Erro a gravar no import e se vale tentar de novo."""
    if isinstance(exc, PipelineError):
        return exc, exc.transient
    if isinstance(exc, TimeoutError):
        return ImportTimeoutError(detail="tempo do job esgotado"), True
    return InternalError(detail=f"{type(exc).__name__}: {exc}"), isinstance(exc, _TRANSIENT_ERRORS)


# --- Fila padrão ------------------------------------------------------------------------------


async def process_import(ctx: Ctx, import_id: str) -> str:
    settings = get_settings()
    redis: ArqRedis = ctx["redis"]
    async with ctx["sessionmaker"]() as session:
        imp = await session.get(Import, uuid.UUID(import_id))
        await session.commit()
        if imp is None or imp.status not in ACTIVE_IMPORT_STATUSES:
            return "ignorado"
        if await imports.complete_from_existing(session, imp):
            return "reaproveitado"

        lock = VideoLock(redis, imp.youtube_id, ttl_s=settings.import_job_timeout_s + 60)
        if not await lock.acquire():
            # Outro import está processando o mesmo vídeo; quando ele terminar, este só copia.
            raise Retry(defer=min(2 * ctx["job_try"], LOCK_WAIT_MAX_S))
        try:
            async with asyncio.timeout(settings.import_job_timeout_s):
                return await _run_import(session, redis, imp)
        except Exception as exc:
            return await _handle_failure(redis, session, imp, exc)
        finally:
            await lock.release()


async def _run_import(session: AsyncSession, redis: ArqRedis, imp: Import) -> str:
    async def stage(status: ImportStatus) -> None:
        imp.status = status
        await session.commit()

    video = await pipeline.find_video(session, imp.youtube_id)
    has_transcript = video is not None and video.transcript is not None
    # De volta do whisper: os metadados foram validados por este mesmo import há pouco.
    if not (imp.status is ImportStatus.TRANSCRIBING and has_transcript):
        if not has_transcript and await _join_whisper(session, redis, imp):
            return "aguardando whisper"

        await stage(ImportStatus.FETCHING)
        video, meta = await pipeline.fetch_video(session, imp.youtube_id)
        if meta is not None:
            await stage(ImportStatus.TRANSCRIBING)
            transcript = await transcription.transcribe_from_subtitles(
                meta.subtitles, meta.language, meta.duration_s
            )
            if transcript is None:
                await queue.enqueue_whisper(redis, imp.youtube_id, meta.language)
                logger.info(
                    "import %s: vídeo %s sem legenda; fila do whisper", imp.id, meta.youtube_id
                )
                return "na fila do whisper"
            await pipeline.save_transcript(session, video, transcript)

    assert video is not None
    video = await pipeline.generate(session, video, on_stage=stage)
    imports.mark_done(imp, await imports.copy_recipe(session, imp.user_id, video))
    await session.commit()
    return "concluído"


async def _join_whisper(session: AsyncSession, redis: ArqRedis, imp: Import) -> bool:
    """Se o vídeo já está com o whisper (por outro import), passa a esperar por ele.

    O status muda antes de reler a transcrição: se o whisper terminar no meio, ou ele já vê
    este import como `transcribing` e o reenfileira, ou a releitura encontra a transcrição.
    """
    if not await queue.job_exists(redis, queue.whisper_job_id(imp.youtube_id)):
        return False
    imp.status = ImportStatus.TRANSCRIBING
    await session.commit()
    video = await pipeline.find_video(session, imp.youtube_id)
    return video is None or video.transcript is None


async def _handle_failure(
    redis: ArqRedis, session: AsyncSession, imp: Import, exc: Exception
) -> str:
    settings = get_settings()
    import_id = imp.id
    error, transient = classify_failure(exc)
    # O rollback expira os atributos de `imp`; daqui em diante só `import_id`, até o refresh.
    await session.rollback()

    if transient:
        key = f"receita:import-retries:{import_id}"
        retries = await redis.incr(key)
        await redis.expire(key, RETRY_COUNTER_TTL_S)
        if retries <= settings.import_max_retries:
            logger.warning(
                "import %s: falha transitória %r; nova tentativa %d/%d",
                import_id,
                error,
                retries,
                settings.import_max_retries,
            )
            raise Retry(defer=settings.import_retry_delay_s * retries) from exc

    if isinstance(error, InternalError):
        logger.error("import %s falhou com erro inesperado", import_id, exc_info=exc)
    else:
        logger.info("import %s falhou: %r", import_id, error)
    await session.refresh(imp)
    imports.mark_failed(imp, error)
    await session.commit()
    return f"falhou: {error.code}"


# --- Fila do whisper --------------------------------------------------------------------------


async def transcribe_whisper(ctx: Ctx, youtube_id: str, language: str | None) -> str:
    settings = get_settings()
    async with ctx["sessionmaker"]() as session:
        video = await pipeline.find_video(session, youtube_id)
        if video is None:
            return "ignorado"
        if video.transcript is None:
            try:
                async with asyncio.timeout(settings.whisper_job_timeout_s):
                    transcript = await transcription.transcribe_with_whisper(youtube_id, language)
            except Exception as exc:
                error, transient = classify_failure(exc)
                await session.rollback()
                # Estourar o tempo de novo com o mesmo áudio só gastaria mais CPU.
                if transient and not isinstance(exc, TimeoutError):
                    if ctx["job_try"] <= settings.import_max_retries:
                        logger.warning("whisper %s: falha transitória %r", youtube_id, error)
                        raise Retry(defer=settings.import_retry_delay_s * ctx["job_try"]) from exc
                logger.info("whisper %s falhou: %r", youtube_id, error)
                failed = await _fail_whisper_waiters(session, youtube_id, error)
                return f"falhou: {error.code} ({failed} import(s))"
            await pipeline.save_transcript(session, video, transcript)

        woken = await _wake_whisper_waiters(session, ctx["redis"], youtube_id)
        return f"transcrito; {woken} import(s) retomado(s)"


async def _whisper_waiters(session: AsyncSession, youtube_id: str) -> list[uuid.UUID]:
    ids = await session.scalars(
        select(Import.id).where(
            Import.youtube_id == youtube_id, Import.status == ImportStatus.TRANSCRIBING
        )
    )
    return list(ids)


async def _wake_whisper_waiters(session: AsyncSession, redis: ArqRedis, youtube_id: str) -> int:
    waiting = await _whisper_waiters(session, youtube_id)
    await session.commit()
    for import_id in waiting:
        await queue.enqueue_import(redis, import_id)
    return len(waiting)


async def _fail_whisper_waiters(
    session: AsyncSession, youtube_id: str, error: PipelineError
) -> int:
    result = await session.execute(
        update(Import)
        .where(Import.youtube_id == youtube_id, Import.status == ImportStatus.TRANSCRIBING)
        .values(status=ImportStatus.FAILED, error_code=error.code, error_message=error.message)
    )
    await session.commit()
    return result.rowcount


# --- Manutenção -------------------------------------------------------------------------------


async def recover_stale_imports(ctx: Ctx) -> str:
    """Reenfileira imports ativos sem job (perdidos num restart) e encerra os parados demais."""
    settings = get_settings()
    redis: ArqRedis = ctx["redis"]
    now = datetime.now(UTC)
    give_up_before = now - timedelta(minutes=settings.import_stale_after_min)
    async with ctx["sessionmaker"]() as session:
        stale = await session.scalars(
            select(Import).where(
                Import.status.in_(list(ACTIVE_IMPORT_STATUSES)),
                Import.updated_at < now - STALE_CHECK_AFTER,
            )
        )
        failed = requeued = 0
        for imp in stale.all():
            if imp.updated_at < give_up_before:
                imports.mark_failed(imp, ImportTimeoutError(detail="import parado"))
                failed += 1
            elif not await _has_job(redis, imp):
                await queue.enqueue_import(redis, imp.id)
                requeued += 1
        await session.commit()
    if failed or requeued:
        logger.warning("imports parados: %d reenfileirado(s), %d encerrado(s)", requeued, failed)
    return f"{requeued} reenfileirado(s), {failed} encerrado(s)"


async def _has_job(redis: ArqRedis, imp: Import) -> bool:
    if await queue.job_exists(redis, queue.import_job_id(imp.id)):
        return True
    return imp.status is ImportStatus.TRANSCRIBING and await queue.job_exists(
        redis, queue.whisper_job_id(imp.youtube_id)
    )


# --- Configuração dos workers -----------------------------------------------------------------


async def startup(ctx: Ctx) -> None:
    ctx["sessionmaker"] = SessionLocal


async def shutdown(ctx: Ctx) -> None:
    await engine.dispose()


async def whisper_startup(ctx: Ctx) -> None:
    await startup(ctx)
    await asyncio.to_thread(transcription.get_whisper_model)
    logger.info("modelo do whisper carregado")


_settings = get_settings()


class WorkerSettings:
    queue_name = queue.DEFAULT_QUEUE
    redis_settings = queue.redis_settings()
    functions = [
        func(
            process_import,
            name=queue.PROCESS_IMPORT,
            timeout=_settings.import_job_timeout_s + 60,
            max_tries=PROCESS_IMPORT_MAX_TRIES,
            keep_result=0,
        )
    ]
    cron_jobs = [
        cron(
            recover_stale_imports,
            minute=set(range(0, 60, 5)),
            run_at_startup=True,
            timeout=120,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10


class WhisperWorkerSettings:
    queue_name = queue.WHISPER_QUEUE
    redis_settings = queue.redis_settings()
    functions = [
        func(
            transcribe_whisper,
            name=queue.TRANSCRIBE_WHISPER,
            timeout=_settings.whisper_job_timeout_s + 60,
            # Folga para reinícios do worker (o arq conta o cancelamento como tentativa).
            max_tries=_settings.import_max_retries + 3,
            keep_result=0,
        )
    ]
    on_startup = whisper_startup
    on_shutdown = shutdown
    max_jobs = _settings.whisper_max_jobs
