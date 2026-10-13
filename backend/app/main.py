from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import queue
from app.api import imports, recipes
from app.api.errors import register_error_handlers
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = await create_pool(queue.redis_settings())
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(title="Receita API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(imports.router)
app.include_router(recipes.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
