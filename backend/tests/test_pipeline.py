import asyncio
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.errors import (
    InvalidUrlError,
    LLMBudgetExceededError,
    LLMInvalidOutputError,
    LLMOutputTooLongError,
    LLMRefusedError,
    LLMUnavailableError,
    NotARecipeError,
    NotEmbeddableError,
    NoTranscriptError,
    VideoUnavailableError,
    YoutubeBlockedError,
)
from app.models import ImportStatus, LLMCall, LLMPurpose, Video
from app.schemas.recipe_llm import RecipeLLM
from app.schemas.transcript import Segment, TranscriptSource
from app.services import pipeline, quotas, recipe_llm, transcription, youtube
from app.services.recipe_llm import PROMPT_VERSION, LLMConfig, RecipeGeneration, VideoContext
from app.services.transcription import Transcript
from app.services.youtube import VideoMetadata
from tests.test_recipe_llm import USAGE, FakeAPI, _message, _ok

YOUTUBE_ID = "abcdefghijk"
URL = f"https://youtu.be/{YOUTUBE_ID}?si=abc"
SPEECH = [Segment(start=float(i), end=i + 1.0, text="bata os ovos com o açúcar") for i in range(6)]

META = VideoMetadata(
    youtube_id=YOUTUBE_ID,
    title="Bolo de cenoura",
    channel="Receitas",
    duration_s=600,
    thumbnail_url="https://i.ytimg.com/vi/abcdefghijk/hq.jpg",
    description="Receita de bolo de cenoura com cobertura de chocolate.",
    embeddable=True,
    availability="public",
    live_status="not_live",
    age_limit=0,
    language="pt",
    subtitles=[],
)

RECIPE = RecipeLLM(
    is_recipe=True,
    title="Bolo de cenoura",
    summary="Bolo fofinho.",
    servings=None,
    prep_time_min=None,
    cook_time_min=40,
    difficulty="fácil",
    ingredients=[],
    steps=[{"order": 1, "text": "Bata tudo e asse.", "video_timestamp_s": 3}],
    tips=[],
    tags=["bolo"],
)
LLM_USAGE = {"input_tokens": 100, "output_tokens": 50}

# A função de verdade, guardada antes de a fixture `fake` trocá-la.
REAL_GENERATE_RECIPE = recipe_llm.generate_recipe


@dataclass
class FakeServices:
    meta: VideoMetadata = META
    transcript: Transcript = field(
        default_factory=lambda: Transcript(SPEECH, TranscriptSource.MANUAL)
    )
    recipe: RecipeLLM = field(default_factory=lambda: RECIPE)
    metadata_error: Exception | None = None
    llm_error: Exception | None = None
    session: AsyncSession | None = None
    calls: list[str] = field(default_factory=list)
    contexts: list[VideoContext] = field(default_factory=list)
    configs: list[LLMConfig | None] = field(default_factory=list)
    open_transactions: list[str] = field(default_factory=list)

    def _network(self, call: str) -> None:
        """Grava a chamada e se havia transação aberta no banco durante ela."""
        self.calls.append(call)
        if self.session is not None and self.session.in_transaction():
            self.open_transactions.append(call)

    async def fetch_metadata(self, youtube_id: str) -> VideoMetadata:
        self._network(f"metadata:{youtube_id}")
        if self.metadata_error:
            raise self.metadata_error
        return self.meta

    async def transcribe(self, meta: VideoMetadata) -> Transcript:
        self._network("transcribe")
        return self.transcript

    async def generate_recipe(
        self, video: VideoContext, *, config: LLMConfig | None = None, **_: Any
    ) -> RecipeGeneration:
        self._network("llm")
        self.contexts.append(video)
        self.configs.append(config)
        if self.llm_error:
            raise self.llm_error
        return RecipeGeneration(
            recipe=self.recipe,
            model="claude-opus-5-5",
            usage=LLM_USAGE,
            prompt_version=PROMPT_VERSION,
        )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> FakeServices:
    services = FakeServices(session=session)
    monkeypatch.setattr(youtube, "fetch_metadata", services.fetch_metadata)
    monkeypatch.setattr(transcription, "transcribe", services.transcribe)
    monkeypatch.setattr(recipe_llm, "generate_recipe", services.generate_recipe)
    return services


