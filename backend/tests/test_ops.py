"""Operação: healthchecks, serialização dos jobs em JSON e logs estruturados."""

import json
import logging
import sys
import uuid
from typing import Any

import pytest
from arq.connections import ArqRedis
from arq.constants import job_key_prefix
from arq.jobs import SerializationError
from arq.logs import default_log_config
from arq.worker import create_worker, func
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app import logs, queue, worker
from app.config import Settings
from app.main import app as fastapi_app

# --- Healthchecks -------------------------------------------------------------------------------


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_checks_database_and_redis(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_ready_reports_what_is_down(
    client: AsyncClient, redis: ArqRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ping() -> None:
        raise RedisConnectionError("fora do ar")

    monkeypatch.setattr(redis, "ping", ping)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert body["checks"] == {"database": "ok", "redis": "error"}


# --- Jobs em JSON -------------------------------------------------------------------------------


async def test_jobs_are_stored_as_json(redis: ArqRedis) -> None:
    import_id = uuid.uuid4()

    assert await queue.enqueue_import(redis, import_id)
    assert await queue.enqueue_whisper(redis, "abcdefghijk", None)

    raw = await redis.get(job_key_prefix + queue.import_job_id(import_id))
    job = json.loads(raw)
    assert job["f"] == queue.PROCESS_IMPORT
    assert job["a"] == [str(import_id)]
    whisper = json.loads(await redis.get(job_key_prefix + queue.whisper_job_id("abcdefghijk")))
    assert whisper["a"] == ["abcdefghijk", None]


async def test_non_json_job_arguments_are_refused(redis: ArqRedis) -> None:
    with pytest.raises(SerializationError):
        await redis.enqueue_job(queue.PROCESS_IMPORT, uuid.uuid4(), _job_id="x")


def test_workers_use_the_json_serializer() -> None:
    for settings in (worker.WorkerSettings, worker.WhisperWorkerSettings):
        arq_worker = create_worker(settings, handle_signals=False)
        assert arq_worker.job_serializer is queue.job_serializer
        assert arq_worker.job_deserializer is queue.job_deserializer
        assert arq_worker.health_check_interval == worker.HEALTH_CHECK_INTERVAL_S


async def test_worker_runs_a_json_job(redis: ArqRedis) -> None:
    """Ponta a ponta: enfileirado pela API (JSON), executado pelo worker (JSON)."""
    received: list[Any] = []

    async def echo(ctx: dict[str, Any], *args: Any) -> str:
        received.extend(args)
        return "ok"

    await redis.enqueue_job("echo", "texto", 3, None, _job_id="echo:1")
    arq_worker = create_worker(
        worker.WorkerSettings,
        redis_pool=redis,
        functions=[func(echo, name="echo")],
        burst=True,
        poll_delay=0,
        handle_signals=False,
        on_startup=None,
        on_shutdown=None,
        cron_jobs=[],
    )

    await arq_worker.async_run()

    assert arq_worker.jobs_complete == 1
    assert received == ["texto", 3, None]


def test_failed_job_result_with_exception_is_serializable() -> None:
    data = {"r": ValueError("falhou"), "s": False}

    assert json.loads(queue.job_serializer(data))["r"] == "ValueError('falhou')"


# --- Logs ---------------------------------------------------------------------------------------


def test_json_formatter_includes_extra_fields_and_exception() -> None:
    record = logging.LogRecord("app.x", logging.ERROR, __file__, 1, "falhou %s", ("agora",), None)
    record.status = 500
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record.exc_info = sys.exc_info()

    payload = json.loads(logs.JsonFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert payload["logger"] == "app.x"
    assert payload["msg"] == "falhou agora"
    assert payload["status"] == 500
    assert "RuntimeError: boom" in payload["exc"]
    assert payload["ts"].endswith("+00:00")


def test_worker_log_config_follows_log_format(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_format", "json")
    config = logs.worker_log_config(default_log_config(verbose=False))
    assert config["formatters"]["arq.standard"] == {"()": logs.JsonFormatter}
    assert config["loggers"]["app"]["level"] == "INFO"

    monkeypatch.setattr(settings, "log_format", "text")
    config = logs.worker_log_config(default_log_config(verbose=False))
    assert config["formatters"]["arq.standard"]["format"] == logs.TEXT_FORMAT


async def test_access_log(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)

    async def page(request: Any) -> PlainTextResponse:
        return PlainTextResponse("ok", status_code=201)

    inner = Starlette(routes=[Route("/x", page), Route("/health", page)])
    app = logs.AccessLogMiddleware(inner)
    logs.access_logger.propagate = True
    caplog.set_level(logging.INFO, logger="app.access")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        await http.get("/x?q=segredo", headers={"X-Forwarded-For": "203.0.113.9"})
        await http.get("/health")

    [record] = [r for r in caplog.records if r.name == "app.access"]
    assert record.getMessage() == "GET /x 201"
    assert record.path == "/x"
    assert record.status == 201
    assert record.client_ip == "203.0.113.9"
    assert record.duration_ms >= 0
    assert "segredo" not in json.dumps(logs.JsonFormatter().format(record))


def test_docs_follow_environment() -> None:
    # Os testes rodam em development: a documentação existe; em produção, os três ficam None.
    assert fastapi_app.docs_url == "/docs"
    assert fastapi_app.openapi_url == "/openapi.json"
