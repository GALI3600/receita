import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, Header, Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.errors import UnauthorizedError
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> ArqRedis:
    return request.app.state.redis


RedisDep = Annotated[ArqRedis, Depends(get_redis)]

DEV_USER_HEADER = "X-Dev-User-Id"


async def get_current_user(
    session: SessionDep,
    dev_user_id: Annotated[str | None, Header(alias=DEV_USER_HEADER)] = None,
) -> User:
    """TEMPORÁRIO (até a fase 3, com login de verdade).

    Só em `ENVIRONMENT=development`: o usuário vem do header `X-Dev-User-Id` (um UUID) e é
    criado na primeira requisição. Em qualquer outro ambiente toda rota autenticada dá 401.
    """
    if get_settings().environment != "development" or not dev_user_id:
        raise UnauthorizedError()
    try:
        user_id = uuid.UUID(dev_user_id)
    except ValueError as exc:
        raise UnauthorizedError(detail=f"{DEV_USER_HEADER} inválido") from exc

    user = await session.get(User, user_id)
    if user is None:
        await session.execute(
            insert(User)
            .values(
                id=user_id,
                email=f"dev-{user_id}@receita.local",
                password_hash="!",
                name="Dev",
            )
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        await session.commit()
        user = await session.get(User, user_id)
        assert user is not None
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
