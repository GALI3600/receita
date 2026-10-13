# Receita

Cole o link de um vídeo de receita do YouTube e ganhe a receita escrita, salva no seu livro de receitas junto com o vídeo.

Plano completo do projeto: [`docs/PLANO.md`](docs/PLANO.md).

## Estrutura

- `backend/` — API em FastAPI (Python 3.12, gerenciada com [uv](https://docs.astral.sh/uv/))
- `frontend/` — site em React + TypeScript + Vite + Tailwind

## Rodando com Docker

```bash
cp backend/.env.example backend/.env   # preencha ANTHROPIC_API_KEY (e SECRET_KEY fora de development)
docker compose up --build
```

- Site: http://localhost:5173
- API: http://localhost:8000 (docs em http://localhost:8000/docs)

O serviço `migrate` roda `alembic upgrade head` e sai; a API e os workers só sobem depois dele.
Os imports são processados em segundo plano por dois workers [arq](https://arq-docs.helpmanual.io/):

- `worker`: fila padrão (metadados, legendas, Claude), varredura de imports parados e retomada dos
  imports adiados pelo orçamento;
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
| POST | `/auth/register` `{name, email, password}` | Cria a conta e manda o link de confirmação (202). Resposta igual se o e-mail já tem conta |
| POST | `/auth/verify` `{token}` | Confirma o e-mail (204) |
| POST | `/auth/resend-verification` | Reenvia o link de confirmação (logado); 429 depois de `RATE_LIMIT_VERIFICATION_EMAIL_PER_ADDRESS` e-mails para o endereço |
| POST | `/auth/login` `{email, password}` | Abre a sessão (cookie `receita_session`) e devolve o mesmo que `/auth/me` |
| POST | `/auth/logout` | Encerra a sessão (204) |
| POST | `/auth/forgot-password` `{email}` | Manda o link de redefinição se houver conta; sempre 200 |
| POST | `/auth/reset-password` `{token, password}` | Troca a senha (link de uso único) e encerra todas as sessões (204) |
| GET | `/auth/me` | Usuário + cota do dia (`quota.used`, `limit`, `remaining`, `resets_at`) |
| GET | `/account/export` | Todos os dados da conta em JSON (LGPD) |
| DELETE | `/account` `{password}` | Apaga a conta, as receitas e os imports (204). Os vídeos compartilhados ficam |
| POST | `/imports` `{url}` | Valida o link e enfileira (202). Se a receita já existe (no livro ou de outro usuário), conclui na hora (200). Exige e-mail confirmado |
| GET | `/imports/{id}` | `status` (`pending` → `fetching` → `transcribing` → `generating` → `done`/`failed`, ou `deferred`), `recipe_id`, `error` (o motivo da falha ou, em `deferred`, da espera) e `queue_position` |
| GET | `/recipes?q=&tag=&favorite=&limit=&cursor=` | Livro do usuário, mais recentes primeiro; `q` busca no título, ingredientes e tags, sem diferenciar acentos |
| GET | `/recipes/{id}` | Receita + vídeo (`youtube_id`, título, canal, thumbnail, duração) |
| PATCH | `/recipes/{id}` | Edita os campos enviados, `is_favorite`, `user_notes` e `rating` (1–5) |
| DELETE | `/recipes/{id}` | Remove do livro |
| POST | `/recipes/{id}/reset` | Volta à receita gerada para o vídeo (mantém favorito, notas e avaliação) |

Erros sempre no formato `{"error": {"code": "...", "message": "..."}}`; erros de validação trazem
também `details`.

### Sessão e segurança

- **Sessão:** JWT (HS256, `SECRET_KEY`) num cookie `httpOnly`, `SameSite=Lax`, `Secure` fora de
  development, válido por `SESSION_TTL_DAYS`. Sair grava a sessão como revogada no Redis; trocar a
  senha derruba todas as sessões. Senhas com argon2.
- **CSRF:** todo `POST`/`PATCH`/`PUT`/`DELETE` precisa do header `X-Requested-With` (qualquer
  valor); se o pedido tiver `Origin`, ela precisa estar em `CORS_ORIGINS`. Sem isso: 403
  `csrf_failed`.
- **E-mail:** com `EMAIL_BACKEND=console` (padrão em development) o e-mail, com o link, aparece no
  log da API (`docker compose logs api`); `smtp` envia de verdade. Os links apontam para
  `FRONTEND_URL` (`/verificar-email?token=...`, `/redefinir-senha?token=...`).
- **Captcha:** com `TURNSTILE_SECRET_KEY`, o cadastro exige o token do Cloudflare Turnstile em
  `cf-turnstile-response`.

### Limites

- **Rate limit por IP** (Redis, janela fixa) em cadastro, login, "esqueci a senha", reenvio do
  link e `POST /imports`: 429 `rate_limited` com `Retry-After`. Valores em `RATE_LIMIT_*`; o
  `X-Forwarded-For` só vale com `TRUST_PROXY_HEADERS=true`. IPv6 conta pela rede /64; um IPv4
  escrito como IPv6 (`::ffff:a.b.c.d`, 6to4) conta como o próprio IPv4.
- **E-mails de confirmação por endereço:** cadastro e reenvios somam no máximo
  `RATE_LIMIT_VERIFICATION_EMAIL_PER_ADDRESS` (padrão 5/dia) para o mesmo e-mail, venham de que IP
  vierem. Enquanto o e-mail não é confirmado, as mensagens não trazem o nome cadastrado.
- **Cota por usuário:** `DAILY_IMPORT_LIMIT` receitas novas por dia UTC (padrão 10). Só conta o
  import que chamou o Claude e terminou `done`; cópias e falhas não contam. Imports em andamento
  ocupam a vaga enquanto não terminam. Estourou: 429 `quota_exceeded` com `Retry-After`.
- **Falhas caras por usuário:** imports que falharam depois de uma chamada paga ao Claude ou de
  mandar o vídeo para o whisper (ex.: vídeo que não é receita) não gastam a cota, mas têm limite
  próprio, `DAILY_FAILED_IMPORT_LIMIT` por dia UTC (padrão 20). Estourou: 429
  `too_many_failed_imports` com `Retry-After`; cópias continuam liberadas.
- **Orçamento global:** quando o gasto do dia com o Claude (calculado do `usage` de cada chamada)
  chega a `DAILY_LLM_BUDGET_USD`, vídeos novos ficam `deferred` (com `error.code`
  `llm_budget_exceeded` explicando a espera) e voltam para a fila às 00:05 UTC (cron do worker,
  sempre em UTC). Cópias continuam funcionando.

```bash
# cadastro → link no log → confirmação → login → import
curl -X POST localhost:8000/auth/register -H 'X-Requested-With: curl' \
  -H 'Content-Type: application/json' -d '{"name": "Ana", "email": "ana@example.com", "password": "uma-senha-boa"}'
docker compose logs api | grep verificar-email
curl -X POST localhost:8000/auth/verify -H 'X-Requested-With: curl' \
  -H 'Content-Type: application/json' -d '{"token": "<token do link>"}'
curl -c cookies.txt -X POST localhost:8000/auth/login -H 'X-Requested-With: curl' \
  -H 'Content-Type: application/json' -d '{"email": "ana@example.com", "password": "uma-senha-boa"}'
curl -b cookies.txt -X POST localhost:8000/imports -H 'X-Requested-With: curl' \
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
