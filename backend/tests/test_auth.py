import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import FORGOT_PASSWORD_MESSAGE
from app.config import Settings
from app.models import User
from app.services import security, turnstile
from app.services.email import Email
from tests.factories import CSRF, headers, make_user

PASSWORD = "senha-forte-123"
NEW_PASSWORD = "outra-senha-456"
URL = "https://youtu.be/abcdefghijk"


def _token_from(email: Email, path: str) -> str:
    match = re.search(rf"http://localhost:5173{path}\?token=([\w.-]+)", email.text)
    assert match is not None, email.text
    return match[1]


async def _register(
    client: AsyncClient, email: str = "Ana.Silva@Example.com", password: str = PASSWORD
) -> httpx.Response:
    return await client.post(
        "/auth/register",
        headers=CSRF,
        json={"name": "  Ana Silva ", "email": email, "password": password},
    )


async def _login(
    client: AsyncClient, email: str = "ana.silva@example.com", password: str = PASSWORD
) -> httpx.Response:
    return await client.post(
        "/auth/login", headers=CSRF, json={"email": email, "password": password}
    )


async def _user_with_password(session: AsyncSession, password: str = PASSWORD) -> User:
    return await make_user(session, password_hash=await security.hash_password(password))


async def test_register_verify_login_me_logout(
    client: AsyncClient, session: AsyncSession, outbox: list[Email]
) -> None:
    response = await _register(client)

    assert response.status_code == 202
    assert "confirmar o cadastro" in response.json()["message"]
    assert "set-cookie" not in response.headers
    user = await session.scalar(select(User))
    assert user is not None
    assert (user.email, user.name, user.email_verified_at) == (
        "ana.silva@example.com",
        "Ana Silva",
        None,
    )
    assert user.password_hash.startswith("$argon2id$")
    [verification] = outbox
    assert verification.to == "ana.silva@example.com"
    token = _token_from(verification, "/verificar-email")

    # Antes de confirmar dá para entrar, mas não para importar.
    response = await _login(client, "ANA.SILVA@example.com ")
    assert response.status_code == 200
    assert response.json()["email_verified"] is False
    response = await client.post("/imports", headers=CSRF, json={"url": URL})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"

    response = await client.post("/auth/verify", headers=CSRF, json={"token": token})
    assert response.status_code == 204
    # O link pode ser aberto de novo sem erro.
    assert (
        await client.post("/auth/verify", headers=CSRF, json={"token": token})
    ).status_code == 204

    response = await _login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{security.SESSION_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=2592000" in cookie
    assert "Secure" not in cookie  # development

    response = await client.get("/auth/me")
    assert response.status_code == 200
    me = response.json()
    assert me["id"] == str(user.id)
    assert (me["name"], me["email"], me["email_verified"], me["plan"]) == (
        "Ana Silva",
        "ana.silva@example.com",
        True,
        "free",
    )
    assert me["quota"]["used"] == 0 and me["quota"]["limit"] == 10
    assert me["quota"]["remaining"] == 10
    resets_at = datetime.fromisoformat(me["quota"]["resets_at"])
    assert resets_at.utcoffset() == timedelta(0)
    assert (resets_at.hour, resets_at.minute) == (0, 0)
    assert timedelta(0) < resets_at - datetime.now(UTC) <= timedelta(days=1)

    session_cookie = client.cookies[security.SESSION_COOKIE]
    response = await client.post("/auth/logout", headers=CSRF)
    assert response.status_code == 204
    assert 'receita_session=""' in response.headers["set-cookie"]
    assert security.SESSION_COOKIE not in client.cookies

    # O token da sessão encerrada não vale mais, mesmo que alguém o tenha guardado.
    response = await client.get(
        "/auth/me", headers={"Cookie": f"{security.SESSION_COOKIE}={session_cookie}"}
    )
    assert response.status_code == 401


async def test_register_with_existing_email_looks_the_same(
    client: AsyncClient, session: AsyncSession, outbox: list[Email]
) -> None:
    first = await _register(client)
    outbox.clear()

    again = await _register(client, "  ANA.silva@example.COM", "outra-senha-qualquer")

    assert (again.status_code, again.json()) == (first.status_code, first.json())
    assert await session.scalar(select(func.count()).select_from(User)) == 1
    [notice] = outbox
    assert notice.subject == "Você já tem uma conta no Receita"
    assert "http://localhost:5173/entrar" in notice.text
    # A senha da conta não muda.
    assert (await _login(client)).status_code == 200


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"name": "Ana", "email": "ana@example.com", "password": "curta12"}, "body.password"),
        ({"name": "Ana", "email": "sem-arroba", "password": PASSWORD}, "body.email"),
        ({"name": "   ", "email": "ana@example.com", "password": PASSWORD}, "body.name"),
        ({"name": "Ana", "email": "ana@example.com", "password": "x" * 129}, "body.password"),
    ],
    ids=["senha-curta", "email-invalido", "nome-vazio", "senha-enorme"],
)
async def test_register_validation(
    client: AsyncClient, session: AsyncSession, payload: dict[str, str], field: str
) -> None:
    response = await client.post("/auth/register", headers=CSRF, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field
    assert await session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    ("email", "password"),
    [("ana.silva@example.com", "senha-errada"), ("ninguem@example.com", PASSWORD)],
    ids=["senha-errada", "email-sem-conta"],
)
async def test_login_failure_does_not_say_why(
    client: AsyncClient, outbox: list[Email], email: str, password: str
) -> None:
    await _register(client)

    response = await _login(client, email, password)

    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "invalid_credentials",
        "message": "E-mail ou senha incorretos.",
    }
    assert "set-cookie" not in response.headers


