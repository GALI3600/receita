"""CSRF e rate limit por IP."""

from typing import Any

import pytest
from arq.connections import ArqRedis
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import RateLimit, Settings
from app.services import rate_limit
from app.services.email import Email
from tests.factories import CSRF, headers, make_user

LOGIN = {"email": "ana@example.com", "password": "qualquer-senha"}

# --- CSRF -------------------------------------------------------------------------------------


async def test_mutation_without_custom_header_is_blocked(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await make_user(session)
    cookie = {"Cookie": headers(user)["Cookie"]}

    for method, path, body in [
        ("POST", "/auth/login", LOGIN),
        ("POST", "/imports", {"url": "https://youtu.be/abcdefghijk"}),
        ("DELETE", "/account", {"password": "x"}),
        ("POST", "/auth/logout", None),
    ]:
        response = await client.request(method, path, headers=cookie, json=body)

        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "csrf_failed"

    # A sessão continua valendo: o logout bloqueado não chegou a rodar.
    assert (await client.get("/auth/me", headers=cookie)).status_code == 200


async def test_reads_do_not_need_the_header(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(session)

    response = await client.get("/auth/me", headers={"Cookie": headers(user)["Cookie"]})

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("origin", "status"),
    [
        ("https://site-malicioso.example", 403),
        ("null", 403),
        ("http://localhost:5173", 401),
        ("http://localhost:5173/", 401),
        (None, 401),
    ],
)
async def test_origin_must_be_an_allowed_one(
    client: AsyncClient, origin: str | None, status: int
) -> None:
    extra = {"Origin": origin} if origin is not None else {}

    response = await client.post("/auth/login", headers={**CSRF, **extra}, json=LOGIN)

    assert response.status_code == status  # 401: passou do CSRF e falhou no login


# --- Rate limit -------------------------------------------------------------------------------


def _request(client_host: str, forwarded_for: str | None = None) -> Request:
    raw_headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    scope: dict[str, Any] = {
        "type": "http",
        "headers": raw_headers,
        "client": (client_host, 1234),
    }
    return Request(scope)


def test_client_ip_ignores_forwarded_for_by_default() -> None:
    request = _request("10.0.0.5", "1.2.3.4")

    assert rate_limit.client_ip(request) == "10.0.0.5"


def test_client_ip_uses_last_forwarded_hop_behind_trusted_proxy(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)

    # O primeiro endereço foi escrito pelo cliente (forjável); o último, pelo proxy.
    assert rate_limit.client_ip(_request("10.0.0.5", "6.6.6.6, 1.2.3.4")) == "1.2.3.4"
    assert rate_limit.client_ip(_request("10.0.0.5")) == "10.0.0.5"


def test_ipv6_clients_share_their_64_network() -> None:
    assert rate_limit.ip_bucket("2001:db8:1:2:aaaa::1") == "2001:db8:1:2::/64"
    assert rate_limit.ip_bucket("2001:db8:1:2:bbbb::9") == "2001:db8:1:2::/64"
    assert rate_limit.ip_bucket("203.0.113.7") == "203.0.113.7"


def test_ipv6_addresses_carrying_ipv4_count_as_that_ipv4() -> None:
    # Num socket dual-stack, todo cliente IPv4 chega como ::ffff:a.b.c.d.
    assert rate_limit.ip_bucket("::ffff:1.2.3.4") == "1.2.3.4"
    assert rate_limit.ip_bucket("::ffff:5.6.7.8") == "5.6.7.8"
    # 6to4: cada IPv4 tem um /48 inteiro, então o /64 não seria limite.
    assert rate_limit.ip_bucket("2002:102:304:1::1") == "1.2.3.4"
    assert rate_limit.ip_bucket("2002:102:304:2::1") == "1.2.3.4"


async def test_dual_stack_ipv4_clients_have_separate_limits(
    client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_login", RateLimit(1, 60))
    monkeypatch.setattr(settings, "trust_proxy_headers", True)

    async def login(ip: str) -> int:
        response = await client.post(
            "/auth/login", headers={**CSRF, "X-Forwarded-For": ip}, json=LOGIN
        )
        return response.status_code

    assert [await login("::ffff:1.2.3.4"), await login("::ffff:5.6.7.8")] == [401, 401]
    assert await login("1.2.3.4") == 429


async def test_login_rate_limit(
    client: AsyncClient, redis: ArqRedis, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_login", RateLimit(2, 60))

    statuses = [
        (await client.post("/auth/login", headers=CSRF, json=LOGIN)).status_code for _ in range(2)
    ]
    blocked = await client.post("/auth/login", headers=CSRF, json=LOGIN)

    assert statuses == [401, 401]
    assert blocked.status_code == 429
    assert blocked.json()["error"] == {
        "code": "rate_limited",
        "message": "Muitas tentativas em pouco tempo. Espere um pouco e tente de novo.",
    }
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    [key] = await redis.keys("receita:rate:login:127.0.0.1:*")
    assert 0 < await redis.ttl(key) <= 60


async def test_forwarded_for_only_counts_behind_trusted_proxy(
    client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_login", RateLimit(1, 60))

    async def login(ip: str) -> int:
        response = await client.post(
            "/auth/login", headers={**CSRF, "X-Forwarded-For": ip}, json=LOGIN
        )
        return response.status_code

    # Sem proxy confiável, trocar o header não ajuda: todos são o mesmo IP.
    assert [await login("1.1.1.1"), await login("2.2.2.2")] == [401, 429]

    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    assert [await login("3.3.3.3"), await login("4.4.4.4"), await login("3.3.3.3")] == [
        401,
        401,
        429,
    ]


@pytest.mark.parametrize(
    ("setting", "method", "path", "body"),
    [
        (
            "rate_limit_register",
            "POST",
            "/auth/register",
            {"name": "Ana", "email": "ana@example.com", "password": "senha-forte-123"},
        ),
        ("rate_limit_forgot_password", "POST", "/auth/forgot-password", {"email": "a@example.com"}),
        ("rate_limit_imports", "POST", "/imports", {"url": "https://vimeo.com/1"}),
        ("rate_limit_resend_verification", "POST", "/auth/resend-verification", None),
    ],
)
async def test_rate_limited_routes(
    client: AsyncClient,
    session: AsyncSession,
    outbox: list[Email],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    user = await make_user(session, verified=False)
    monkeypatch.setattr(settings, setting, RateLimit(1, 3600))

    first = await client.request(method, path, headers=headers(user), json=body)
    second = await client.request(method, path, headers=headers(user), json=body)

    assert first.status_code != 429
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in second.headers


async def test_import_polling_is_not_rate_limited(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(session)
    monkeypatch.setattr(settings, "rate_limit_imports", RateLimit(1, 3600))

    for _ in range(3):
        response = await client.get("/recipes", headers=headers(user))
        assert response.status_code == 200


async def test_redis_down_lets_requests_through(
    client: AsyncClient, redis: ArqRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_pipeline(*args: object, **kwargs: object) -> object:
        raise RedisConnectionError("conexão recusada")

    monkeypatch.setattr(redis, "pipeline", broken_pipeline)

    response = await client.post("/auth/login", headers=CSRF, json=LOGIN)

    assert response.status_code == 401
