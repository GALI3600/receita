"""Formato único de erro da API: `{"error": {"code", "message"}}`."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError, ErrorCode, InternalError
from app.schemas.errors import ErrorBody, ErrorResponse, FieldError

logger = logging.getLogger(__name__)

_HTTP_ERRORS: dict[int, tuple[ErrorCode, str]] = {
    401: (ErrorCode.UNAUTHORIZED, "Entre na sua conta para continuar."),
    404: (ErrorCode.NOT_FOUND, "Não encontramos o que você procurou."),
    405: (ErrorCode.NOT_FOUND, "Essa operação não existe aqui."),
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body, exclude_none=True),
        headers=headers,
    )


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status_code >= 500:
        logger.error("%s %s: %r", request.method, request.url.path, exc)
    return error_response(exc.status_code, exc.code, exc.message, headers=exc.headers or None)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        FieldError(
            field=".".join(str(part) for part in error["loc"]),
            type=error["type"],
            message=error["msg"],
        )
        for error in exc.errors()
    ]
    return error_response(
        422, ErrorCode.VALIDATION_ERROR, "Alguns dados enviados são inválidos.", details
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code, message = _HTTP_ERRORS.get(
        exc.status_code, (ErrorCode.INTERNAL_ERROR, "Não foi possível atender o pedido.")
    )
    return error_response(exc.status_code, code, message)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("erro inesperado em %s %s", request.method, request.url.path)
    error = InternalError()
    return error_response(500, error.code, error.message)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