async def test_process_video_full_run(session: AsyncSession, fake: FakeServices) -> None:
    stages: list[ImportStatus] = []

    async def on_stage(status: ImportStatus) -> None:
        stages.append(status)

    video = await pipeline.process_video(URL, session, on_stage=on_stage)

    assert fake.calls == [f"metadata:{YOUTUBE_ID}", "transcribe", "llm"]
    assert stages == [ImportStatus.FETCHING, ImportStatus.TRANSCRIBING, ImportStatus.GENERATING]
    assert fake.contexts[0].segments == SPEECH
    assert fake.contexts[0].transcript_source == TranscriptSource.MANUAL
    assert fake.configs == [recipe_llm.default_config()]

    session.expunge_all()
    saved = await session.scalar(select(Video).where(Video.youtube_id == YOUTUBE_ID))
    assert saved is not None and saved.id == video.id
    assert saved.title == "Bolo de cenoura"
    assert saved.thumbnail_url == META.thumbnail_url
    assert saved.transcript == SPEECH
    assert saved.transcript_source is TranscriptSource.MANUAL
    assert saved.generated_recipe == RECIPE.model_dump(mode="json")
    assert saved.llm_model == "claude-opus-5-5"
    assert saved.llm_usage == LLM_USAGE
    assert saved.prompt_version == PROMPT_VERSION

    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.video_id, c.model, c.usage, c.error_code) for c in calls] == [
        (video.id, "claude-opus-5-5", LLM_USAGE, None)
    ]
    [call] = calls
    assert call.purpose is LLMPurpose.CLI
    assert call.cost_usd == quotas.llm_cost_usd("claude-opus-5-5", LLM_USAGE)
    assert call.latency_ms is not None and call.latency_ms >= 0
    assert (call.effort, call.max_tokens, call.cache_marker) == (
        "medium",
        recipe_llm.MAX_TOKENS,
        "5m",
    )
    assert fake.open_transactions == []


async def test_process_video_reuse_keeps_no_transaction_open_during_network(
    session: AsyncSession, fake: FakeServices
) -> None:
    await pipeline.process_video(URL, session, skip_llm=True)
    session.expunge_all()

    await pipeline.process_video(URL, session)

    assert fake.calls[-2:] == [f"metadata:{YOUTUBE_ID}", "llm"]
    assert fake.open_transactions == []


async def test_process_video_reuses_existing_video(
    session: AsyncSession, fake: FakeServices
) -> None:
    first = await pipeline.process_video(URL, session)
    fake.calls.clear()

    fake.meta = replace(META, title="Bolo de cenoura (novo título)")

    again = await pipeline.process_video(f"https://www.youtube.com/watch?v={YOUTUBE_ID}", session)

    # Metadados são conferidos de novo (barato); transcrição e Claude, não.
    assert fake.calls == [f"metadata:{YOUTUBE_ID}"]
    assert again.id == first.id
    assert again.title == "Bolo de cenoura (novo título)"
    assert await session.scalar(select(func.count()).select_from(Video)) == 1


@pytest.mark.parametrize(
    ("meta", "error"),
    [
        (replace(META, embeddable=False), NotEmbeddableError),
        (replace(META, availability="private"), VideoUnavailableError),
    ],
)
async def test_process_video_reuse_revalidates_metadata(
    session: AsyncSession, fake: FakeServices, meta: VideoMetadata, error: type[Exception]
) -> None:
    await pipeline.process_video(URL, session)
    fake.meta = meta
    fake.calls.clear()

    with pytest.raises(error):
        await pipeline.process_video(URL, session)
    assert fake.calls == [f"metadata:{YOUTUBE_ID}"]


async def test_process_video_reuse_survives_youtube_block(
    session: AsyncSession, fake: FakeServices
) -> None:
    first = await pipeline.process_video(URL, session)
    fake.metadata_error = YoutubeBlockedError()

    again = await pipeline.process_video(URL, session)

    assert again.id == first.id
    assert again.generated_recipe is not None


