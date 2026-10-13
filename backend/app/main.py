import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import logs, queue
from app.api import account, auth, health, imports, recipes
from app.api.deps import csrf_protect
from app.api.errors import register_error_handlers
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logs.configure_api_logging()
    if settings.is_development:
        logger.warning(
            "ENVIRONMENT=development: cookie de sessão sem Secure e e-mails via %s",
            settings.email_backend,
        )
    elif settings.email_backend == "console":
        logger.warning("EMAIL_BACKEND=console fora de development: os e-mails só vão para o log")
    app.state.redis = await queue.create_redis_pool()
    try:
        yield
    finally:
        await app.state.redis.aclose()


# A documentação interativa (/docs, /redoc, /openapi.json) só em development: em produção ela
# só mostraria a superfície da API (e o Swagger UI viria de um CDN barrado pela CSP).
_docs = settings.is_development
app = FastAPI(
    title="Receita API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(csrf_protect)],
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.access_log:
    app.add_middleware(logs.AccessLogMiddleware)
register_error_handlers(app)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(imports.router)
app.include_router(recipes.router)
