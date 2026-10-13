# syntax=docker/dockerfile:1

# Dois alvos finais a partir de um build comum:
#   dev   — docker-compose.yml (root, código montado por bind mount, --reload no compose);
#   prod  — docker-compose.prod.yml (o padrão: usuário sem privilégios, sem --reload, healthcheck).

# --- build: dependências num venv (uv), sem as de desenvolvimento ------------------------------
FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .
# O checkout no Windows (/mnt/c) chega com 777: ninguém além do root escreve no código.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && chmod -R go-w /app

# --- runtime: o que os dois alvos têm em comum ------------------------------------------------
FROM python:3.12-slim AS runtime

# ffmpeg: usado pelo yt-dlp para juntar/converter mídia quando necessário. O deno (runtime JS
# que o yt-dlp usa para os desafios do YouTube) vem no venv, pelo extra yt-dlp[deno].
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=build /app /app
EXPOSE 8000

# --- dev --------------------------------------------------------------------------------------
FROM runtime AS dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- prod (padrão) ----------------------------------------------------------------------------
FROM runtime AS prod

# O código fica do root e só para leitura; o usuário "app" escreve só no HOME (cache do modelo
# do whisper, do yt-dlp e do deno) e em /tmp (áudio temporário).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app \
    && mkdir -p /home/app/.cache/huggingface \
    && chown -R app:app /home/app/.cache
ENV HOME=/home/app HF_HOME=/home/app/.cache/huggingface
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
