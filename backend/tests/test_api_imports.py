import uuid
from typing import Any

import pytest
from arq.connections import ArqRedis
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.models import Import, ImportStatus, Recipe
from tests.factories import GENERATED, headers, make_recipe, make_user, make_video

URL = "https://youtu.be/abcdefghijk?si=xyz"


async def _queued(redis: ArqRedis, queue_name: str = queue.DEFAULT_QUEUE) -> list[str]:
    return [job.job_id or "" for job in await redis.queued_jobs(queue_name=queue_name)]


async def _recipes(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Recipe)) or 0


async def test_new_video_is_queued(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis
) -> None:
    user = await make_user(session)

    response = await client.post("/imports", headers=headers(user.id), json={"url": URL})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["youtube_id"] == "abcdefghijk"
    assert body["url"] == URL
    assert body["recipe_id"] is None and body["error"] is None
    assert body["queue_position"] == 1

    assert await _queued(redis) == [f"import:{body['id']}"]
    job = (await redis.queued_jobs())[0]
    assert (job.function, job.args) == (queue.PROCESS_IMPORT, (body["id"],))

    imp = await session.get(Import, uuid.UUID(body["id"]))
    assert imp is not None and imp.user_id == user.id


async def test_invalid_url_is_rejected_without_queueing(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis
) -> None:
    user = await make_user(session)

    response = await client.post(
        "/imports", headers=headers(user.id), json={"url": "https://vimeo.com/123"}
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_url",
            "message": "Esse link não parece ser de um vídeo do YouTube. Confira e tente de novo.",
        }
    }
    assert await _queued(redis) == []
    assert await session.scalar(select(func.count()).select_from(Import)) == 0


async def test_missing_url_is_a_validation_error(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session)

    response = await client.post("/imports", headers=headers(user.id), json={})

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.url"


async def test_recipe_already_in_book_returns_it(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis
) -> None:
    user = await make_user(session)
    recipe = await make_recipe(session, user, await make_video(session))

    response = await client.post(
        "/imports",
        headers=headers(user.id),
        json={"url": "https://www.youtube.com/watch?v=abcdefghijk"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["recipe_id"] == str(recipe.id)
    assert body["queue_position"] is None
    assert await _queued(redis) == []
    assert await _recipes(session) == 1


async def test_processed_video_is_copied_right_away(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis
) -> None:
    owner, user = await make_user(session), await make_user(session, "Bia")
    video = await make_video(session)
    await make_recipe(session, owner, video, title="Editada pela dona")

    response = await client.post("/imports", headers=headers(user.id), json={"url": URL})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert await _queued(redis) == []

    copy = await session.get(Recipe, uuid.UUID(body["recipe_id"]))
    assert copy is not None
    assert (copy.user_id, copy.video_id) == (user.id, video.id)
    assert copy.title == GENERATED["title"]  # vem da canônica, não da cópia de outra pessoa
    assert copy.ingredients == GENERATED["ingredients"]


@pytest.mark.parametrize(
    "video_kwargs",
    [
        {"prompt_version": "versao-antiga"},
        {"generated": {**GENERATED, "is_recipe": False}},
        {"generated": None},
    ],
    ids=["prompt-antigo", "nao-e-receita", "sem-receita"],
)
async def test_video_without_usable_recipe_is_queued(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis, video_kwargs: dict[str, Any]
) -> None:
    user = await make_user(session)
    await make_video(session, **video_kwargs)

    response = await client.post("/imports", headers=headers(user.id), json={"url": URL})

    assert response.status_code == 202
    assert len(await _queued(redis)) == 1
    assert await _recipes(session) == 0


async def test_same_video_twice_reuses_import_in_progress(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis
) -> None:
    user, other = await make_user(session), await make_user(session, "Bia")

    first = await client.post("/imports", headers=headers(user.id), json={"url": URL})
    again = await client.post(
        "/imports",
        headers=headers(user.id),
        json={"url": "https://youtube.com/shorts/abcdefghijk"},
    )
    from_other = await client.post("/imports", headers=headers(other.id), json={"url": URL})

    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert from_other.status_code == 202
    assert from_other.json()["id"] != first.json()["id"]
    assert await _queued(redis) == [
        f"import:{first.json()['id']}",
        f"import:{from_other.json()['id']}",
    ]
    assert from_other.json()["queue_position"] == 2


async def test_queue_down_fails_import(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(session)

    async def broken(*args: object, **kwargs: object) -> bool:
        raise RedisConnectionError("conexão recusada")

    monkeypatch.setattr(queue, "enqueue_import", broken)

    response = await client.post("/imports", headers=headers(user.id), json={"url": URL})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "queue_unavailable"
    imp = await session.scalar(select(Import))
    assert imp is not None
    assert (imp.status, imp.error_code) == (ImportStatus.FAILED, "queue_unavailable")


async def test_get_import(client: AsyncClient, session: AsyncSession, redis: ArqRedis) -> None:
    user = await make_user(session)
    created = (await client.post("/imports", headers=headers(user.id), json={"url": URL})).json()

    response = await client.get(f"/imports/{created['id']}", headers=headers(user.id))

    assert response.status_code == 200
    assert response.json() == created


async def test_get_failed_import_shows_error(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    imp = Import(
        user_id=user.id,
        url=URL,
        youtube_id="abcdefghijk",
        status=ImportStatus.FAILED,
        error_code="not_embeddable",
        error_message="Não dá para exibir.",
    )
    session.add(imp)
    await session.commit()

    response = await client.get(f"/imports/{imp.id}", headers=headers(user.id))

    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == {"code": "not_embeddable", "message": "Não dá para exibir."}
    assert body["queue_position"] is None


async def test_get_import_in_whisper_queue_shows_position(
    client: AsyncClient, session: AsyncSession, redis: ArqRedis
) -> None:
    user = await make_user(session)
    await queue.enqueue_whisper(redis, "outrovideo1", "pt")
    await queue.enqueue_whisper(redis, "abcdefghijk", "pt")
    imp = Import(
        user_id=user.id, url=URL, youtube_id="abcdefghijk", status=ImportStatus.TRANSCRIBING
    )
    session.add(imp)
    await session.commit()

    response = await client.get(f"/imports/{imp.id}", headers=headers(user.id))

    assert response.json()["queue_position"] == 2


async def test_import_of_another_user_is_not_found(
    client: AsyncClient, session: AsyncSession
) -> None:
    owner, intruder = await make_user(session), await make_user(session, "Bia")
    created = (await client.post("/imports", headers=headers(owner.id), json={"url": URL})).json()

    response = await client.get(f"/imports/{created['id']}", headers=headers(intruder.id))

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "not_found",
        "message": "Importação não encontrada.",
    }


async def test_imports_require_user(client: AsyncClient) -> None:
    response = await client.post("/imports", json={"url": URL})
    assert response.status_code == 401
