from collections.abc import Callable
from typing import Annotated, Any

from arq.connections import ArqRedis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import RateLimit, Settings, get_settings
from app.db import get_session
from app.errors import AppError, CsrfError, EmailNotVerifiedError, UnauthorizedError
from app.models import User
from app.services import auth, rate_limit, security

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> ArqRedis:
    return request.app.state.redis


RedisDep = Annotated[ArqRedis, Depends(get_redis)]

CSRF_HEADER = "X-Requested-With"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


async def csrf_protect(request: Request) -> None:
    """Proteção contra CSRF para os métodos que mudam estado.

    A sessão vai num cookie, que o navegador manda sozinho até em pedidos forjados por outro
    site. Exigir um header próprio (`X-Requested-With`) obriga o navegador a fazer o preflight
    de CORS, que só libera as origens de `CORS_ORIGINS`; e um `Origin` presente precisa ser uma
    delas. Clientes fora do navegador (curl) não mandam `Origin` e só precisam do header.
    """
    if request.method in _SAFE_METHODS:
        return
    if not request.headers.get(CSRF_HEADER):
        raise CsrfError(detail=f"sem o header {CSRF_HEADER}")
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in {
        allowed.rstrip("/") for allowed in get_settings().cors_origins
    }:
        raise CsrfError(detail=f"origem não permitida: {origin}")


async def get_session_claims(request: Request) -> security.SessionClaims:
    token = request.cookies.get(security.SESSION_COOKIE)
    if not token:
        raise UnauthorizedError(detail="sem cookie de sessão")
    try:
        return security.decode_session_token(token)
    except AppError as exc:
        raise UnauthorizedError(detail=exc.detail) from exc


SessionClaimsDep = Annotated[security.SessionClaims, Depends(get_session_claims)]


async def get_current_user(claims: SessionClaimsDep, session: SessionDep, redis: RedisDep) -> User:
    """Usuário da sessão (cookie). 401 se faltar, expirar, tiver saído ou trocado a senha."""
    return await auth.user_for_session(session, redis, claims)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_verified_user(user: CurrentUser) -> User:
    if user.email_verified_at is None:
        raise EmailNotVerifiedError()
    return user


VerifiedUser = Annotated[User, Depends(get_verified_user)]


def ip_rate_limit(action: str, limit: Callable[[Settings], RateLimit]) -> Any:
    """Dependência que conta o pedido no limite por IP da ação (lido das settings a cada vez)."""

    async def dependency(request: Request, redis: RedisDep) -> None:
        await rate_limit.check_ip(redis, request, action, limit(get_settings()))

    return Depends(dependency)
