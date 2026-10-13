"""Logs da API e dos workers: texto (desenvolvimento) ou JSON, uma linha por evento (produção).

Com `LOG_FORMAT=json`, cada linha é um objeto com `ts`, `level`, `logger` e `msg`, mais `exc`
quando há exceção e os campos passados em `extra=` (ex.: o log de acesso da API). Assim o
`docker compose logs` continua legível e qualquer coletor (Loki, Vector, jq) separa os campos.
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request

from app.config import get_settings
from app.services.rate_limit import client_ip

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Atributos que todo LogRecord tem; o resto veio de `extra=` e vai para o JSON.
_RECORD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def make_formatter() -> logging.Formatter:
    if get_settings().log_format == "json":
        return JsonFormatter()
    return logging.Formatter(TEXT_FORMAT)


def configure_api_logging() -> None:
    """Logs do app (INFO) no stderr; em JSON, também os do uvicorn (que ele já configurou)."""
    formatter = make_formatter()
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)
        app_logger.propagate = False
    for handler in app_logger.handlers:
        handler.setFormatter(formatter)
    if isinstance(formatter, JsonFormatter):
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            for handler in logging.getLogger(name).handlers:
                handler.setFormatter(formatter)


def worker_log_config(base: dict[str, Any]) -> dict[str, Any]:
    """O `default_log_config` do arq com o formato do app e o logger `app` em INFO."""
    if get_settings().log_format == "json":
        base["formatters"]["arq.standard"] = {"()": JsonFormatter}
    else:
        base["formatters"]["arq.standard"]["format"] = TEXT_FORMAT
    base["loggers"]["app"] = {"handlers": ["arq.standard"], "level": "INFO"}
    return base


# --- Log de acesso ------------------------------------------------------------------------------

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

access_logger = logging.getLogger("app.access")


class AccessLogMiddleware:
    """Uma linha por pedido HTTP: método, caminho (sem a query), status, duração e IP.

    Fica no lugar do log de acesso do uvicorn (`--no-access-log`) em produção: o IP é o mesmo
    que o rate limit usa (atrás do Caddy, o do cliente) e a query string, que pode ter texto de
    busca, não vai para o log.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Os healthchecks do Docker batem em /health a cada poucos segundos: só as falhas.
            if status >= 400 or not scope["path"].startswith("/health"):
                _log_access(scope, status, start)


def _log_access(scope: Scope, status: int, start: float) -> None:
    access_logger.info(
        "%s %s %d",
        scope["method"],
        scope["path"],
        status,
        extra={
            "method": scope["method"],
            "path": scope["path"],
            "status": status,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            "client_ip": client_ip(Request(scope)),
        },
    )
