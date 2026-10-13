import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import queue
from app.api import account, auth, imports, recipes
from app.api.deps import csrf_protect
from app.api.errors import register_error_handlers
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Logs do app (INFO) no stderr, como no worker: o uvicorn só configura os loggers dele."""
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    if settings.is_development:
        logger.warning(
            "ENVIRONMENT=development: cookie de sessão sem Secure e e-mails via %s",
            settings.email_backend,
        )
    elif settings.email_backend == "console":
        logger.warning("EMAIL_BACKEND=console fora de development: os e-mails só vão para o log")
    app.state.redis = await create_pool(queue.redis_settings())
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(
    title="Receita API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(csrf_protect)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(imports.router)
app.include_router(recipes.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
