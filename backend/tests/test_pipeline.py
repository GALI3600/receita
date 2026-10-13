from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import (
    InvalidUrlError,
    LLMRefusedError,
    NotARecipeError,
    NotEmbeddableError,
    NoTranscriptError,
    YoutubeBlockedError,
)
from app.models import ImportStatus, Video
from app.schemas.recipe_llm import RecipeLLM
from app.schemas.transcript import Segment, TranscriptSource
from app.services import pipeline, recipe_llm, transcription, youtube
from app.services.recipe_llm import PROMPT_VERSION, RecipeGeneration, VideoContext
from app.services.transcription import Transcript
from app.services.youtube import VideoMetadata

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
    steps=[],
    tips=[],
    tags=["bolo"],
)


@dataclass
class FakeServices:
    meta: VideoMetadata = META
    transcript: Transcript = field(
        default_factory=lambda: Transcript(SPEECH, TranscriptSource.MANUAL)
    )
    recipe: RecipeLLM = field(default_factory=lambda: RECIPE)
    llm_error: Exception | None = None
    calls: list[str] = field(default_factory=list)
    contexts: list[VideoContext] = field(default_factory=list)

    async def fetch_metadata(self, youtube_id: str) -> VideoMetadata:
        self.calls.append(f"metadata:{youtube_id}")
        return self.meta

    async def transcribe(self, meta: VideoMetadata) -> Transcript:
        self.calls.append("transcribe")
        return self.transcript

    async def generate_recipe(self, video: VideoContext, **_: Any) -> RecipeGeneration:
        self.calls.append("llm")
        self.contexts.append(video)
        if self.llm_error:
            raise self.llm_error
        return RecipeGeneration(
            recipe=self.recipe,
            model="claude-opus-5-5",
            usage={"input_tokens": 100, "output_tokens": 50},
            prompt_version=PROMPT_VERSION,
        )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeServices:
    services = FakeServices()
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

    session.expunge_all()
    saved = await session.scalar(select(Video).where(Video.youtube_id == YOUTUBE_ID))
    assert saved is not None and saved.id == video.id
    assert saved.title == "Bolo de cenoura"
    assert saved.thumbnail_url == META.thumbnail_url
    assert saved.transcript == SPEECH
    assert saved.transcript_source is TranscriptSource.MANUAL
    assert saved.generated_recipe == RECIPE.model_dump(mode="json")
    assert saved.llm_model == "claude-opus-5-5"
    assert saved.llm_usage == {"input_tokens": 100, "output_tokens": 50}
    assert saved.prompt_version == PROMPT_VERSION


async def test_process_video_reuses_existing_video(
    session: AsyncSession, fake: FakeServices
) -> None:
    first = await pipeline.process_video(URL, session)
    fake.calls.clear()

    again = await pipeline.process_video(f"https://www.youtube.com/watch?v={YOUTUBE_ID}", session)

    assert fake.calls == []
    assert again.id == first.id
    assert await session.scalar(select(func.count()).select_from(Video)) == 1


async def test_process_video_regenerates_when_prompt_changes(
    session: AsyncSession, fake: FakeServices
) -> None:
    video = await pipeline.process_video(URL, session)
    video.prompt_version = "versao-antiga"
    await session.commit()
    fake.calls.clear()

    await pipeline.process_video(URL, session)

    assert fake.calls == ["llm"]  # transcrição reaproveitada


async def test_process_video_skip_llm_then_generate(
    session: AsyncSession, fake: FakeServices
) -> None:
    video = await pipeline.process_video(URL, session, skip_llm=True)
    assert fake.calls == [f"metadata:{YOUTUBE_ID}", "transcribe"]
    assert video.transcript == SPEECH
    assert video.generated_recipe is None

    fake.calls.clear()
    video = await pipeline.process_video(URL, session)
    assert fake.calls == ["llm"]
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
    assert fake.calls == []


async def test_process_video_not_a_recipe_without_speech_reports_no_transcript(
    session: AsyncSession, fake: FakeServices
) -> None:
    fake.transcript = Transcript([], TranscriptSource.WHISPER)
    fake.meta = replace(META, description=" ".join(["palavra"] * 30))
    fake.recipe = RECIPE.model_copy(update={"is_recipe": False})

    with pytest.raises(NoTranscriptError):
        await pipeline.process_video(URL, session)


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
