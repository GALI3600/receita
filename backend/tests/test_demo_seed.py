from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.config import Settings
from app.models import LLMPurpose, Recipe, Video
from app.schemas.recipe_llm import RecipeLLM
from app.services import demo, pipeline, recipe_llm
from app.services.imports import existing_recipe_id, is_ready
from app.services.recipe_llm import RecipeGeneration
from tests.factories import GENERATED, SPEECH, headers, make_user, make_video


def test_demo_recipes_follow_the_llm_schema() -> None:
    assert len(demo.DEMO_VIDEOS) >= 2
    for video in demo.DEMO_VIDEOS:
        recipe = RecipeLLM.model_validate(video.recipe)
        assert recipe.is_recipe
        assert len(video.youtube_id) == 11
        orders = [step.order for step in recipe.steps]
        assert orders == list(range(1, len(orders) + 1))
        timestamps = [s.video_timestamp_s for s in recipe.steps if s.video_timestamp_s is not None]
        assert all(0 <= t < video.duration_s for t in timestamps)
        # Contáveis sem unidade concordam com a quantidade: "3 cenouras", "4 ovos".
        for ingredient in recipe.ingredients:
            if ingredient.unit is None and (ingredient.quantity or "").isdigit():
                if int(ingredient.quantity or "0") > 1:
                    assert ingredient.name.split()[0].endswith("s"), ingredient.name


async def test_seed_demo_fills_the_users_book(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)

    recipe_ids = await demo.seed_demo(session, f"  {user.email.upper()} ")

    assert len(recipe_ids) == len(demo.DEMO_VIDEOS)
    videos = list(await session.scalars(select(Video)))
    assert {v.youtube_id for v in videos} == {d.youtube_id for d in demo.DEMO_VIDEOS}
    assert all(v.embeddable for v in videos)
    # A receita de demonstração não conta como gerada pelo Claude com o prompt atual.
    assert all(v.prompt_version == demo.DEMO_PROMPT_VERSION for v in videos)
    assert not any(is_ready(v) for v in videos)

    response = await client.get("/recipes", headers=headers(user))
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["items"]}
    assert titles == {d.recipe["title"] for d in demo.DEMO_VIDEOS}

    first = demo.DEMO_VIDEOS[0]
    detail = (await client.get(f"/recipes/{recipe_ids[0]}", headers=headers(user))).json()
    assert detail["video"]["youtube_id"] == first.youtube_id
    assert detail["video"]["thumbnail_url"] == first.thumbnail_url
    assert detail["steps"][0]["video_timestamp_s"] == first.recipe["steps"][0]["video_timestamp_s"]


async def test_seed_demo_is_idempotent_and_updates_existing_videos(session: AsyncSession) -> None:
    user = await make_user(session)
    # Um import anterior desse vídeo que falhou (sem receita) não impede o seed.
    await make_video(session, demo.DEMO_VIDEOS[0].youtube_id, generated=None, title="velho")

    first = await demo.seed_demo(session, user.email)
    second = await demo.seed_demo(session, user.email)

    assert first == second
    count = await session.scalar(select(func.count()).select_from(Recipe))
    assert count == len(demo.DEMO_VIDEOS)
    video = await session.scalar(
        select(Video).where(Video.youtube_id == demo.DEMO_VIDEOS[0].youtube_id)
    )
    assert video is not None
    await session.refresh(video)
    assert video.title == demo.DEMO_VIDEOS[0].title
    assert video.generated_recipe == demo.DEMO_VIDEOS[0].recipe
    assert video.prompt_version == demo.DEMO_PROMPT_VERSION


async def test_demo_video_is_generated_for_real_for_other_users(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await make_user(session)
    other = await make_user(session, "Bia")
    owner_ids = await demo.seed_demo(session, owner.email)
    first = demo.DEMO_VIDEOS[0]

    # O dono do seed continua com a cópia; os outros não recebem a receita de demonstração.
    assert await existing_recipe_id(session, owner.id, first.youtube_id) == owner_ids[0]
    assert await existing_recipe_id(session, other.id, first.youtube_id) is None

    generated = RecipeLLM.model_validate({**GENERATED, "title": "Bolo do Claude"})

    async def fake_generate(video: recipe_llm.VideoContext, **_: Any) -> RecipeGeneration:
        return RecipeGeneration(
            recipe=generated,
            model=recipe_llm.MODEL,
            usage={"input_tokens": 10, "output_tokens": 5},
            prompt_version=recipe_llm.PROMPT_VERSION,
        )

    monkeypatch.setattr(recipe_llm, "generate_recipe", fake_generate)
    video = await session.scalar(select(Video).where(Video.youtube_id == first.youtube_id))
    assert video is not None
    video.transcript = SPEECH  # o import de outra pessoa transcreve o vídeo antes de gerar
    await session.commit()

    video, was_generated = await pipeline.generate(session, video, purpose=LLMPurpose.CLI)

    assert was_generated
    assert video.generated_recipe is not None
    assert video.generated_recipe["title"] == "Bolo do Claude"
    assert (video.llm_model, video.prompt_version) == (recipe_llm.MODEL, recipe_llm.PROMPT_VERSION)
    assert is_ready(video)
    assert await existing_recipe_id(session, other.id, first.youtube_id) is not None


async def test_seed_demo_requires_an_existing_account(session: AsyncSession) -> None:
    with pytest.raises(demo.DemoSeedError, match="nenhuma conta"):
        await demo.seed_demo(session, "ninguem@example.com")


async def test_seed_demo_only_runs_in_development(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(session)
    monkeypatch.setattr(settings, "environment", "production")

    with pytest.raises(demo.DemoSeedError, match="development"):
        await demo.seed_demo(session, user.email)

    assert await session.scalar(select(func.count()).select_from(Video)) == 0


def test_cli_seed_demo_reports_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def refuse(session: object, email: str) -> list[object]:
        raise demo.DemoSeedError("seed-demo só roda com ENVIRONMENT=development")

    monkeypatch.setattr(cli, "seed_demo", refuse)

    assert cli.main(["seed-demo", "--email", "ana@example.com"]) == 1
    assert "ENVIRONMENT=development" in capsys.readouterr().err
