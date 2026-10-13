"""Filas do arq: nomes, conexão com o Redis e enfileiramento dos jobs de import.

Duas filas: a padrão (metadados, legendas, Claude) e a do whisper, atendida por um worker com
concorrência baixa para que transcrições pesadas não travem os imports que têm legenda.
Os ids dos jobs são determinísticos: o arq não enfileira de novo um id que já está na fila ou
rodando, o que evita jobs duplicados para o mesmo import ou para o mesmo vídeo.
"""

import uuid

from arq.connections import ArqRedis, RedisSettings
from arq.constants import default_queue_name, in_progress_key_prefix, job_key_prefix

from app.config import get_settings

DEFAULT_QUEUE = default_queue_name
WHISPER_QUEUE = "arq:queue:whisper"

PROCESS_IMPORT = "process_import"
TRANSCRIBE_WHISPER = "transcribe_whisper"


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


def import_job_id(import_id: uuid.UUID) -> str:
    return f"import:{import_id}"


def resume_job_id(import_id: uuid.UUID) -> str:
    return f"import:{import_id}:resume"


def whisper_job_id(youtube_id: str) -> str:
    return f"whisper:{youtube_id}"


async def enqueue_import(redis: ArqRedis, import_id: uuid.UUID) -> bool:
    """Enfileira o processamento do import; False se ele já está na fila ou rodando."""
    job = await redis.enqueue_job(
        PROCESS_IMPORT,
        str(import_id),
        _job_id=import_job_id(import_id),
        _queue_name=DEFAULT_QUEUE,
    )
    return job is not None


async def resume_import(redis: ArqRedis, import_id: uuid.UUID) -> bool:
    """Põe de volta na fila um import que esperava o whisper; False se não conseguiu.

    O arq recusa um id enquanto o job anterior não foi finalizado. Se o job do import ainda está
    rodando, ele pode ter lido o vídeo antes de a transcrição ser gravada e estar saindo com
    "aguardando whisper": a retomada vai então com outro id. Se o job só está na fila, nada a
    fazer, porque quando rodar ele já encontra a transcrição.
    """
    if await enqueue_import(redis, import_id):
        return True
    if not await redis.exists(in_progress_key_prefix + import_job_id(import_id)):
        return True
    job = await redis.enqueue_job(
        PROCESS_IMPORT,
        str(import_id),
        _job_id=resume_job_id(import_id),
        _queue_name=DEFAULT_QUEUE,
    )
    return job is not None


async def enqueue_whisper(redis: ArqRedis, youtube_id: str, language: str | None) -> bool:
    job = await redis.enqueue_job(
        TRANSCRIBE_WHISPER,
        youtube_id,
        language,
        _job_id=whisper_job_id(youtube_id),
        _queue_name=WHISPER_QUEUE,
    )
    return job is not None


async def job_exists(redis: ArqRedis, job_id: str) -> bool:
    return bool(await redis.exists(job_key_prefix + job_id))


async def queue_position(redis: ArqRedis, queue_name: str, job_id: str) -> int | None:
    """Posição aproximada (1 = próximo) do job na fila; None se já está rodando ou não existe.

    Os jobs em execução continuam no sorted set do arq até terminarem, então entram na conta.
    """
    if await redis.exists(in_progress_key_prefix + job_id):
        return None
    rank = await redis.zrank(queue_name, job_id)
    return None if rank is None else rank + 1
