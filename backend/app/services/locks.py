"""Lock no Redis por vídeo: um único job por vez busca, transcreve legendas e chama o Claude.

Imports simultâneos do mesmo vídeo esperam o lock e, quando o primeiro termina, encontram a
receita pronta e só copiam. O lock expira sozinho (`ttl_s`), então um worker que morre no meio
não trava o vídeo para sempre.
"""

import uuid

from redis.asyncio import Redis

# Apaga só se o lock ainda for nosso: depois de expirar ele pode ter sido pego por outro job.
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class VideoLock:
    def __init__(self, redis: Redis, youtube_id: str, ttl_s: float) -> None:
        self.redis = redis
        self.key = f"receita:lock:video:{youtube_id}"
        self.ttl_ms = int(ttl_s * 1000)
        self.token = uuid.uuid4().hex

    async def acquire(self) -> bool:
        return bool(await self.redis.set(self.key, self.token, nx=True, px=self.ttl_ms))

    async def release(self) -> None:
        await self.redis.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
