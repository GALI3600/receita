"""LGPD: exportar e apagar a conta."""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Import, ImportStatus, Recipe, User, Video
from app.services import security
from tests.factories import GENERATED, headers, make_recipe, make_user, make_video

PASSWORD = "senha-forte-123"


async def _user_with_password(session: AsyncSession, name: str = "Ana") -> User:
    return await make_user(session, name, password_hash=await security.hash_password(PASSWORD))


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_export_has_the_user_data_and_nothing_else(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, other = await make_user(session), await make_user(session, "Bia")
    video = await make_video(session)
    recipe = await make_recipe(session, user, video, user_notes="menos açúcar", rating=5)
    await make_recipe(session, other, video)
    imp = Import(
        user_id=user.id,
        url="https://youtu.be/abcdefghijk",
        youtube_id="abcdefghijk",
        status=ImportStatus.DONE,
        recipe_id=recipe.id,
    )
    session.add_all(
        [imp, Import(user_id=other.id, url="u", youtube_id="abcdefghijk")],
    )
    await session.commit()

    response = await client.get("/account/export", headers=headers(user))

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="receita-meus-dados.json"'
    )
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email
    assert body["user"]["email_verified_at"] is not None
    assert "password_hash" not in body["user"]
    [exported] = body["recipes"]
    assert exported["id"] == str(recipe.id)
    assert (exported["user_notes"], exported["rating"]) == ("menos açúcar", 5)
    assert exported["ingredients"] == GENERATED["ingredients"]
    assert exported["video"]["youtube_id"] == "abcdefghijk"
    [exported_import] = body["imports"]
    assert exported_import["id"] == str(imp.id)
    assert exported_import["recipe_id"] == str(recipe.id)
    assert body["exported_at"]


async def test_delete_account_requires_password(client: AsyncClient, session: AsyncSession) -> None:
    user = await _user_with_password(session)

    response = await client.request(
        "DELETE", "/account", headers=headers(user), json={"password": "senha-errada"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == {"code": "invalid_password", "message": "Senha incorreta."}
    assert await session.get(User, user.id) is not None


async def test_delete_account_removes_user_data_but_keeps_shared_videos(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, other = await _user_with_password(session), await make_user(session, "Bia")
    video = await make_video(session)
    recipe = await make_recipe(session, user, video)
    other_recipe = await make_recipe(session, other, video)
    session.add_all(
        [
            Import(
                user_id=user.id,
                url="u",
                youtube_id=video.youtube_id,
                status=ImportStatus.DONE,
                recipe_id=recipe.id,
            ),
            Import(user_id=other.id, url="u", youtube_id=video.youtube_id),
        ]
    )
    await session.commit()
    auth = headers(user)
    user_id, other_id, other_recipe_id = user.id, other.id, other_recipe.id

    response = await client.request("DELETE", "/account", headers=auth, json={"password": PASSWORD})

    assert response.status_code == 204
    assert 'receita_session=""' in response.headers["set-cookie"]
    session.expire_all()
    assert await session.get(User, user_id) is None
    assert (await session.scalars(select(Recipe.id))).all() == [other_recipe_id]
    assert (await session.scalars(select(Import.user_id))).all() == [other_id]
    assert await _count(session, Video) == 1
    assert await session.get(User, other_id) is not None

    assert (await client.get("/auth/me", headers=auth)).status_code == 401
