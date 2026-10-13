import base64
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import Import, Recipe, User
from tests.factories import GENERATED, headers, make_recipe, make_user, make_video, youtube_id


async def test_get_recipe_with_video(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    video = await make_video(session)
    recipe = await make_recipe(session, user, video, is_favorite=True)

    response = await client.get(f"/recipes/{recipe.id}", headers=headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(recipe.id)
    assert body["title"] == "Bolo de cenoura"
    assert body["ingredients"][0] == {
        "name": "cenoura",
        "quantity": "3",
        "unit": None,
        "note": "média",
        "group": "massa",
    }
    assert body["steps"][1] == {
        "order": 2,
        "text": "Asse por 40 minutos.",
        "video_timestamp_s": 300,
    }
    assert body["is_favorite"] is True
    assert body["video"] == {
        "youtube_id": "abcdefghijk",
        "title": "Bolo de cenoura fofinho",
        "channel": "Receitas",
        "thumbnail_url": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
        "duration_s": 600,
    }


@pytest.mark.parametrize(
    ("method", "suffix", "json"),
    [
        ("GET", "", None),
        ("PATCH", "", {"title": "Meu bolo"}),
        ("DELETE", "", None),
        ("POST", "/reset", None),
    ],
)
async def test_recipe_of_another_user_is_not_found(
    client: AsyncClient, session: AsyncSession, method: str, suffix: str, json: Any
) -> None:
    owner, intruder = await make_user(session), await make_user(session, "Bia")
    recipe = await make_recipe(session, owner, await make_video(session))

    response = await client.request(
        method, f"/recipes/{recipe.id}{suffix}", headers=headers(intruder.id), json=json
    )

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Receita não encontrada."}}
    still_there = await session.get(Recipe, recipe.id, populate_existing=True)
    assert still_there is not None and still_there.title == "Bolo de cenoura"


async def test_unknown_recipe_is_not_found(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    response = await client.get(f"/recipes/{uuid.uuid4()}", headers=headers(user.id))
    assert response.status_code == 404


async def test_requires_dev_user_header(client: AsyncClient) -> None:
    response = await client.get("/recipes")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_invalid_dev_user_header(client: AsyncClient) -> None:
    response = await client.get("/recipes", headers={"X-Dev-User-Id": "ana"})
    assert response.status_code == 401


async def test_dev_user_is_created_on_first_request(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id = uuid.uuid4()

    for _ in range(2):
        response = await client.get("/recipes", headers=headers(user_id))
        assert response.status_code == 200

    user = await session.get(User, user_id)
    assert user is not None and user.email == f"dev-{user_id}@receita.local"


async def test_dev_header_is_ignored_outside_development(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")

    response = await client.get("/recipes", headers=headers(uuid.uuid4()))

    assert response.status_code == 401


def test_dev_login_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    assert Settings(_env_file=None).environment != "development"


async def test_patch_updates_only_sent_fields(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    recipe = await make_recipe(session, user, await make_video(session))
    before = recipe.updated_at

    response = await client.patch(
        f"/recipes/{recipe.id}",
        headers=headers(user.id),
        json={
            "title": "  Bolo da vovó ",
            "is_favorite": True,
            "rating": 5,
            "user_notes": "Usei menos açúcar.",
            "tags": ["Bolo", "#Café", "bolo", " "],
            "steps": [
                {"order": 7, "text": "Asse.", "video_timestamp_s": 10},
                {"text": "Sirva."},
            ],
            "servings": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Bolo da vovó"
    assert body["is_favorite"] is True
    assert body["rating"] == 5
    assert body["user_notes"] == "Usei menos açúcar."
    assert body["tags"] == ["bolo", "café"]
    assert body["steps"] == [
        {"order": 1, "text": "Asse.", "video_timestamp_s": 10},
        {"order": 2, "text": "Sirva.", "video_timestamp_s": None},
    ]
    assert body["servings"] is None
    assert body["summary"] == GENERATED["summary"]
    assert body["ingredients"] == GENERATED["ingredients"]

    saved = await session.get(Recipe, recipe.id, populate_existing=True)
    assert saved is not None and saved.title == "Bolo da vovó"
    assert saved.updated_at > before


async def test_patch_can_clear_rating(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    recipe = await make_recipe(session, user, await make_video(session), rating=3)

    response = await client.patch(
        f"/recipes/{recipe.id}", headers=headers(user.id), json={"rating": None}
    )

    assert response.status_code == 200
    assert response.json()["rating"] is None


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"rating": 0}, "body.rating"),
        ({"rating": 6}, "body.rating"),
        ({"title": None}, "body"),
        ({"title": "   "}, "body.title"),
        ({"ingredients": [{"quantity": "2"}]}, "body.ingredients.0.name"),
        ({"prep_time_min": -1}, "body.prep_time_min"),
        ({"difficulty": "impossível"}, "body.difficulty"),
        ({"video_id": str(uuid.uuid4())}, "body.video_id"),
        # O Postgres recusa o caractere NUL: sem a validação, viraria erro 500.
        ({"title": "bolo\x00"}, "body.title"),
        ({"summary": "\x00"}, "body.summary"),
        ({"servings": "8\x00"}, "body.servings"),
        ({"ingredients": [{"name": "ovo", "note": "\x00"}]}, "body.ingredients.0.note"),
        ({"steps": [{"text": "asse\x00"}]}, "body.steps.0.text"),
        ({"tips": ["ok", "a\x00b"]}, "body.tips.1"),
        ({"tags": ["a\x00b"]}, "body.tags.0"),
        ({"user_notes": "nota\x00"}, "body.user_notes"),
    ],
)
async def test_patch_validation(
    client: AsyncClient, session: AsyncSession, payload: dict[str, Any], field: str
) -> None:
    user = await make_user(session)
    recipe = await make_recipe(session, user, await make_video(session))

    response = await client.patch(f"/recipes/{recipe.id}", headers=headers(user.id), json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Alguns dados enviados são inválidos."
    assert error["details"][0]["field"] == field


async def test_delete_recipe(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    video = await make_video(session)
    recipe = await make_recipe(session, user, video)
    imp = Import(user_id=user.id, url="u", youtube_id=video.youtube_id, recipe_id=recipe.id)
    session.add(imp)
    await session.commit()

    response = await client.delete(f"/recipes/{recipe.id}", headers=headers(user.id))
    assert response.status_code == 204

    response = await client.get(f"/recipes/{recipe.id}", headers=headers(user.id))
    assert response.status_code == 404
    saved_import = await session.get(Import, imp.id, populate_existing=True)
    assert saved_import is not None and saved_import.recipe_id is None


async def test_reset_restores_generated_recipe(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    recipe = await make_recipe(session, user, await make_video(session))
    edits = {
        "title": "Bolo editado",
        "ingredients": [{"name": "beterraba"}],
        "steps": [{"text": "Improvise."}],
        "tags": ["outro"],
        "is_favorite": True,
        "rating": 4,
        "user_notes": "minha nota",
    }
    response = await client.patch(f"/recipes/{recipe.id}", headers=headers(user.id), json=edits)
    assert response.status_code == 200

    response = await client.post(f"/recipes/{recipe.id}/reset", headers=headers(user.id))

    assert response.status_code == 200
    body = response.json()
    for field in ("title", "summary", "servings", "ingredients", "steps", "tips", "tags"):
        assert body[field] == GENERATED[field], field
    assert (body["is_favorite"], body["rating"], body["user_notes"]) == (True, 4, "minha nota")


async def test_reset_without_generated_recipe(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    video = await make_video(session)
    recipe = await make_recipe(session, user, video)
    video.generated_recipe = None
    await session.commit()

    response = await client.post(f"/recipes/{recipe.id}/reset", headers=headers(user.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_original_recipe"


# --- Listagem ---------------------------------------------------------------------------------


async def _book(session: AsyncSession, user: User) -> dict[str, Recipe]:
    """Três receitas criadas em ordem: pão de queijo (mais antiga), feijoada, mousse."""
    specs = [
        ("pao", "Pão de queijo", ["polvilho", "queijo"], ["lanche", "mineira"], False),
        ("feijoada", "Feijoada completa", ["feijão preto", "linguiça"], ["almoço"], True),
        ("mousse", "Mousse de maracujá", ["maracujá", "leite condensado"], ["sobremesa"], True),
    ]
    book: dict[str, Recipe] = {}
    for n, (key, title, ingredients, tags, favorite) in enumerate(specs):
        video = await make_video(session, youtube_id(n))
        book[key] = await make_recipe(
            session,
            user,
            video,
            title=title,
            ingredients=[{"name": name} for name in ingredients],
            tags=tags,
            is_favorite=favorite,
        )
    return book


async def _titles(client: AsyncClient, user: User, **params: Any) -> list[str]:
    response = await client.get("/recipes", headers=headers(user.id), params=params)
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


async def test_list_is_recent_first_and_scoped_to_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, other = await make_user(session), await make_user(session, "Bia")
    await _book(session, user)
    await make_recipe(session, other, await make_video(session, "outrovideo1"), title="Alheia")

    assert await _titles(client, user) == [
        "Mousse de maracujá",
        "Feijoada completa",
        "Pão de queijo",
    ]
    assert await _titles(client, other) == ["Alheia"]


async def test_list_item_shape(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    await make_recipe(session, user, await make_video(session))

    response = await client.get("/recipes", headers=headers(user.id))

    item = response.json()["items"][0]
    assert item["video"]["youtube_id"] == "abcdefghijk"
    assert item["tags"] == GENERATED["tags"]
    assert "ingredients" not in item and "steps" not in item


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("feijoada", ["Feijoada completa"]),
        ("PAO", ["Pão de queijo"]),  # sem acento e em maiúsculas
        ("maracuja", ["Mousse de maracujá"]),
        ("polvilho", ["Pão de queijo"]),  # ingrediente
        ("feijao", ["Feijoada completa"]),
        ("mineira", ["Pão de queijo"]),  # tag
        ("leite condensado", ["Mousse de maracujá"]),  # termos em qualquer ordem
        ("queijo almoço", []),
        ("%", []),
        ("name", []),  # não procura nas chaves do JSON
    ],
)
async def test_list_search(
    client: AsyncClient, session: AsyncSession, q: str, expected: list[str]
) -> None:
    user = await make_user(session)
    await _book(session, user)

    assert await _titles(client, user, q=q) == expected


async def test_list_filters(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    await _book(session, user)

    assert await _titles(client, user, tag="Sobremesa") == ["Mousse de maracujá"]
    assert await _titles(client, user, favorite="true") == [
        "Mousse de maracujá",
        "Feijoada completa",
    ]
    assert await _titles(client, user, favorite="false") == ["Pão de queijo"]
    assert await _titles(client, user, favorite="true", q="feijao") == ["Feijoada completa"]


async def test_list_pagination(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)
    await _book(session, user)

    first = (await client.get("/recipes", headers=headers(user.id), params={"limit": 2})).json()
    assert [i["title"] for i in first["items"]] == ["Mousse de maracujá", "Feijoada completa"]
    assert first["next_cursor"]

    second = (
        await client.get(
            "/recipes",
            headers=headers(user.id),
            params={"limit": 2, "cursor": first["next_cursor"]},
        )
    ).json()
    assert [i["title"] for i in second["items"]] == ["Pão de queijo"]
    assert second["next_cursor"] is None


async def test_list_invalid_params(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)

    response = await client.get("/recipes", headers=headers(user.id), params={"cursor": "lixo"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"

    response = await client.get("/recipes", headers=headers(user.id), params={"limit": 0})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "query.limit"


@pytest.mark.parametrize(
    "created_at",
    [
        "0001-01-01T00:00:00+05:00",
        "9999-12-31T23:59:59-14:00",
        "1999-12-31T23:59:59+00:00",
        "2026-10-13T12:00:00",
    ],
    ids=["antes-do-ano-1-em-utc", "depois-de-9999-em-utc", "antes-de-2000", "sem-fuso"],
)
async def test_forged_cursor_is_rejected(
    client: AsyncClient, session: AsyncSession, created_at: str
) -> None:
    user = await make_user(session)
    raw = f"{created_at}|{uuid.uuid4()}".encode()
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    response = await client.get("/recipes", headers=headers(user.id), params={"cursor": cursor})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"


@pytest.mark.parametrize("param", ["q", "tag"])
async def test_list_rejects_nul_char(
    client: AsyncClient, session: AsyncSession, param: str
) -> None:
    user = await make_user(session)

    response = await client.get("/recipes", headers=headers(user.id), params={param: "a\x00b"})

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == f"query.{param}"


async def test_unknown_route_uses_error_format(client: AsyncClient) -> None:
    response = await client.get("/nada")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Não encontramos o que você procurou."}
    }
