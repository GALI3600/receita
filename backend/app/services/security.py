"""Senhas (argon2) e tokens assinados (JWT HS256 com `SECRET_KEY`).

Cada token tem uma finalidade, gravada no `aud`: um token de verificação de e-mail não serve
de sessão nem de reset, e vice-versa. Sessão e reset carregam `pwd`, uma impressão do hash da
senha atual: trocar a senha invalida todas as sessões abertas e torna o link de reset de uso
único (depois de usado, o hash muda e o mesmo token não confere mais).
"""

import asyncio
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from app.config import get_settings
from app.errors import InvalidTokenError

ALGORITHM = "HS256"
SESSION_COOKIE = "receita_session"

_password_hash = PasswordHash.recommended()


class TokenPurpose(StrEnum):
    SESSION = "session"
    VERIFY_EMAIL = "verify-email"
    RESET_PASSWORD = "reset-password"


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: uuid.UUID
    session_id: str
    password_fingerprint: str
    expires_at: datetime


# --- Senhas -----------------------------------------------------------------------------------


async def hash_password(password: str) -> str:
    # O argon2 gasta dezenas de ms de CPU de propósito: fora do event loop.
    return await asyncio.to_thread(_password_hash.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    """Confere a senha; um hash que não é argon2 (ex.: "!" de contas sem senha) nunca confere."""
    try:
        return await asyncio.to_thread(_password_hash.verify, password, password_hash)
    except PwdlibError:
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _password_hash.hash(uuid.uuid4().hex)


async def burn_password_check(password: str) -> None:
    """Gasta o mesmo tempo de uma verificação real, para quando o e-mail não existe.

    Sem isso, o login responderia mais rápido para e-mails sem conta e revelaria quem tem.
    """
    dummy = await asyncio.to_thread(_dummy_hash)
    await verify_password(password, dummy)


def password_fingerprint(password_hash: str) -> str:
    """Impressão curta do hash da senha (HMAC): muda a cada troca de senha, não revela o hash."""
    key = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(key, password_hash.encode(), hashlib.sha256).hexdigest()[:32]


# --- Tokens -----------------------------------------------------------------------------------


def _encode(purpose: TokenPurpose, user_id: uuid.UUID, ttl: timedelta, **claims: Any) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "aud": purpose.value, "iat": now, "exp": now + ttl, **claims}
    return jwt.encode(payload, get_settings().secret_key.get_secret_value(), algorithm=ALGORITHM)


def _decode(token: str, purpose: TokenPurpose, *required: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            get_settings().secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=purpose.value,
            options={"require": ["sub", "aud", "iat", "exp", *required]},
        )
        claims["sub"] = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError(detail=f"{purpose}: {type(exc).__name__}: {exc}") from exc
    return claims


def create_session_token(user_id: uuid.UUID, password_hash: str) -> str:
    ttl = timedelta(days=get_settings().session_ttl_days)
    return _encode(
        TokenPurpose.SESSION,
        user_id,
        ttl,
        jti=uuid.uuid4().hex,
        pwd=password_fingerprint(password_hash),
    )


def decode_session_token(token: str) -> SessionClaims:
    claims = _decode(token, TokenPurpose.SESSION, "jti", "pwd")
    return SessionClaims(
        user_id=claims["sub"],
        session_id=str(claims["jti"]),
        password_fingerprint=str(claims["pwd"]),
        expires_at=datetime.fromtimestamp(claims["exp"], UTC),
    )


def create_email_verification_token(user_id: uuid.UUID, email: str) -> str:
    ttl = timedelta(hours=get_settings().email_verification_ttl_hours)
    return _encode(TokenPurpose.VERIFY_EMAIL, user_id, ttl, email=email)


def decode_email_verification_token(token: str) -> tuple[uuid.UUID, str]:
    """Devolve o usuário e o e-mail que o token confirma."""
    claims = _decode(token, TokenPurpose.VERIFY_EMAIL, "email")
    return claims["sub"], str(claims["email"])


def create_password_reset_token(user_id: uuid.UUID, password_hash: str) -> str:
    ttl = timedelta(minutes=get_settings().password_reset_ttl_minutes)
    return _encode(
        TokenPurpose.RESET_PASSWORD, user_id, ttl, pwd=password_fingerprint(password_hash)
    )


def decode_password_reset_token(token: str) -> tuple[uuid.UUID, str]:
    """Devolve o usuário e a impressão da senha que ele tinha quando o link foi pedido."""
    claims = _decode(token, TokenPurpose.RESET_PASSWORD, "pwd")
    return claims["sub"], str(claims["pwd"])


def fingerprint_matches(fingerprint: str, password_hash: str) -> bool:
    return hmac.compare_digest(fingerprint, password_fingerprint(password_hash))
