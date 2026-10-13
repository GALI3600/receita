"""Healthchecks: `/health` (o processo responde) e `/health/ready` (banco e Redis acessíveis).

O `/health/ready` é o healthcheck do container da API e o que um monitor externo deve olhar
(`https://<domínio>/api/health/ready`): 503 com `checks` dizendo o que falhou.
"""

import asyncio
import logging
from collections.abc import Awaitable

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import RedisDep, SessionDep
from app.errors import ServiceUnavailableError

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

CHECK_TIMEOUT_S = 3


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _check(name: str, probe: Awaitable[object]) -> str:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            await probe
    except Exception as exc:
        logger.warning("readiness: %s indisponível: %r", name, exc)
        return "error"
    return "ok"


@router.get("/ready", responses={503: {"description": "Banco ou Redis indisponível"}})
async def ready(session: SessionDep, redis: RedisDep) -> JSONResponse:
    checks = {
        "database": await _check("banco", session.execute(text("SELECT 1"))),
        "redis": await _check("redis", redis.ping()),
    }
    if all(status == "ok" for status in checks.values()):
        return JSONResponse({"status": "ok", "checks": checks})
    error = ServiceUnavailableError()
    body = {"error": {"code": error.code, "message": error.message}, "checks": checks}
    return JSONResponse(jsonable_encoder(body), status_code=503)
