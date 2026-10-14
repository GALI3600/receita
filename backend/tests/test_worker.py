import asyncio
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from arq import Retry
from arq.connections import ArqRedis
from arq.constants import in_progress_key_prefix, job_key_prefix, result_key_prefix
from arq.worker import create_worker
from httpx import AsyncClient
from sqlalchemy import event, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import queue, worker
from app.config import get_settings
from app.errors import (
    InternalError,
    LLMBudgetExceededError,
    LLMMissingKeyError,
    LLMOutputTooLongError,
    LLMRefusedError,
    LLMUnavailableError,
    NotEmbeddableError,
    TranscriptionFailedError,
    TranscriptionGaveUpError,
    YoutubeBlockedError,
)
from app.models import Import, ImportStatus, LLMCall, LLMPurpose, Recipe, User, Video
from app.schemas.imports import ImportOut
from app.schemas.recipe_llm import RecipeLLM
from app.schemas.transcript import Segment, TranscriptSource
from app.services import imports, llm_calls, pipeline, recipe_llm, transcription, youtube
from app.services.locks import VideoLock
from app.services.recipe_llm import PROMPT_VERSION, RecipeGeneration, VideoContext
from app.services.transcription import Transcript
from app.services.youtube import SubtitleTrack, VideoMetadata
from tests.factories import GENERATED, SPEECH, headers, make_user, make_video, youtube_id

YOUTUBE_ID = "abcdefghijk"
WHISPER_SPEECH = [
    Segment(start=1.0, end=2.0, text="misture a farinha com os ovos") for _ in range(6)
]
TRACK = SubtitleTrack("pt", "manual", False, {"json3": "https://example.com/sub"})
META = VideoMetadata(
    youtube_id=YOUTUBE_ID,
    title="Bolo de cenoura",
    channel="Receitas",
    duration_s=600,
    thumbnail_url=None,
    description="",
    embeddable=True,
    availability="public",
    live_status="not_live",
    age_limit=0,
    language="pt",
    subtitles=[TRACK],
)


@dataclass
class FakeServices:
    """Troca YouTube, legendas, whisper e Claude; grava o status do import em cada chamada."""

    session_factory: async_sessionmaker[AsyncSession]
    meta: VideoMetadata = META
    subtitles: Transcript | None = field(
        default_factory=lambda: Transcript(SPEECH, TranscriptSource.MANUAL)
    )
    metadata_error: Exception | None = None
    whisper_error: Exception | None = None
    llm_error: Exception | None = None
    llm_recipe: dict[str, Any] = field(default_factory=lambda: GENERATED)
    llm_delay_s: float = 0
    calls: list[str] = field(default_factory=list)
    statuses: list[ImportStatus] = field(default_factory=list)

    async def _record(self, call: str) -> None:
        self.calls.append(call)
        async with self.session_factory() as session:
            status = await session.scalar(select(Import.status).order_by(Import.created_at))
        if status is not None:
            self.statuses.append(status)

    async def fetch_metadata(self, youtube_id: str) -> VideoMetadata:
        await self._record("metadata")
        if self.metadata_error:
            raise self.metadata_error
        return replace(self.meta, youtube_id=youtube_id)

    async def transcribe_from_subtitles(self, *args: Any) -> Transcript | None:
        await self._record("subtitles")
        return self.subtitles

    async def transcribe_with_whisper(self, youtube_id: str, language: str | None) -> Transcript:
        self.calls.append(f"whisper:{language}")
        if self.whisper_error:
            raise self.whisper_error
        return Transcript(WHISPER_SPEECH, TranscriptSource.WHISPER)

    async def generate_recipe(self, video: VideoContext, **_: Any) -> RecipeGeneration:
        await self._record("llm")
        await asyncio.sleep(self.llm_delay_s)
        if self.llm_error:
            raise self.llm_error
        return RecipeGeneration(
            recipe=RecipeLLM.model_validate(self.llm_recipe),
            model=recipe_llm.MODEL,
            usage={"input_tokens": 100, "output_tokens": 50},
            prompt_version=PROMPT_VERSION,
        )