async def test_account_without_password_cannot_log_in(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session)  # hash "!"

    response = await _login(client, user.email, "!")

    assert response.status_code == 401


async def test_session_cookie_is_secure_outside_development(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _user_with_password(session)
    monkeypatch.setattr(settings, "environment", "production")

    response = await _login(client, user.email)

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


async def test_password_reset_is_single_use_and_ends_sessions(
    client: AsyncClient, session: AsyncSession, outbox: list[Email]
) -> None:
    user = await _user_with_password(session)
    old_session = headers(user)

    response = await client.post("/auth/forgot-password", headers=CSRF, json={"email": user.email})

    assert response.status_code == 200
    [reset] = outbox
    assert reset.to == user.email
    token = _token_from(reset, "/redefinir-senha")

    response = await client.post(
        "/auth/reset-password", headers=CSRF, json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 204

    assert (await _login(client, user.email, PASSWORD)).status_code == 401
    assert (await _login(client, user.email, NEW_PASSWORD)).status_code == 200
    assert (await client.get("/auth/me", headers=old_session)).status_code == 401

    response = await client.post(
        "/auth/reset-password", headers=CSRF, json={"token": token, "password": "terceira-senha"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"
    assert (await _login(client, user.email, NEW_PASSWORD)).status_code == 200


async def test_password_reset_confirms_email(
    client: AsyncClient, session: AsyncSession, outbox: list[Email]
) -> None:
    user = await make_user(session, verified=False, password_hash="!")
    await client.post("/auth/forgot-password", headers=CSRF, json={"email": user.email})
    token = _token_from(outbox[0], "/redefinir-senha")

    await client.post(
        "/auth/reset-password", headers=CSRF, json={"token": token, "password": NEW_PASSWORD}
    )

    await session.refresh(user)
    assert user.email_verified_at is not None


async def test_forgot_password_for_unknown_email_looks_the_same(
    client: AsyncClient, session: AsyncSession, outbox: list[Email]
) -> None:
    user = await make_user(session)
    known = await client.post("/auth/forgot-password", headers=CSRF, json={"email": user.email})

    unknown = await client.post(
        "/auth/forgot-password", headers=CSRF, json={"email": "ninguem@example.com"}
    )

    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json() == {"message": FORGOT_PASSWORD_MESSAGE}
    assert [email.to for email in outbox] == [user.email]


async def test_forgot_password_emails_are_limited_per_address(
    client: AsyncClient,
    session: AsyncSession,
    outbox: list[Email],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(session)
    monkeypatch.setattr(settings, "trust_proxy_headers", True)

    # De IPs diferentes: o limite por IP não pega, o por e-mail sim (sem avisar quem pede).
    for n in range(7):
        response = await client.post(
            "/auth/forgot-password",
            headers={**CSRF, "X-Forwarded-For": f"203.0.113.{n}"},
            json={"email": user.email},
        )
        assert response.status_code == 200

    assert len(outbox) == settings.rate_limit_forgot_password.requests


@pytest.mark.parametrize("kind", ["lixo", "outra-finalidade", "expirado", "outra-chave"])
async def test_invalid_tokens_are_rejected(
    client: AsyncClient, session: AsyncSession, settings: Settings, kind: str
) -> None:
    user = await make_user(session, verified=False)
    match kind:
        case "lixo":
            token = "isso.nao.e-um-token"
        case "outra-finalidade":
            token = security.create_password_reset_token(user.id, user.password_hash)
        case "expirado":
            token = jwt.encode(
                {
                    "sub": str(user.id),
                    "aud": "verify-email",
                    "email": user.email,
                    "iat": datetime.now(UTC) - timedelta(days=3),
                    "exp": datetime.now(UTC) - timedelta(days=1),
                },
                settings.secret_key.get_secret_value(),
                algorithm=security.ALGORITHM,
            )
        case _:
            token = jwt.encode(
                {
                    "sub": str(user.id),
                    "aud": "verify-email",
                    "email": user.email,
                    "iat": datetime.now(UTC),
                    "exp": datetime.now(UTC) + timedelta(days=1),
                },
                "x" * 40,
                algorithm=security.ALGORITHM,
            )

    response = await client.post("/auth/verify", headers=CSRF, json={"token": token})

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "invalid_token",
        "message": "Este link é inválido ou expirou. Peça um novo.",
    }
    await session.refresh(user)
    assert user.email_verified_at is None


async def test_verification_token_of_deleted_user_is_invalid(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = security.create_email_verification_token(uuid.uuid4(), "fantasma@example.com")

    response = await client.post("/auth/verify", headers=CSRF, json={"token": token})

    assert response.status_code == 400


async def test_resend_verification(
    client: AsyncClient, session: AsyncSession, outbox: list[Email]
) -> None:
    pending, verified = await make_user(session, verified=False), await make_user(session)

    response = await client.post("/auth/resend-verification", headers=headers(pending))
    assert response.status_code == 200
    assert response.json()["message"] == (
        f"Enviamos um novo link de confirmação para {pending.email}."
    )
    response = await client.post("/auth/resend-verification", headers=headers(verified))
    assert response.json()["message"] == "Seu e-mail já está confirmado."

    [email] = outbox
    assert email.to == pending.email
    token = _token_from(email, "/verificar-email")
    assert (
        await client.post("/auth/verify", headers=CSRF, json={"token": token})
    ).status_code == 204


@pytest.mark.parametrize(
    "cookie",
    [
        "lixo",
        security.create_email_verification_token(uuid.uuid4(), "a@example.com"),
        security.create_session_token(uuid.uuid4(), "!"),
    ],
    ids=["lixo", "token-de-outra-finalidade", "usuario-inexistente"],
)
async def test_invalid_session_cookie_is_unauthorized(client: AsyncClient, cookie: str) -> None:
    response = await client.get(
        "/auth/me", headers={"Cookie": f"{security.SESSION_COOKIE}={cookie}"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/auth/me"),
        ("POST", "/auth/resend-verification"),
        ("GET", "/account/export"),
        ("DELETE", "/account"),
        ("POST", "/imports"),
        ("GET", f"/imports/{uuid.uuid4()}"),
        ("GET", "/recipes"),
        ("GET", f"/recipes/{uuid.uuid4()}"),
        ("PATCH", f"/recipes/{uuid.uuid4()}"),
        ("DELETE", f"/recipes/{uuid.uuid4()}"),
        ("POST", f"/recipes/{uuid.uuid4()}/reset"),
    ],
)
async def test_protected_routes_require_session(
    client: AsyncClient, method: str, path: str
) -> None:
    body = {"url": URL, "password": PASSWORD, "title": "x"} if method != "GET" else None

    response = await client.request(method, path, headers=CSRF, json=body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_logout_without_session_just_clears_cookie(client: AsyncClient) -> None:
    response = await client.post("/auth/logout", headers=CSRF)

    assert response.status_code == 204


# --- Turnstile --------------------------------------------------------------------------------


@pytest.fixture
def turnstile_enabled(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Liga o captcha com a Cloudflare simulada; devolve os formulários recebidos por ela."""
    received: list[dict[str, str]] = []
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr("segredo-turnstile"))

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        received.append(form)
        if form["response"] == "cai":
            raise httpx.ConnectError("sem rede")
        return httpx.Response(
            200, json={"success": form["response"] == "token-bom", "error-codes": []}
        )

    monkeypatch.setattr(
        turnstile, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return received


@pytest.mark.parametrize(
    ("token", "status", "code"),
    [
        ("token-bom", 202, None),
        ("token-ruim", 400, "captcha_failed"),
        (None, 400, "captcha_failed"),
        ("cai", 503, "captcha_unavailable"),
    ],
)
async def test_turnstile_on_register(
    client: AsyncClient,
    session: AsyncSession,
    outbox: list[Email],
    turnstile_enabled: list[dict[str, str]],
    token: str | None,
    status: int,
    code: str | None,
) -> None:
    body = {"name": "Ana", "email": "ana@example.com", "password": PASSWORD}
    if token is not None:
        body["cf-turnstile-response"] = token

    response = await client.post("/auth/register", headers=CSRF, json=body)

    assert response.status_code == status
    if code is not None:
        assert response.json()["error"]["code"] == code
    users = await session.scalar(select(func.count()).select_from(User))
    assert users == (1 if status == 202 else 0)
    if token is not None:
        assert turnstile_enabled[0]["secret"] == "segredo-turnstile"
        assert turnstile_enabled[0]["response"] == token
        assert turnstile_enabled[0]["remoteip"] == "127.0.0.1"


async def test_turnstile_is_skipped_without_secret(
    client: AsyncClient, outbox: list[Email]
) -> None:
    assert not turnstile.is_enabled()

    response = await _register(client)

    assert response.status_code == 202
