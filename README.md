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

## Checagens

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run format:check && npm run build
```