@pytest.fixture
def fake(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> FakeServices:
    services = FakeServices(session_factory)
    monkeypatch.setattr(youtube, "fetch_metadata", services.fetch_metadata)
    monkeypatch.setattr(
        transcription, "transcribe_from_subtitles", services.transcribe_from_subtitles
    )
    monkeypatch.setattr(transcription, "transcribe_with_whisper", services.transcribe_with_whisper)
    monkeypatch.setattr(recipe_llm, "generate_recipe", services.generate_recipe)
    return services


@pytest.fixture
def ctx(redis: ArqRedis, session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    return {"redis": redis, "sessionmaker": session_factory, "job_try": 1}


@pytest.fixture
def job_deadlines(monkeypatch: pytest.MonkeyPatch) -> list[asyncio.Timeout]:
    """Prazos (`asyncio.timeout`) dos jobs de import, para vencê-los no ponto exato do teste."""
    deadlines: list[asyncio.Timeout] = []
    real_timeout = asyncio.timeout
    job_timeout_s = get_settings().import_job_timeout_s

    def timeout(delay: float | None) -> asyncio.Timeout:
        if delay != job_timeout_s:
            return real_timeout(delay)
        deadline = real_timeout(None)
        deadlines.append(deadline)
        return deadline

    monkeypatch.setattr(asyncio, "timeout", timeout)
    return deadlines


def _expire(deadlines: list[asyncio.Timeout]) -> None:
    """Vence o prazo do job: o cancelamento chega no próximo `await` da tarefa."""
    deadlines[-1].reschedule(asyncio.get_running_loop().time())


def _on_sql(engine: AsyncEngine, matches: str, action: Callable[[], None]) -> None:
    """Roda `action` antes de cada comando SQL que começa com `matches`."""

    def before_cursor_execute(*args: Any) -> None:
        statement: str = args[2]
        if statement.startswith(matches):
            action()

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


async def _new_import(
    session: AsyncSession, user: User | None = None, yt_id: str = YOUTUBE_ID
) -> Import:
    user = user or await make_user(session)
    imp = Import(user_id=user.id, url=f"https://youtu.be/{yt_id}", youtube_id=yt_id)
    session.add(imp)
    await session.commit()
    return imp


async def _reload(session: AsyncSession, imp: Import) -> Import:
    loaded = await session.get(Import, imp.id, populate_existing=True)
    assert loaded is not None
    return loaded


async def _run(ctx: dict[str, Any], imp: Import) -> str:
    return await worker.process_import(ctx, str(imp.id))


async def test_full_run_with_subtitles(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "concluído"

    assert fake.calls == ["metadata", "subtitles", "llm"]
    assert fake.statuses == [
        ImportStatus.FETCHING,
        ImportStatus.TRANSCRIBING,
        ImportStatus.GENERATING,
    ]
    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.DONE
    assert imp.error_code is None
    recipe = await session.get(Recipe, imp.recipe_id)
    assert recipe is not None
    assert recipe.user_id == imp.user_id
    assert recipe.title == GENERATED["title"]
    video = await session.scalar(select(Video))
    assert video is not None and video.transcript == SPEECH
    assert await redis.keys("receita:lock:*") == []


async def test_done_import_is_not_processed_again(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    imp = await _new_import(session)
    await _run(ctx, imp)
    fake.calls.clear()

    assert await _run(ctx, imp) == "ignorado"
    assert await worker.process_import(ctx, str(uuid.uuid4())) == "ignorado"
    assert fake.calls == []


async def test_ready_video_is_copied_without_services(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    await make_video(session, YOUTUBE_ID)
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "reaproveitado"

    assert fake.calls == []
    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.DONE and imp.recipe_id is not None


async def test_without_subtitles_goes_to_whisper_queue_and_back(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    fake.subtitles = None
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "na fila do whisper"

    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.TRANSCRIBING
    whisper_jobs = await redis.queued_jobs(queue_name=queue.WHISPER_QUEUE)
    assert [(j.job_id, j.function, j.args) for j in whisper_jobs] == [
        (f"whisper:{YOUTUBE_ID}", queue.TRANSCRIBE_WHISPER, (YOUTUBE_ID, "pt"))
    ]
    assert await redis.queued_jobs() == []
    assert await redis.keys("receita:lock:*") == []

    result = await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")

    assert result == "transcrito; 1 import(s) retomado(s)"
    assert [j.job_id for j in await redis.queued_jobs()] == [f"import:{imp.id}"]
    video = await session.scalar(select(Video).execution_options(populate_existing=True))
    assert video is not None
    assert (video.transcript, video.transcript_source) == (WHISPER_SPEECH, "whisper")

    fake.calls.clear()
    fake.statuses.clear()
    assert await _run(ctx, imp) == "concluído"

    # Na volta do whisper não busca os metadados de novo.
    assert fake.calls == ["llm"]
    assert fake.statuses == [ImportStatus.GENERATING]
    assert (await _reload(session, imp)).status is ImportStatus.DONE


async def test_second_import_waits_for_whisper_of_the_same_video(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    fake.subtitles = None
    first = await _new_import(session)
    await _run(ctx, first)
    second = await _new_import(session)
    fake.calls.clear()

    assert await _run(ctx, second) == "aguardando whisper"

    assert fake.calls == []
    assert (await _reload(session, second)).status is ImportStatus.TRANSCRIBING

    await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")
    queued = {j.job_id for j in await redis.queued_jobs()}
    assert queued == {f"import:{first.id}", f"import:{second.id}"}

    assert await _run(ctx, first) == "concluído"
    assert await _run(ctx, second) == "reaproveitado"
    assert fake.calls.count("llm") == 1
    assert fake.calls.count("whisper:pt") == 1


async def test_import_waits_while_another_job_holds_the_video(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    imp = await _new_import(session)
    other = VideoLock(redis, YOUTUBE_ID, ttl_s=60)
    assert await other.acquire()

    with pytest.raises(Retry):
        await _run(ctx, imp)

    assert fake.calls == []
    assert (await _reload(session, imp)).status is ImportStatus.PENDING

    # O outro job termina e deixa a receita pronta: este só copia.
    await make_video(session, YOUTUBE_ID)
    await other.release()
    assert await _run(ctx, imp) == "reaproveitado"
    assert fake.calls == []


async def test_concurrent_imports_call_claude_once(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    fake.llm_delay_s = 0.3
    users = [await make_user(session, name) for name in ("Ana", "Bia")]
    first, second = [await _new_import(session, user) for user in users]

    results = await asyncio.gather(_run(ctx, first), _run(ctx, second), return_exceptions=True)

    assert sorted(type(r).__name__ for r in results) == ["Retry", "str"]
    assert fake.calls.count("llm") == 1
    waiting = second if isinstance(results[1], Retry) else first
    assert await _run(ctx, waiting) == "reaproveitado"
    assert fake.calls.count("llm") == 1
    recipes = (await session.scalars(select(Recipe.user_id))).all()
    assert sorted(recipes) == sorted(user.id for user in users)


async def test_domain_error_fails_import(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    fake.llm_error = LLMMissingKeyError(detail="ANTHROPIC_API_KEY não configurada")
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "falhou: llm_missing_key"

    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.FAILED
    assert imp.error_code == "llm_missing_key"
    assert imp.error_message == LLMMissingKeyError.default_message
    assert imp.recipe_id is None
    assert await redis.keys("receita:lock:*") == []
    # A transcrição fica salva para a próxima tentativa.
    video = await session.scalar(select(Video).execution_options(populate_existing=True))
    assert video is not None and video.transcript == SPEECH


async def test_validation_error_fails_without_retry(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.meta = replace(META, embeddable=False)
    imp = await _new_import(session)

    await _run(ctx, imp)

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, NotEmbeddableError.code)
    assert fake.calls == ["metadata"]


@pytest.mark.parametrize(
    "error",
    [LLMUnavailableError(), OperationalError("SELECT 1", {}, ConnectionError("caiu"))],
    ids=["llm-indisponivel", "banco-caiu"],
)
async def test_transient_error_is_retried_then_fails(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, error: Exception
) -> None:
    fake.llm_error = error
    imp = await _new_import(session)
    retries = get_settings().import_max_retries

    for attempt in range(1, retries + 1):
        with pytest.raises(Retry) as exc_info:
            await _run(ctx, imp)
        assert exc_info.value.defer_score == get_settings().import_retry_delay_s * attempt * 1000
        assert (await _reload(session, imp)).status is not ImportStatus.FAILED

    await _run(ctx, imp)

    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.FAILED
    expected = error if isinstance(error, LLMUnavailableError) else InternalError()
    assert imp.error_code == expected.code
    assert fake.calls.count("llm") == retries + 1


async def test_unexpected_error_fails_without_retry(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = KeyError("bug")
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "falhou: internal_error"

    imp = await _reload(session, imp)
    assert imp.error_message == InternalError.default_message
    assert "bug" not in (imp.error_message or "")


async def test_output_too_long_fails_import_without_retry(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = LLMOutputTooLongError(
        llm_model=recipe_llm.MODEL, llm_usage={"output_tokens": recipe_llm.MAX_TOKENS}
    )
    imp = await _new_import(session)

    # Sem Retry: com o mesmo teto, o corte se repetiria.
    assert await _run(ctx, imp) == "falhou: llm_output_too_long"

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "llm_output_too_long")
    assert imp.error_message == LLMOutputTooLongError.default_message
    assert imp.cost_incurred_at is not None
    assert fake.calls.count("llm") == 1
    call = await session.scalar(select(LLMCall))
    assert call is not None
    assert (call.error_code, call.max_tokens) == ("llm_output_too_long", recipe_llm.MAX_TOKENS)


async def test_job_timeout_is_retried_then_fails(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    monkeypatch: pytest.MonkeyPatch,
    job_deadlines: list[asyncio.Timeout],
) -> None:
    async def stuck_llm(video: VideoContext, **_: Any) -> RecipeGeneration:
        fake.calls.append("llm")
        _expire(job_deadlines)
        await asyncio.Event().wait()
        raise AssertionError("não deveria terminar")

    monkeypatch.setattr(recipe_llm, "generate_recipe", stuck_llm)
    imp = await _new_import(session)
    retries = get_settings().import_max_retries

    for _ in range(retries):
        with pytest.raises(Retry):
            await _run(ctx, imp)
        assert (await _reload(session, imp)).status is ImportStatus.GENERATING

    assert await _run(ctx, imp) == "falhou: import_timeout"

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "import_timeout")
    assert fake.calls.count("llm") == retries + 1
    # Cada tentativa cancelada fica com o custo estimado: a API pode ter cobrado.
    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.usage) for c in calls] == [("llm_timeout", {})] * (retries + 1)
    assert all(c.cost_usd is not None and c.cost_usd > 0 for c in calls)


async def test_job_timeout_in_the_middle_of_a_commit_is_retried(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    db_engine: AsyncEngine,
    job_deadlines: list[asyncio.Timeout],
) -> None:
    imp = await _new_import(session)
    expired: list[bool] = []

    def expire_once() -> None:
        if not expired:
            expired.append(True)
            _expire(job_deadlines)

    # O prazo vence enquanto o UPDATE do status (FETCHING) espera a resposta do banco.
    _on_sql(db_engine, "UPDATE imports", expire_once)

    with pytest.raises(Retry):
        await _run(ctx, imp)

    assert expired and fake.calls == []
    assert (await _reload(session, imp)).status is ImportStatus.PENDING
    assert await _run(ctx, imp) == "concluído"


async def test_transient_db_error_on_commit_is_retried_then_fails(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, db_engine: AsyncEngine
) -> None:
    def connection_lost() -> None:
        raise OperationalError("UPDATE videos", {}, ConnectionError("caiu"))

    # Falha no flush do commit de save_transcript: a transação da sessão fica desativada.
    _on_sql(db_engine, "UPDATE videos SET transcript", connection_lost)
    imp = await _new_import(session)
    retries = get_settings().import_max_retries

    for _ in range(retries):
        with pytest.raises(Retry):
            await _run(ctx, imp)
        assert (await _reload(session, imp)).status is ImportStatus.TRANSCRIBING

    assert await _run(ctx, imp) == "falhou: internal_error"

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "internal_error")
    assert fake.calls.count("subtitles") == retries + 1


async def test_db_error_on_commit_fails_import(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    # Valor que não cabe na coluna: o banco recusa no commit de save_transcript.
    fake.subtitles = Transcript(SPEECH, "legenda-invalida")  # type: ignore[arg-type]
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "falhou: internal_error"

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "internal_error")


async def test_whisper_failure_fails_waiting_imports(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.subtitles = None
    fake.whisper_error = TranscriptionFailedError(detail="áudio corrompido")
    first = await _new_import(session)
    await _run(ctx, first)
    second = await _new_import(session)
    await _run(ctx, second)

    with pytest.raises(Retry):
        await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")

    last_try = {**ctx, "job_try": get_settings().import_max_retries + 1}
    result = await worker.transcribe_whisper(last_try, YOUTUBE_ID, "pt")

    assert result == "falhou: transcription_failed (2 import(s))"
    for imp in (first, second):
        imp = await _reload(session, imp)
        assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "transcription_failed")


async def test_whisper_timeout_is_not_retried(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    redis: ArqRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake.subtitles = None
    imp = await _new_import(session)
    await _run(ctx, imp)

    async def slow(youtube_id: str, language: str | None) -> Transcript:
        await asyncio.sleep(1)
        raise AssertionError("não deveria terminar")

    monkeypatch.setattr(transcription, "transcribe_with_whisper", slow)
    monkeypatch.setattr(get_settings(), "whisper_job_timeout_s", 0.05)

    await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")
    await _finish_whisper_job(redis)

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "import_timeout")

    # Um novo import do mesmo vídeo falha na hora: o whisper estouraria o tempo de novo.
    again = await _new_import(session)
    assert await _run(ctx, again) == "falhou: transcription_failed"
    assert await redis.queued_jobs(queue_name=queue.WHISPER_QUEUE) == []


async def _finish_whisper_job(redis: ArqRedis) -> None:
    """Tira o job do whisper do Redis, como o arq faz quando ele termina."""
    job_id = queue.whisper_job_id(YOUTUBE_ID)
    await redis.delete(job_key_prefix + job_id)
    await redis.zrem(queue.WHISPER_QUEUE, job_id)


async def _whisper_until_done(ctx: dict[str, Any]) -> str:
    """Roda o job do whisper como o arq: de novo a cada Retry, até ele terminar."""
    for job_try in range(1, 10):
        try:
            result = await worker.transcribe_whisper({**ctx, "job_try": job_try}, YOUTUBE_ID, "pt")
        except Retry:
            continue
        await _finish_whisper_job(ctx["redis"])
        return result
    raise AssertionError("o job do whisper não terminou")


async def _video(session: AsyncSession) -> Video:
    video = await session.scalar(select(Video).execution_options(populate_existing=True))
    assert video is not None
    return video


async def test_whisper_attempts_are_limited_per_video(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    fake.subtitles = None
    fake.whisper_error = TranscriptionFailedError(detail="áudio corrompido")
    first = await _new_import(session)
    await _run(ctx, first)

    assert await _whisper_until_done(ctx) == "falhou: transcription_failed (1 import(s))"
    runs = get_settings().import_max_retries + 1
    assert fake.calls.count("whisper:pt") == runs
    video = await _video(session)
    assert (video.whisper_attempts, video.whisper_error_code) == (runs, "transcription_failed")

    # Ainda há tentativas para o vídeo: um novo import volta para o whisper até o limite.
    second = await _new_import(session)
    assert await _run(ctx, second) == "na fila do whisper"
    assert await _whisper_until_done(ctx) == "falhou: transcription_failed (1 import(s))"
    assert fake.calls.count("whisper:pt") == pipeline.WHISPER_MAX_ATTEMPTS

    # Daqui em diante, o import falha sem entrar na fila do whisper.
    third = await _new_import(session)
    assert await _run(ctx, third) == "falhou: transcription_failed"
    assert await redis.queued_jobs(queue_name=queue.WHISPER_QUEUE) == []
    assert fake.calls.count("whisper:pt") == pipeline.WHISPER_MAX_ATTEMPTS
    third = await _reload(session, third)
    assert third.error_message == TranscriptionGaveUpError.default_message


async def test_whisper_run_killed_midway_counts_as_attempt(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.subtitles = None
    # Worker reiniciado ou morto por falta de memória: o job não chega ao tratamento de erro.
    fake.whisper_error = asyncio.CancelledError()
    imp = await _new_import(session)
    await _run(ctx, imp)

    for _ in range(pipeline.WHISPER_MAX_ATTEMPTS):
        with pytest.raises(asyncio.CancelledError):
            await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")

    result = await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")

    assert result == "falhou: transcription_failed (1 import(s))"
    assert fake.calls.count("whisper:pt") == pipeline.WHISPER_MAX_ATTEMPTS
    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "transcription_failed")


async def test_youtube_block_does_not_count_as_whisper_attempt(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.subtitles = None
    fake.whisper_error = YoutubeBlockedError()
    imp = await _new_import(session)
    await _run(ctx, imp)

    assert await _whisper_until_done(ctx) == "falhou: youtube_blocked (1 import(s))"

    video = await _video(session)
    assert (video.whisper_attempts, video.whisper_error_code) == (0, None)


async def test_waiter_whose_job_is_still_finishing_is_resumed(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, redis: ArqRedis
) -> None:
    fake.subtitles = None
    first = await _new_import(session)
    await _run(ctx, first)
    second = await _new_import(session)
    await queue.enqueue_import(redis, second.id)
    # O job de `second` acabou de sair com "aguardando whisper", mas o arq ainda não o
    # finalizou: o id `import:<id>` continua ocupado.
    assert await _run(ctx, second) == "aguardando whisper"
    await redis.set(in_progress_key_prefix + queue.import_job_id(second.id), b"1")

    result = await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")

    assert result == "transcrito; 2 import(s) retomado(s)"
    assert {j.job_id for j in await redis.queued_jobs()} == {
        f"import:{first.id}",
        f"import:{second.id}",
        f"import:{second.id}:resume",
    }
    assert await _run(ctx, second) == "concluído"


@pytest.mark.parametrize(
    ("settings", "function", "args", "job_id"),
    [
        (worker.WorkerSettings, queue.PROCESS_IMPORT, ("x",), "import:x"),
        (worker.WhisperWorkerSettings, queue.TRANSCRIBE_WHISPER, (YOUTUBE_ID, "pt"), "whisper:v"),
    ],
    ids=["import", "whisper"],
)
async def test_job_given_up_by_arq_does_not_block_the_id(
    redis: ArqRedis, settings: type, function: str, args: tuple[str, ...], job_id: str
) -> None:
    arq_worker = create_worker(
        settings,
        redis_pool=redis,
        burst=True,
        poll_delay=0,
        handle_signals=False,
        on_startup=None,
        on_shutdown=None,
        cron_jobs=[],
    )
    max_tries = next(iter(arq_worker.functions.values())).max_tries
    assert max_tries is not None
    await redis.enqueue_job(
        function, *args, _job_id=job_id, _queue_name=settings.queue_name, _job_try=max_tries + 1
    )

    await arq_worker.async_run()

    assert arq_worker.jobs_failed == 1
    assert not await redis.exists(result_key_prefix + job_id)
    assert await redis.enqueue_job(function, *args, _job_id=job_id, _queue_name=settings.queue_name)


async def test_whisper_job_is_idempotent(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    await make_video(session, YOUTUBE_ID, generated=None)

    assert await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt") == (
        "transcrito; 0 import(s) retomado(s)"
    )
    assert await worker.transcribe_whisper(ctx, "naoexiste00", "pt") == "ignorado"
    assert fake.calls == []


async def test_recover_stale_imports(
    ctx: dict[str, Any], session: AsyncSession, redis: ArqRedis
) -> None:
    user = await make_user(session)
    now = datetime.now(UTC)
    lost = Import(user_id=user.id, url="u", youtube_id=YOUTUBE_ID)
    queued = Import(user_id=user.id, url="u", youtube_id=YOUTUBE_ID)
    waiting_whisper = Import(
        user_id=user.id, url="u", youtube_id="whisperwait", status=ImportStatus.TRANSCRIBING
    )
    abandoned = Import(
        user_id=user.id, url="u", youtube_id=YOUTUBE_ID, status=ImportStatus.GENERATING
    )
    recent = Import(user_id=user.id, url="u", youtube_id=YOUTUBE_ID)
    session.add_all([lost, queued, waiting_whisper, abandoned, recent])
    await session.commit()
    ages = {lost: 10, queued: 10, waiting_whisper: 10, abandoned: 60 * 24, recent: 1}
    for imp, minutes in ages.items():
        await session.execute(
            update(Import)
            .where(Import.id == imp.id)
            .values(updated_at=now - timedelta(minutes=minutes))
        )
    await session.commit()
    await queue.enqueue_import(redis, queued.id)
    await queue.enqueue_whisper(redis, "whisperwait", None)

    result = await worker.recover_stale_imports(ctx)

    assert result == "1 reenfileirado(s), 1 encerrado(s)"
    assert {j.job_id for j in await redis.queued_jobs()} == {
        f"import:{queued.id}",
        f"import:{lost.id}",
    }
    abandoned = await _reload(session, abandoned)
    assert (abandoned.status, abandoned.error_code) == (ImportStatus.FAILED, "import_timeout")
    assert (await _reload(session, recent)).status is ImportStatus.PENDING


def test_classify_failure() -> None:
    assert worker.classify_failure(YoutubeBlockedError())[1] is True
    assert worker.classify_failure(NotEmbeddableError())[1] is False
    error, transient = worker.classify_failure(TimeoutError())
    assert (error.code, transient) == ("import_timeout", True)
    error, transient = worker.classify_failure(ValueError("x"))
    assert (error.code, transient) == ("internal_error", False)
    assert worker.classify_failure(ConnectionRefusedError())[1] is True


async def test_video_lock(redis: ArqRedis) -> None:
    first = VideoLock(redis, YOUTUBE_ID, ttl_s=60)
    second = VideoLock(redis, YOUTUBE_ID, ttl_s=60)

    assert await first.acquire()
    assert not await second.acquire()
    await second.release()  # não é dele: não solta
    assert not await second.acquire()

    await first.release()
    assert await second.acquire()
    assert 0 < await redis.pttl(second.key) <= 60_000


# --- Cota e orçamento -------------------------------------------------------------------------


async def _spend_today(session: AsyncSession, usd: int) -> LLMCall:
    """Registra uma chamada ao Claude de hoje que custou `usd` dólares (só saída, US$ 20/MTok)."""
    video = await make_video(session, "outrovideo1")
    call = LLMCall(
        video_id=video.id,
        model=recipe_llm.MODEL,
        prompt_version=PROMPT_VERSION,
        usage={"input_tokens": 0, "output_tokens": usd * 50_000},
        purpose=LLMPurpose.IMPORT,
    )
    session.add(call)
    await session.commit()
    return call


async def test_new_recipe_uses_quota(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "concluído"

    imp = await _reload(session, imp)
    assert imp.charged_at is not None
    assert datetime.now(UTC) - imp.charged_at < timedelta(minutes=1)
    assert imp.deferred_at is None
    call = await session.scalar(select(LLMCall))
    assert call is not None
    assert (call.purpose, call.error_code) == (LLMPurpose.IMPORT, None)


async def test_copy_does_not_use_quota(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    await make_video(session, YOUTUBE_ID)
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "reaproveitado"

    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.DONE and imp.charged_at is None


async def test_recipe_generated_while_waiting_does_not_use_quota(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Outro import gerou a receita depois que este já tinha passado da checagem de cópia: a
    # geração no pipeline encontra a receita pronta e não chama o Claude.
    await make_video(session, YOUTUBE_ID)
    imp = await _new_import(session)

    async def no_copy(*args: Any) -> bool:
        return False

    monkeypatch.setattr(imports, "complete_from_existing", no_copy)

    assert await _run(ctx, imp) == "concluído"

    assert "llm" not in fake.calls
    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.DONE and imp.charged_at is None


async def test_not_a_recipe_does_not_use_quota(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_recipe = {**GENERATED, "is_recipe": False, "steps": []}
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "falhou: not_a_recipe"

    imp = await _reload(session, imp)
    assert (imp.status, imp.charged_at) == (ImportStatus.FAILED, None)


async def test_costly_failures_are_limited_per_day(
    ctx: dict[str, Any],
    client: AsyncClient,
    session: AsyncSession,
    fake: FakeServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Vídeos com fala que não são receita: cada um custa uma chamada ao Claude e não gasta a
    # cota, então sem outro limite uma conta só esgotaria o orçamento do dia de todo mundo.
    monkeypatch.setattr(get_settings(), "daily_import_limit", 1)
    monkeypatch.setattr(get_settings(), "daily_failed_import_limit", 2)
    fake.llm_recipe = {**GENERATED, "is_recipe": False, "steps": []}
    user = await make_user(session)

    async def post(n: int) -> httpx.Response:
        return await client.post(
            "/imports", headers=headers(user), json={"url": f"https://youtu.be/{youtube_id(n)}"}
        )

    for n in range(2):
        response = await post(n)
        assert response.status_code == 202
        result = await worker.process_import(ctx, response.json()["id"])
        assert result == "falhou: not_a_recipe"

    blocked = await post(2)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_failed_imports"
    assert int(blocked.headers["Retry-After"]) <= 86400
    assert fake.calls.count("llm") == 2
    quota = (await client.get("/auth/me", headers=headers(user))).json()["quota"]
    assert quota["used"] == 0
    # Vídeos que já estão no site continuam liberados.
    await make_video(session, youtube_id(3))
    assert (await post(3)).status_code == 200


async def test_failures_count_only_after_paid_claude_call(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    user = await make_user(session)
    fake.llm_error = LLMRefusedError(llm_model=recipe_llm.MODEL, llm_usage={"output_tokens": 10})
    refused = await _new_import(session, user)
    assert await _run(ctx, refused) == "falhou: llm_refused"

    # Sem chamada paga: chave ausente, vídeo que já se sabe não ser receita, metadados recusados.
    fake.llm_error = LLMMissingKeyError()
    await make_video(session, youtube_id(1), generated=None)
    no_key = await _new_import(session, user, youtube_id(1))
    assert await _run(ctx, no_key) == "falhou: llm_missing_key"
    not_a_recipe = {**GENERATED, "is_recipe": False, "steps": []}
    await make_video(session, youtube_id(2), generated=not_a_recipe)
    known_non_recipe = await _new_import(session, user, youtube_id(2))
    assert await _run(ctx, known_non_recipe) == "falhou: not_a_recipe"
    fake.metadata_error = NotEmbeddableError()
    not_embeddable = await _new_import(session, user, youtube_id(3))
    assert await _run(ctx, not_embeddable) == "falhou: not_embeddable"

    assert fake.calls.count("llm") == 2
    refused = await _reload(session, refused)
    assert refused.status is ImportStatus.FAILED and refused.cost_incurred_at is not None
    for imp in (no_key, not_embeddable, known_non_recipe):
        imp = await _reload(session, imp)
        assert imp.status is ImportStatus.FAILED, imp.youtube_id
        assert imp.cost_incurred_at is None, imp.error_code


async def test_whisper_failure_counts_only_for_the_import_that_queued_it(
    ctx: dict[str, Any], session: AsyncSession, fake: FakeServices
) -> None:
    fake.subtitles = None
    fake.whisper_error = TranscriptionGaveUpError()
    first = await _new_import(session)
    assert await _run(ctx, first) == "na fila do whisper"
    second = await _new_import(session)
    assert await _run(ctx, second) == "aguardando whisper"

    await worker.transcribe_whisper(ctx, YOUTUBE_ID, "pt")

    first, second = await _reload(session, first), await _reload(session, second)
    assert first.status is second.status is ImportStatus.FAILED
    assert first.cost_incurred_at is not None
    assert second.cost_incurred_at is None


async def test_import_is_deferred_when_budget_is_over(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    redis: ArqRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "daily_llm_budget_usd", 5.0)
    await _spend_today(session, 5)
    imp = await _new_import(session)

    assert await _run(ctx, imp) == "adiado"

    assert "llm" not in fake.calls
    imp = await _reload(session, imp)
    assert (imp.status, imp.charged_at) == (ImportStatus.DEFERRED, None)
    # O usuário fica sabendo por que o import está esperando.
    error = ImportOut.from_import(imp).error
    assert error is not None
    assert (error.code, error.message) == (
        "llm_budget_exceeded",
        LLMBudgetExceededError.default_message,
    )
    # O que não custa nada já ficou pronto para o dia seguinte.
    video = await session.scalar(select(Video).where(Video.youtube_id == YOUTUBE_ID))
    assert video is not None and video.transcript == SPEECH
    assert await redis.keys("receita:lock:*") == []


async def test_deferred_imports_resume_when_budget_frees_up(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    redis: ArqRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "daily_llm_budget_usd", 5.0)
    call = await _spend_today(session, 5)
    imp = await _new_import(session)
    await _run(ctx, imp)

    assert await worker.resume_deferred_imports(ctx) == "orçamento esgotado; nada retomado"
    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.DEFERRED
    deferred_at = imp.deferred_at
    assert deferred_at is not None
    assert await redis.queued_jobs() == []

    # Virou o dia: o gasto de ontem não conta mais.
    await session.execute(
        update(LLMCall)
        .where(LLMCall.id == call.id)
        .values(created_at=datetime.now(UTC) - timedelta(days=1))
    )
    await session.commit()

    assert await worker.resume_deferred_imports(ctx) == "1 retomado(s)"
    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code, imp.error_message) == (ImportStatus.PENDING, None, None)
    assert [job.job_id for job in await redis.queued_jobs()] == [f"import:{imp.id}"]

    assert await _run(ctx, imp) == "concluído"
    imp = await _reload(session, imp)
    assert imp.status is ImportStatus.DONE and imp.charged_at is not None
    assert imp.deferred_at == deferred_at
    assert fake.calls.count("llm") == 1
    new_calls = (await session.scalars(select(LLMCall).where(LLMCall.id != call.id))).all()
    assert [(c.purpose, c.error_code) for c in new_calls] == [(LLMPurpose.DEFERRED, None)]


async def test_deferred_imports_wait_for_slack_for_a_whole_call(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    redis: ArqRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 5.0)
    await _spend_today(session, 5)
    imp = await _new_import(session)
    await _run(ctx, imp)
    minimum = float(llm_calls.minimum_reservation_usd(recipe_llm.default_config()))

    # Sobra folga, mas menos que a menor reserva: retomado, o import consultaria o YouTube de
    # novo e voltaria a ser adiado.
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 5 + minimum - 0.001)
    assert await worker.resume_deferred_imports(ctx) == "orçamento esgotado; nada retomado"
    assert (await _reload(session, imp)).status is ImportStatus.DEFERRED
    assert await redis.queued_jobs() == []

    monkeypatch.setattr(settings, "daily_llm_budget_usd", 5 + minimum + 0.001)
    assert await worker.resume_deferred_imports(ctx) == "1 retomado(s)"
    assert (await _reload(session, imp)).status is ImportStatus.PENDING


def test_deferral_keeps_the_first_date() -> None:
    imp = Import(user_id=uuid.uuid4(), url="u", youtube_id=YOUTUBE_ID)
    imports.mark_deferred(imp, LLMBudgetExceededError())
    first = imp.deferred_at
    imports.mark_resumed(imp)
    imports.mark_deferred(imp, LLMBudgetExceededError())

    assert first is not None and imp.deferred_at == first


async def test_stale_recovery_leaves_deferred_imports_alone(
    ctx: dict[str, Any], session: AsyncSession, redis: ArqRedis
) -> None:
    user = await make_user(session)
    deferred = Import(user_id=user.id, url="u", youtube_id=YOUTUBE_ID, status=ImportStatus.DEFERRED)
    session.add(deferred)
    await session.commit()
    await session.execute(
        update(Import)
        .where(Import.id == deferred.id)
        .values(updated_at=datetime.now(UTC) - timedelta(days=1))
    )
    await session.commit()

    assert await worker.recover_stale_imports(ctx) == "0 reenfileirado(s), 0 encerrado(s)"
    assert (await _reload(session, deferred)).status is ImportStatus.DEFERRED


@pytest.fixture
def tokyo_time(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fuso do sistema a leste de UTC, onde 00:05 local ainda é o dia anterior em UTC."""
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.usefixtures("tokyo_time")
async def test_crons_follow_the_utc_day_whatever_the_system_timezone() -> None:
    arq_worker = create_worker(worker.WorkerSettings)
    [resume] = [
        job for job in arq_worker.cron_jobs if job.coroutine is worker.resume_deferred_imports
    ]

    # Como o arq agenda: a próxima execução a partir de agora, no fuso do worker.
    resume.calculate_next(datetime.now(arq_worker.timezone))

    assert resume.next_run is not None
    next_run = resume.next_run.astimezone(UTC)
    assert (next_run.hour, next_run.minute) == (0, 5)
    assert next_run - datetime.now(UTC) <= timedelta(days=1)
