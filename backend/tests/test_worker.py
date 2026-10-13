import asyncio
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from arq import Retry
from arq.connections import ArqRedis
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import queue, worker
from app.config import get_settings
from app.errors import (
    InternalError,
    LLMMissingKeyError,
    LLMUnavailableError,
    NotEmbeddableError,
    TranscriptionFailedError,
    YoutubeBlockedError,
)
from app.models import Import, ImportStatus, Recipe, User, Video
from app.schemas.recipe_llm import RecipeLLM
from app.schemas.transcript import Segment, TranscriptSource
from app.services import recipe_llm, transcription, youtube
from app.services.locks import VideoLock
from app.services.recipe_llm import PROMPT_VERSION, RecipeGeneration, VideoContext
from app.services.transcription import Transcript
from app.services.youtube import SubtitleTrack, VideoMetadata
from tests.factories import GENERATED, SPEECH, make_user, make_video

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
        return self.meta

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
            recipe=RecipeLLM.model_validate(GENERATED),
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


async def _new_import(session: AsyncSession, user: User | None = None) -> Import:
    user = user or await make_user(session)
    imp = Import(user_id=user.id, url=f"https://youtu.be/{YOUTUBE_ID}", youtube_id=YOUTUBE_ID)
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


async def test_job_timeout_is_retried(
    ctx: dict[str, Any],
    session: AsyncSession,
    fake: FakeServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "import_job_timeout_s", 0.05)
    fake.llm_delay_s = 1
    imp = await _new_import(session)

    with pytest.raises(Retry):
        await _run(ctx, imp)


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

    imp = await _reload(session, imp)
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "import_timeout")


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
