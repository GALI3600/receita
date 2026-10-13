# Receita

Cole o link de um vídeo de receita do YouTube e ganhe a receita escrita, salva no seu livro de receitas junto com o vídeo.

Plano completo do projeto: [`docs/PLANO.md`](docs/PLANO.md).

## Estrutura

- `backend/` — API em FastAPI (Python 3.12, gerenciada com [uv](https://docs.astral.sh/uv/))
- `frontend/` — site em React + TypeScript + Vite + Tailwind

## Rodando com Docker

```bash
cp backend/.env.example backend/.env   # preencha ANTHROPIC_API_KEY
docker compose up --build
```

- Site: http://localhost:5173
- API: http://localhost:8000 (docs em http://localhost:8000/docs)

## Rodando sem Docker

Suba só o banco e o Redis com `docker compose up db redis`, depois:

```bash
# backend
cd backend
uv sync
uv run uvicorn app.main:app --reload

# frontend (Node 22+)
cd frontend
npm install
npm run dev
```

## Pipeline pela linha de comando

Transforma um link em receita e salva o `Video` no banco (precisa do banco migrado):

```bash
cd backend
uv run alembic upgrade head
uv run python -m app.cli import "https://youtu.be/<id>"             # completo (precisa de ANTHROPIC_API_KEY)
uv run python -m app.cli import "https://youtu.be/<id>" --skip-llm  # só metadados + transcrição
uv run python -m app.cli import "https://youtu.be/<id>" --json -v   # Video completo em JSON, com logs
```

Ou dentro do container: `docker compose run --rm api python -m app.cli import <url>`.

A transcrição usa a legenda manual (pt, depois en), depois a automática e, sem legenda, o
faster-whisper local (`WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE` no `.env`; o modelo
é baixado do Hugging Face no primeiro uso). Vídeos com mais de `MAX_VIDEO_DURATION_MIN` minutos são
recusados.

## Checagens

Os testes de banco usam um banco separado (`TEST_DATABASE_URL`, padrão
`postgresql+asyncpg://receita:receita@localhost:5432/receita_test`):

```bash
docker compose exec db createdb -U receita receita_test   # uma vez
```

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run format:check && npm run build
```
