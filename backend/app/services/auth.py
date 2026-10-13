"""Contas: cadastro, login, sessões, verificação de e-mail, troca de senha e exclusão.

A sessão é um JWT em cookie httpOnly (ver `security`). Sair da conta grava o id da sessão numa
lista de revogadas no Redis até o token expirar; trocar a senha invalida todas as sessões de
uma vez, porque o token guarda a impressão do hash da senha.
"""

import logging
import math
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import (
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidTokenError,
    UnauthorizedError,
)
from app.models import User
from app.services import security

logger = logging.getLogger(__name__)

REVOKED_SESSION_PREFIX = "receita:session-revoked:"


# --- Sessões ----------------------------------------------------------------------------------


async def revoke_session(redis: Redis, claims: security.SessionClaims) -> None:
    ttl_s = math.ceil((claims.expires_at - datetime.now(UTC)).total_seconds())
    if ttl_s <= 0:
        return
    try:
        await redis.set(f"{REVOKED_SESSION_PREFIX}{claims.session_id}", "1", ex=ttl_s)
    except (RedisError, OSError) as exc:
        logger.warning("não foi possível revogar a sessão %s: %r", claims.session_id, exc)


async def _is_revoked(redis: Redis, session_id: str) -> bool:
    # Sem Redis, a sessão vale: a lista só guarda quem saiu, e o cookie já foi apagado do
    # navegador nesse caso. Derrubar todo login por uma queda do Redis seria pior.
    try:
        return bool(await redis.exists(f"{REVOKED_SESSION_PREFIX}{session_id}"))
    except (RedisError, OSError) as exc:
        logger.warning("lista de sessões revogadas indisponível: %r", exc)
        return False


async def user_for_session(
    session: AsyncSession, redis: Redis, claims: security.SessionClaims
) -> User:
    if await _is_revoked(redis, claims.session_id):
        raise UnauthorizedError(detail="sessão encerrada")
    user = await session.get(User, claims.user_id)
    if user is None:
        raise UnauthorizedError(detail="usuário não existe mais")
    if not security.fingerprint_matches(claims.password_fingerprint, user.password_hash):
        raise UnauthorizedError(detail="a senha mudou depois do login")
    return user


# --- Cadastro e login -------------------------------------------------------------------------


async def find_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def register(
    session: AsyncSession, *, name: str, email: str, password: str
) -> tuple[User, bool]:
    """Cria a conta; se o e-mail já tem conta, devolve ela e `False` (nada muda nela).

    O hash é calculado nos dois casos: o tempo de resposta não pode revelar se o e-mail existe.
    """
    password_hash = await security.hash_password(password)
    existing = await find_by_email(session, email)
    if existing is not None:
        await session.commit()
        return existing, False

    user = User(email=email, name=name, password_hash=password_hash)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Outro cadastro com o mesmo e-mail ganhou a corrida.
        await session.rollback()
        existing = await find_by_email(session, email)
        if existing is None:
            raise
        await session.commit()
        return existing, False
    return user, True


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    user = await find_by_email(session, email)
    await session.commit()
    if user is None:
        await security.burn_password_check(password)
        raise InvalidCredentialsError(detail="e-mail sem conta")
    if not await security.verify_password(password, user.password_hash):
        raise InvalidCredentialsError(detail="senha errada")
    return user


async def check_password(user: User, password: str) -> None:
    if not await security.verify_password(password, user.password_hash):
        raise InvalidPasswordError()


# --- Links por e-mail -------------------------------------------------------------------------


async def _user_or_invalid_token(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise InvalidTokenError(detail="usuário não existe mais")
    return user


async def verify_email(session: AsyncSession, token: str) -> User:
    """Confirma o e-mail do token. Usar o mesmo link de novo não é erro."""
    user_id, email = security.decode_email_verification_token(token)
    user = await _user_or_invalid_token(session, user_id)
    if user.email != email:
        raise InvalidTokenError(detail="o e-mail da conta mudou depois do envio do link")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await session.commit()
    return user


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    """Troca a senha com o link de reset, que vale uma vez só.

    O token guarda a impressão da senha de quando foi pedido. A troca só acontece se o hash
    ainda for o mesmo (compare-and-swap no UPDATE), então dois usos simultâneos do mesmo link
    não passam os dois. A nova senha derruba todas as sessões abertas e, como o link chegou
    pelo e-mail, também confirma o e-mail.
    """
    user_id, fingerprint = security.decode_password_reset_token(token)
    user = await _user_or_invalid_token(session, user_id)
    old_hash = user.password_hash
    await session.commit()
    if not security.fingerprint_matches(fingerprint, old_hash):
        raise InvalidTokenError(detail="link de reset já usado ou senha trocada depois")

    new_hash = await security.hash_password(new_password)
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.password_hash == old_hash)
        .values(
            password_hash=new_hash,
            email_verified_at=func.coalesce(User.email_verified_at, func.now()),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise InvalidTokenError(detail="link de reset usado por outro pedido ao mesmo tempo")
    await session.commit()


# --- Conta (LGPD) -----------------------------------------------------------------------------


async def delete_account(session: AsyncSession, user: User) -> None:
    """Apaga o usuário; receitas e imports vão junto (ON DELETE CASCADE). Vídeos ficam."""
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()
