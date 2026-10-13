import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.config import Settings
from app.models import Recipe, Video
from app.schemas.recipe_llm import RecipeLLM
from app.services import demo, recipe_llm
from app.services.imports import is_ready
from tests.factories import headers, make_user, make_video


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
    assert all(is_ready(v) and v.embeddable for v in videos)
    assert all(v.prompt_version == recipe_llm.PROMPT_VERSION for v in videos)

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
    assert is_ready(video)


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
