import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Difficulty, Import, ImportStatus, Recipe, User, UserPlan, Video
from app.schemas.transcript import Segment, TranscriptSource


def _user(email: str = "ana@example.com") -> User:
    return User(email=email, password_hash="hash", name="Ana")


def _video(youtube_id: str = "abcdefghijk") -> Video:
    return Video(youtube_id=youtube_id, title="Bolo", duration_s=300, embeddable=True)


async def test_create_full_graph(session: AsyncSession) -> None:
    user, video = _user(), _video()
    video.transcript = [Segment(start=0.0, end=2.5, text="olá")]
    video.transcript_source = TranscriptSource.WHISPER
    video.llm_usage = {"input_tokens": 10, "output_tokens": 5}
    session.add_all([user, video])
    await session.flush()

    recipe = Recipe(
        user_id=user.id,
        video_id=video.id,
        title="Bolo de cenoura",
        difficulty=Difficulty.EASY,
        ingredients=[{"name": "cenoura", "quantity": "3"}],
        tags=["sobremesa", "bolo"],
    )
    session.add(recipe)
    await session.flush()
    session.add(
        Import(
            user_id=user.id,
            url="https://youtu.be/abcdefghijk",
            youtube_id="abcdefghijk",
            recipe_id=recipe.id,
        )
    )
    await session.commit()

    session.expunge_all()
    loaded_user = await session.scalar(select(User))
    loaded_video = await session.scalar(select(Video))
    loaded_recipe = await session.scalar(select(Recipe))
    loaded_import = await session.scalar(select(Import))
    assert loaded_user is not None and loaded_video is not None
    assert loaded_recipe is not None and loaded_import is not None

    assert loaded_user.plan is UserPlan.FREE
    assert loaded_user.created_at.tzinfo is not None
    assert loaded_video.transcript == [{"start": 0.0, "end": 2.5, "text": "olá"}]
    assert loaded_video.transcript_source is TranscriptSource.WHISPER
    assert loaded_recipe.difficulty is Difficulty.EASY
    assert loaded_recipe.tags == ["sobremesa", "bolo"]
    assert loaded_recipe.tips == []
    assert loaded_recipe.is_favorite is False
    assert loaded_import.status is ImportStatus.PENDING

    raw = await session.execute(text("SELECT difficulty, status FROM recipes, imports"))
    assert raw.one() == ("fácil", "pending")


async def test_tags_are_searchable_with_array_contains(session: AsyncSession) -> None:
    user, video = _user(), _video()
    session.add_all([user, video])
    await session.flush()
    session.add(Recipe(user_id=user.id, video_id=video.id, title="Bolo", tags=["vegano"]))
    await session.commit()

    found = await session.scalar(select(Recipe.title).where(Recipe.tags.contains(["vegano"])))
    assert found == "Bolo"


async def test_video_youtube_id_is_unique(session: AsyncSession) -> None:
    session.add_all([_video(), _video()])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_user_email_is_unique(session: AsyncSession) -> None:
    session.add_all([_user(), _user()])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_recipe_is_unique_per_user_and_video(session: AsyncSession) -> None:
    user, video = _user(), _video()
    session.add_all([user, video])
    await session.flush()
    session.add_all(
        [
            Recipe(user_id=user.id, video_id=video.id, title="A"),
            Recipe(user_id=user.id, video_id=video.id, title="B"),
        ]
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_recipe_rating_range_is_checked(session: AsyncSession) -> None:
    user, video = _user(), _video()
    session.add_all([user, video])
    await session.flush()
    session.add(Recipe(user_id=user.id, video_id=video.id, title="A", rating=6))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_user_cascades_to_recipes_and_imports(session: AsyncSession) -> None:
    user, video = _user(), _video()
    session.add_all([user, video])
    await session.flush()
    session.add(Recipe(user_id=user.id, video_id=video.id, title="A"))
    session.add(Import(user_id=user.id, url="u", youtube_id=video.youtube_id))
    await session.commit()

    await session.execute(text("DELETE FROM users"))
    await session.commit()

    assert await session.scalar(select(Recipe)) is None
    assert await session.scalar(select(Import)) is None
    assert await session.scalar(select(Video)) is not None
