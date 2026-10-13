"""Rate limit por IP no Redis, com janela fixa.

Cada ação (cadastro, login, ...) tem um contador por IP e por janela: a chave inclui o número
da janela e expira junto com ela. Se o Redis cair, o pedido passa (com um aviso no log): o
limite protege contra abuso, não pode derrubar o login.
"""

import ipaddress
import logging
import math
import time

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import RateLimit, get_settings
from app.errors import RateLimitedError

logger = logging.getLogger(__name__)

KEY_PREFIX = "receita:rate"
# Um cliente IPv6 costuma ter um /64 inteiro: limitar por endereço seria trivial de contornar.
IPV6_PREFIX = 64


def client_ip(request: Request) -> str:
    """IP do cliente; com `TRUST_PROXY_HEADERS`, o último do X-Forwarded-For.

    O último endereço é o que o proxy reverso acrescentou (o IP que se conectou a ele). Os
    anteriores vêm do próprio cliente e podem ser forjados.
    """
    host = request.client.host if request.client else ""
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        candidates = [part.strip() for part in forwarded.split(",") if part.strip()]
        if candidates:
            host = candidates[-1]
    return host


def ip_bucket(ip: str) -> str:
    """Chave do limite para um IP: o próprio IPv4 ou a rede /64 do IPv6."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip or "desconhecido"
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/{IPV6_PREFIX}", strict=False))
    return str(address)


async def check_ip(redis: Redis, request: Request, action: str, limit: RateLimit) -> None:
    await hit(redis, action, ip_bucket(client_ip(request)), limit)


async def _count(redis: Redis, action: str, key: str, limit: RateLimit) -> tuple[int, int] | None:
    """Conta um pedido e devolve (pedidos na janela, segundos até ela acabar); None sem Redis."""
    now = time.time()
    window = int(now // limit.window_s)
    redis_key = f"{KEY_PREFIX}:{action}:{key}:{window}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, limit.window_s, nx=True)
            count, _ = await pipe.execute()
    except (RedisError, OSError) as exc:
        logger.warning("rate limit de %s indisponível: %r", action, exc)
        return None
    return count, math.ceil((window + 1) * limit.window_s - now)


async def hit(redis: Redis, action: str, key: str, limit: RateLimit) -> None:
    """Conta um pedido; levanta `RateLimitedError` (com Retry-After) acima do limite."""
    counted = await _count(redis, action, key, limit)
    if counted is not None and counted[0] > limit.requests:
        count, retry_after = counted
        raise RateLimitedError(retry_after, detail=f"{action} {key}: {count}/{limit.requests}")


async def allow(redis: Redis, action: str, key: str, limit: RateLimit) -> bool:
    """Como `hit`, mas só responde se ainda está dentro do limite (para limitar sem avisar)."""
    counted = await _count(redis, action, key, limit)
    return counted is None or counted[0] <= limit.requests
