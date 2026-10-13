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

O serviço `migrate` roda `alembic upgrade head` e sai; a API e os workers só sobem depois dele.
Os imports são processados em segundo plano por dois workers [arq](https://arq-docs.helpmanual.io/):

- `worker`: fila padrão (metadados, legendas, Claude) e varredura de imports parados;
- `worker-whisper`: só a transcrição com faster-whisper, `WHISPER_MAX_JOBS` por vez (padrão 1). O
  modelo é carregado quando o worker inicia e fica no volume `hf-cache`.

## Rodando sem Docker

Suba só o banco e o Redis com `docker compose up db redis`, depois:

```bash
# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run arq app.worker.WorkerSettings --custom-log-dict app.worker.LOG_CONFIG          # outro terminal
uv run arq app.worker.WhisperWorkerSettings --custom-log-dict app.worker.LOG_CONFIG   # outro terminal

# frontend (Node 22+)
cd frontend
npm install
npm run dev
```

## API

| Método | Rota | |
|---|---|---|
| POST | `/imports` `{url}` | Valida o link e enfileira (202). Se a receita já existe (no livro ou de outro usuário), conclui na hora (200) |
| GET | `/imports/{id}` | `status` (`pending` → `fetching` → `transcribing` → `generating` → `done`/`failed`), `recipe_id`, `error` e `queue_position` |
| GET | `/recipes?q=&tag=&favorite=&limit=&cursor=` | Livro do usuário, mais recentes primeiro; `q` busca no título, ingredientes e tags, sem diferenciar acentos |
| GET | `/recipes/{id}` | Receita + vídeo (`youtube_id`, título, canal, thumbnail, duração) |
| PATCH | `/recipes/{id}` | Edita os campos enviados, `is_favorite`, `user_notes` e `rating` (1–5) |
| DELETE | `/recipes/{id}` | Remove do livro |
| POST | `/recipes/{id}/reset` | Volta à receita gerada para o vídeo (mantém favorito, notas e avaliação) |

Erros sempre no formato `{"error": {"code": "...", "message": "..."}}`; erros de validação trazem
também `details`.

**Usuário (temporário, até a fase 3):** com `ENVIRONMENT=development`, o usuário vem do header
`X-Dev-User-Id` (um UUID qualquer) e é criado na primeira requisição. Em outro ambiente as rotas
respondem 401.

```bash
curl -X POST localhost:8000/imports -H "X-Dev-User-Id: $(uuidgen)" \
  -H 'Content-Type: application/json' -d '{"url": "https://youtu.be/<id>"}'
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

Cada chamada paga ao Claude, com sucesso ou não, é gravada em `llm_calls` (modelo, `usage`, código
de erro): é a base do custo diário. Uma recusa, ou duas saídas inválidas, para o mesmo vídeo fazem
o pipeline parar de chamar o Claude para ele até `PROMPT_VERSION` mudar.

## Checagens

Os testes de banco usam um banco separado (`TEST_DATABASE_URL`, padrão
`postgresql+asyncpg://receita:receita@localhost:5432/receita_test`) e o db 15 do Redis
(`TEST_REDIS_URL`, padrão `redis://localhost:6379/15`), esvaziado a cada teste:

```bash
docker compose exec db createdb -U receita receita_test   # uma vez
```

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run format:check && npm run build
```