async def test_process_video_new_video_fails_when_youtube_blocks(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.metadata_error = YoutubeBlockedError()

    with pytest.raises(YoutubeBlockedError):
        await pipeline.process_video(URL, session)


async def test_process_video_regenerates_when_prompt_changes(
    session: AsyncSession, fake: FakeServices
) -> None:
    video = await pipeline.process_video(URL, session)
    video.prompt_version = "versao-antiga"
    await session.commit()
    fake.calls.clear()

    await pipeline.process_video(URL, session)

    assert fake.calls == [f"metadata:{YOUTUBE_ID}", "llm"]  # transcrição reaproveitada
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 2


async def test_process_video_skip_llm_then_generate(
    session: AsyncSession, fake: FakeServices
) -> None:
    video = await pipeline.process_video(URL, session, skip_llm=True)
    assert fake.calls == [f"metadata:{YOUTUBE_ID}", "transcribe"]
    assert video.transcript == SPEECH
    assert video.generated_recipe is None

    fake.calls.clear()
    video = await pipeline.process_video(URL, session)
    assert fake.calls == [f"metadata:{YOUTUBE_ID}", "llm"]
    assert video.generated_recipe is not None


async def test_process_video_retries_transcription_after_failure(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(meta: VideoMetadata) -> Transcript:
        raise YoutubeBlockedError()

    monkeypatch.setattr(transcription, "transcribe", broken)
    with pytest.raises(YoutubeBlockedError):
        await pipeline.process_video(URL, session)

    saved = await session.scalar(select(Video))
    assert saved is not None and saved.transcript is None

    monkeypatch.setattr(transcription, "transcribe", fake.transcribe)
    video = await pipeline.process_video(URL, session)
    assert video.id == saved.id
    assert video.transcript == SPEECH


async def test_process_video_invalid_url_does_nothing(
    session: AsyncSession, fake: FakeServices
) -> None:
    with pytest.raises(InvalidUrlError):
        await pipeline.process_video("https://www.youtube.com/@canal", session)
    assert fake.calls == []


async def test_process_video_rejects_non_embeddable_without_saving(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.meta = replace(META, embeddable=False)

    with pytest.raises(NotEmbeddableError):
        await pipeline.process_video(URL, session)

    assert fake.calls == [f"metadata:{YOUTUBE_ID}"]
    assert await session.scalar(select(Video)) is None


async def test_process_video_uses_description_when_no_speech(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.transcript = Transcript([], TranscriptSource.WHISPER)
    fake.meta = replace(
        META,
        description="Ingredientes: 3 cenouras, 4 ovos, 2 xícaras de açúcar, 1 xícara de óleo, "
        "2 xícaras de farinha e 1 colher de fermento. Asse por 40 minutos a 180 graus.",
    )

    video = await pipeline.process_video(URL, session)

    assert fake.contexts[0].segments == []
    assert fake.contexts[0].transcript_source is None
    assert video.transcript == []
    assert video.transcript_source is TranscriptSource.WHISPER


async def test_process_video_without_speech_or_description(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.transcript = Transcript([], TranscriptSource.WHISPER)
    fake.meta = replace(META, description="Inscreva-se!")

    with pytest.raises(NoTranscriptError) as exc_info:
        await pipeline.process_video(URL, session)

    assert exc_info.value.code == "no_transcript"
    assert "llm" not in fake.calls


async def test_process_video_not_a_recipe_is_cached(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.recipe = RECIPE.model_copy(update={"is_recipe": False, "summary": "É um vlog."})

    with pytest.raises(NotARecipeError) as exc_info:
        await pipeline.process_video(URL, session)
    assert exc_info.value.code == "not_a_recipe"

    fake.calls.clear()
    with pytest.raises(NotARecipeError):
        await pipeline.process_video(URL, session)
    assert fake.calls == [f"metadata:{YOUTUBE_ID}"]


async def test_process_video_not_a_recipe_without_speech_reports_no_transcript(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.transcript = Transcript([], TranscriptSource.WHISPER)
    fake.meta = replace(META, description=" ".join(["palavra"] * 30))
    fake.recipe = RECIPE.model_copy(update={"is_recipe": False})

    with pytest.raises(NoTranscriptError):
        await pipeline.process_video(URL, session)


async def test_process_video_ingredients_without_method_or_speech_is_cached(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Vídeo só com música (o whisper ouviu "You") e descrição só com ingredientes: o Claude
    # devolve is_recipe=true sem passos. A mesma entrada daria a mesma resposta, então o vídeo
    # fica com uma não receita do prompt atual e o erro não convida a tentar de novo.
    fake.transcript = Transcript(
        [Segment(start=0.0, end=2.0, text="You")], TranscriptSource.WHISPER
    )
    fake.meta = replace(
        META,
        description="Ingredientes: 1 kg de carne, 1 kg de arroz, 2 colheres de pilau masala, "
        "3 cebolas, 4 dentes de alho, 2 tomates, sal e óleo.",
    )
    only_ingredients = RecipeLLM.model_validate(
        RECIPE.model_dump()
        | {
            "steps": [],
            "ingredients": [
                {"name": "carne", "quantity": "1", "unit": "kg", "note": None, "group": None}
            ],
        }
    )
    api = FakeAPI(
        _ok(_message(content=[{"type": "text", "text": only_ingredients.model_dump_json()}]))
    )
    monkeypatch.setattr(recipe_llm, "generate_recipe", REAL_GENERATE_RECIPE)
    monkeypatch.setattr(recipe_llm, "get_client", api.client)

    with pytest.raises(NoTranscriptError) as exc_info:
        await pipeline.process_video(URL, session)
    assert exc_info.value.code == "no_transcript"
    assert exc_info.value.llm_usage is None  # a chamada paga foi registrada como sucesso

    with pytest.raises(NoTranscriptError):
        await pipeline.process_video(URL, session)

    assert len(api.requests) == 1
    video = await session.scalar(select(Video))
    assert video is not None
    assert video.prompt_version == PROMPT_VERSION
    assert video.generated_recipe is not None
    assert video.generated_recipe["is_recipe"] is False
    assert video.generated_recipe["summary"] == recipe_llm.NO_METHOD_SUMMARY
    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.usage) for c in calls] == [(None, USAGE)]


async def test_process_video_llm_error_keeps_transcript(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = LLMRefusedError()

    with pytest.raises(LLMRefusedError):
        await pipeline.process_video(URL, session)

    saved = await session.scalar(select(Video))
    assert saved is not None
    assert saved.transcript == SPEECH
    assert saved.generated_recipe is None


async def test_process_video_short_video_with_short_speech_goes_to_llm(
    session: AsyncSession, fake: FakeServices
) -> None:
    speech = [
        Segment(
            start=0.0,
            end=30.0,
            text="misture farinha ovos e leite asse por vinte minutos "
            "a cento e oitenta graus e sirva",
        )
    ]
    fake.transcript = Transcript(speech, TranscriptSource.MANUAL)
    fake.meta = replace(META, duration_s=40, description="Bolo rápido!")

    await pipeline.process_video(URL, session)

    assert fake.contexts[0].segments == speech


def _failed_call(error: type[Exception], **kwargs: Any) -> Exception:
    return error(llm_model="claude-opus-5-5", llm_usage=LLM_USAGE, **kwargs)


async def test_process_video_refusal_is_recorded_and_not_retried(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = _failed_call(LLMRefusedError, detail="recusa")

    with pytest.raises(LLMRefusedError):
        await pipeline.process_video(URL, session)
    fake.calls.clear()
    with pytest.raises(LLMRefusedError) as exc_info:
        await pipeline.process_video(URL, session)

    assert "llm" not in fake.calls
    assert exc_info.value.llm_usage is None  # a segunda vez não houve chamada paga
    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.usage) for c in calls] == [("llm_refused", LLM_USAGE)]


async def test_process_video_invalid_output_gives_up_after_limit(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = _failed_call(LLMInvalidOutputError, detail="max_tokens")

    for _ in range(3):
        with pytest.raises(LLMInvalidOutputError):
            await pipeline.process_video(URL, session)

    assert fake.calls.count("llm") == 2
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 2


async def test_process_video_failures_reset_with_new_prompt_version(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.llm_error = _failed_call(LLMRefusedError)
    with pytest.raises(LLMRefusedError):
        await pipeline.process_video(URL, session)

    monkeypatch.setattr(recipe_llm, "PROMPT_VERSION", "versao-nova")
    fake.llm_error = None
    video = await pipeline.process_video(URL, session)

    assert fake.calls.count("llm") == 2
    assert video.generated_recipe is not None


async def test_process_video_unpaid_llm_errors_are_not_recorded(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = LLMUnavailableError()

    for _ in range(3):
        with pytest.raises(LLMUnavailableError):
            await pipeline.process_video(URL, session)

    assert fake.calls.count("llm") == 3
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 0


async def test_process_video_handles_concurrent_insert(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(Video(youtube_id=YOUTUBE_ID, title="Outro processo", duration_s=1, embeddable=True))
    await session.commit()
    session.expunge_all()

    real_get_video = pipeline._get_video
    lookups: list[str] = []

    async def stale_first_lookup(db: AsyncSession, youtube_id: str) -> Video | None:
        lookups.append(youtube_id)
        # A primeira busca acontece antes de o outro processo gravar o vídeo.
        return None if len(lookups) == 1 else await real_get_video(db, youtube_id)

    monkeypatch.setattr(pipeline, "_get_video", stale_first_lookup)

    video = await pipeline.process_video(URL, session)

    assert len(lookups) == 2
    assert video.title == META.title
    assert video.transcript == SPEECH
    assert await session.scalar(select(func.count()).select_from(Video)) == 1


async def test_reservation_exists_during_the_call(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    fake: FakeServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str | None, Decimal | None, dict[str, Any]]] = []

    async def generate_recipe(video: VideoContext, **kwargs: Any) -> RecipeGeneration:
        # Outra sessão: a reserva já foi comitada e conta no orçamento de quem vier depois.
        async with session_factory() as other:
            call = await other.scalar(select(LLMCall))
            assert call is not None
            seen.append((call.error_code, call.cost_usd, call.usage))
        return await fake.generate_recipe(video, **kwargs)

    monkeypatch.setattr(recipe_llm, "generate_recipe", generate_recipe)

    await pipeline.process_video(URL, session)

    [(error_code, cost_usd, usage)] = seen
    assert error_code == "llm_in_progress"
    assert cost_usd is not None and cost_usd > 0
    assert usage == {}


async def test_sdk_timeout_keeps_estimated_cost(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = FakeAPI(error=httpx2.ReadTimeout("lento"))
    monkeypatch.setattr(recipe_llm, "generate_recipe", REAL_GENERATE_RECIPE)
    monkeypatch.setattr(recipe_llm, "get_client", api.client)

    for _ in range(3):
        with pytest.raises(LLMUnavailableError) as exc_info:
            await pipeline.process_video(URL, session)
        assert exc_info.value.llm_maybe_billed

    # Timeout não é falha determinística: o vídeo continua indo para o Claude.
    assert len(api.requests) == 3
    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.usage) for c in calls] == [("llm_timeout", {})] * 3
    assert all(c.cost_usd is not None and c.cost_usd > 0 for c in calls)
    assert all(c.latency_ms is not None for c in calls)


async def test_unpaid_connection_failure_is_discarded(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = FakeAPI(error=httpx2.ConnectError("recusada"))
    monkeypatch.setattr(recipe_llm, "generate_recipe", REAL_GENERATE_RECIPE)
    monkeypatch.setattr(recipe_llm, "get_client", api.client)

    with pytest.raises(LLMUnavailableError) as exc_info:
        await pipeline.process_video(URL, session)

    assert not exc_info.value.llm_maybe_billed
    assert len(api.requests) == 1
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 0


async def test_eval_failures_do_not_block_production(
    session: AsyncSession, fake: FakeServices
) -> None:
    video = await pipeline.process_video(URL, session, skip_llm=True)
    session.add(
        LLMCall(
            video_id=video.id,
            model="claude-haiku-5-5",
            prompt_version=PROMPT_VERSION,
            usage=LLM_USAGE,
            error_code="llm_refused",
            purpose=LLMPurpose.EVAL,
        )
    )
    await session.commit()

    video = await pipeline.process_video(URL, session)

    assert fake.calls.count("llm") == 1
    assert video.generated_recipe is not None


async def test_cancelled_call_is_marked_timeout(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cancelled(video: VideoContext, **_: Any) -> RecipeGeneration:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await asyncio.Event().wait()
        raise AssertionError("não deveria terminar")

    monkeypatch.setattr(recipe_llm, "generate_recipe", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await pipeline.process_video(URL, session)
    task = asyncio.current_task()
    assert task is not None
    task.uncancel()

    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.usage) for c in calls] == [("llm_timeout", {})]
    assert calls[0].cost_usd is not None and calls[0].cost_usd > 0
    assert calls[0].latency_ms is not None


async def test_unexpected_error_after_reservation_is_marked_timeout(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = RuntimeError("bug depois da resposta")

    with pytest.raises(RuntimeError):
        await pipeline.process_video(URL, session)

    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.usage) for c in calls] == [("llm_timeout", {})]
    assert calls[0].cost_usd is not None and calls[0].cost_usd > 0


async def test_no_call_is_recorded_when_the_estimate_does_not_fit(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sem gasto nenhum hoje, mas a estimativa (12k de saída reservados) passa do teto.
    monkeypatch.setattr(get_settings(), "daily_llm_budget_usd", 0.01)

    with pytest.raises(LLMBudgetExceededError):
        await pipeline.process_video(URL, session)

    assert "llm" not in fake.calls
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 0


async def test_output_too_long_is_not_retried_with_the_same_ceiling(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.llm_error = _failed_call(
        LLMOutputTooLongError, llm_stop_reason="max_tokens", llm_request_id="req_corte"
    )

    with pytest.raises(LLMOutputTooLongError):
        await pipeline.process_video(URL, session)
    fake.calls.clear()
    with pytest.raises(LLMOutputTooLongError) as exc_info:
        await pipeline.process_video(URL, session)

    assert "llm" not in fake.calls
    assert exc_info.value.llm_usage is None  # a segunda vez não houve chamada paga
    calls = (await session.scalars(select(LLMCall))).all()
    assert [(c.error_code, c.max_tokens, c.stop_reason, c.request_id) for c in calls] == [
        ("llm_output_too_long", recipe_llm.MAX_TOKENS, "max_tokens", "req_corte")
    ]


async def test_higher_ceiling_allows_retry_after_cut(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.llm_error = _failed_call(LLMOutputTooLongError)
    with pytest.raises(LLMOutputTooLongError):
        await pipeline.process_video(URL, session)

    higher = LLMConfig(max_tokens=recipe_llm.MAX_TOKENS + 1000)
    monkeypatch.setattr(recipe_llm, "default_config", lambda: higher)
    fake.llm_error = None
    video = await pipeline.process_video(URL, session)

    assert fake.calls.count("llm") == 2
    assert fake.configs[-1] == higher
    assert video.generated_recipe is not None
    calls = (await session.scalars(select(LLMCall).order_by(LLMCall.started_at))).all()
    assert [(c.error_code, c.max_tokens) for c in calls] == [
        ("llm_output_too_long", recipe_llm.MAX_TOKENS),
        (None, recipe_llm.MAX_TOKENS + 1000),
    ]


async def test_lower_ceiling_after_cut_still_gives_up(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.llm_error = _failed_call(LLMOutputTooLongError)
    with pytest.raises(LLMOutputTooLongError):
        await pipeline.process_video(URL, session)

    monkeypatch.setattr(recipe_llm, "default_config", lambda: LLMConfig(max_tokens=8000))
    with pytest.raises(LLMOutputTooLongError):
        await pipeline.process_video(URL, session)

    assert fake.calls.count("llm") == 1


async def test_call_metadata_is_recorded(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def generate_recipe(video: VideoContext, **kwargs: Any) -> RecipeGeneration:
        generation = await fake.generate_recipe(video, **kwargs)
        return replace(generation, request_id="req_x", stop_reason="end_turn")

    monkeypatch.setattr(recipe_llm, "generate_recipe", generate_recipe)

    await pipeline.process_video(URL, session)

    call = await session.scalar(select(LLMCall))
    assert call is not None
    assert (call.request_id, call.stop_reason) == ("req_x", "end_turn")


async def test_cache_ttl_comes_from_settings(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "llm_cache_ttl", "1h")

    await pipeline.process_video(URL, session)

    assert fake.configs == [LLMConfig(cache_ttl="1h")]
    call = await session.scalar(select(LLMCall))
    assert call is not None and call.cache_marker == "1h"


async def test_cost_of_fallback_write_uses_request_cache_marker(
    session: AsyncSession, fake: FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "llm_cache_ttl", "1h")
    # A tentativa recusada escreveu o prefixo; a que respondeu só leu o cache.
    usage = {
        "cache_creation_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
        "iterations": [
            {"model": "claude-opus-5-5", "cache_creation_input_tokens": 1_000_000},
            {"model": "claude-opus-5", "cache_read_input_tokens": 1_000_000},
        ],
    }

    async def generate_recipe(video: VideoContext, **kwargs: Any) -> RecipeGeneration:
        generation = await fake.generate_recipe(video, **kwargs)
        return replace(generation, model="claude-opus-5", usage=usage)

    monkeypatch.setattr(recipe_llm, "generate_recipe", generate_recipe)

    await pipeline.process_video(URL, session)

    call = await session.scalar(select(LLMCall))
    assert call is not None and call.cost_usd == Decimal("8.5")
