# Deploy — VPS com Docker Compose

Este guia põe o Receita no ar numa VPS com o `docker-compose.prod.yml`: um só servidor roda o
proxy com HTTPS, o site, a API, os workers, o Postgres e o Redis.

```
Internet ──443/80──▶ caddy ─┬─ /         → build estático do frontend (/srv)
                            └─ /api/*    → api:8000 (sem o prefixo /api)
                                             │
                     worker ◀── Redis (fila arq, rate limit, sessões) ──▶ worker-whisper
                        │                                                   │
                        └──────────────── Postgres ◀────────────────────────┘
```

| Serviço | Imagem | O que faz |
|---|---|---|
| `caddy` | `receita-web` (Caddy 2 + `frontend/dist`) | HTTPS automático (Let's Encrypt), SPA, proxy de `/api`, headers de segurança |
| `api` | `receita-backend` (alvo `prod`) | FastAPI no uvicorn, `API_WORKERS` processos, sem `--reload` |
| `migrate` | `receita-backend` | `alembic upgrade head` e sai; API e workers esperam por ele |
| `worker` | `receita-backend` | fila padrão do arq: metadados (yt-dlp), legendas, Claude |
| `worker-whisper` | `receita-backend` | fila do whisper (faster-whisper em CPU) |
| `db` | `postgres:17-alpine` | banco, sem porta publicada |
| `redis` | `redis:8-alpine` | com senha (`requirepass`) e AOF, sem porta publicada |

Só o Caddy publica portas. A imagem do backend roda como usuário sem privilégios (uid 10001),
com o código só para leitura, `cap_drop: ALL` e `no-new-privileges`. Todos os serviços têm
healthcheck, `restart: unless-stopped`, limite de memória e rotação de logs (json-file,
5 × 10 MB por container).

## 1. Requisitos da VPS

| | Mínimo | Recomendado |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU (o whisper usa todos os núcleos enquanto transcreve) |
| RAM | 4 GB | 8 GB |
| Disco | 30 GB SSD | 60 GB SSD |
| Sistema | Linux x86_64 com Docker Engine 24+ e o plugin Compose v2 | Ubuntu 24.04 LTS / Debian 12 |

De onde vêm esses números:

- **whisper `small` em int8 (CPU):** ~1–2 GB de RAM por transcrição (o limite do container é 3 GB)
  e, em 4 vCPU, algo entre 1/4 e 1/2 da duração do vídeo (um vídeo de 12 min leva uns 3–6 min).
  Com 2 vCPU, conte com quase a duração do vídeo. Só os vídeos **sem legenda** passam pelo
  whisper; os outros usam a legenda do YouTube e levam segundos.
- **Resto do stack:** API (2 processos) ~300 MB, worker ~300 MB, Postgres ~200 MB, Redis e
  Caddy ~50 MB cada.
- **Disco:** imagens ~2 GB, modelo do whisper ~500 MB (volume `hf-cache`), banco pequeno (texto),
  backups (`BACKUP_KEEP_DAYS` dias) e logs (no máximo ~50 MB por container). O áudio baixado
  para o whisper é apagado logo depois da transcrição.
- **Rede:** portas 80 e 443 (TCP) e 443 (UDP, HTTP/3) abertas; saída liberada para o YouTube,
  a API da Anthropic, o servidor SMTP, o Hugging Face (download do modelo) e o Let's Encrypt.

> **IP de datacenter e o YouTube:** alguns provedores têm faixas de IP que o YouTube barra como
> robô (o yt-dlp falha com "Sign in to confirm you're not a bot"). Veja a seção
> [Troubleshooting](#yt-dlp-bloqueado-sign-in-to-confirm-youre-not-a-bot).

## 2. DNS

Crie, no provedor do domínio, os registros apontando para o IP da VPS:

```
receita.example.com.   A      203.0.113.10
receita.example.com.   AAAA   2001:db8::10      # se a VPS tiver IPv6
```

Espere o DNS propagar (`dig +short receita.example.com`) **antes** de subir o stack: o Caddy
pede o certificado na primeira subida e o Let's Encrypt precisa achar a VPS pelo nome.

**Cloudflare:** com a nuvem cinza (só DNS), nada muda. Com a laranja (proxy), use o modo SSL
"Full (strict)" e descomente o bloco `servers { trusted_proxies ... }` no `deploy/Caddyfile`
(veja [IP do cliente e rate limit](#ip-do-cliente-e-rate-limit)).

## 3. Primeira instalação

```bash
# 1. Docker (https://docs.docker.com/engine/install/) e um usuário para o deploy
sudo usermod -aG docker "$USER"   # saia e entre de novo na sessão

# 2. Código
sudo mkdir -p /opt/receita && sudo chown "$USER" /opt/receita
git clone <url-do-repositório> /opt/receita
cd /opt/receita

# 3. Configuração
cp .env.production.example .env.production
chmod 600 .env.production
openssl rand -hex 32   # rode três vezes: POSTGRES_PASSWORD, REDIS_PASSWORD e SECRET_KEY
nano .env.production
```

No `.env.production`, preencha pelo menos:

| Variável | O quê |
|---|---|
| `DOMAIN`, `ACME_EMAIL` | domínio do site e e-mail para o Let's Encrypt |
| `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY` | segredos (`openssl rand -hex 32`); vazios, o Compose não sobe |
| `CORS_ORIGINS`, `FRONTEND_URL` | `["https://<DOMAIN>"]` e `https://<DOMAIN>` |
| `ANTHROPIC_API_KEY` | chave da API do Claude |
| `SMTP_*`, `EMAIL_FROM` | servidor de e-mail (sem `SMTP_HOST` a API não sobe em produção) |
| `TURNSTILE_SECRET_KEY`, `VITE_TURNSTILE_SITE_KEY` | captcha do cadastro (recomendado num site aberto) |
| `DAILY_LLM_BUDGET_USD` | teto diário de gasto com o Claude |

O Compose define sozinho `ENVIRONMENT=production`, `DATABASE_URL`, `REDIS_URL` (com a senha),
`TRUST_PROXY_HEADERS=true`, `LOG_FORMAT=json` e `ACCESS_LOG=true`.

```bash
# 4. Subir (o primeiro build leva alguns minutos)
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build --wait
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

Para não repetir os parâmetros, crie um alias (os exemplos abaixo usam ele):

```bash
echo "alias dcp='docker compose -f /opt/receita/docker-compose.prod.yml --env-file /opt/receita/.env.production'" >> ~/.bashrc
source ~/.bashrc
```

> O project name é `receita-prod` (fixo no arquivo): os volumes se chamam `receita-prod_pgdata`,
> `receita-prod_redisdata`, `receita-prod_hf-cache`, `receita-prod_caddy-data` e
> `receita-prod_caddy-config`. Não apague o `caddy-data`: ele guarda os certificados.

## 4. Primeiro acesso

1. `curl https://<DOMAIN>/api/health/ready` → `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`.
2. Abra `https://<DOMAIN>`, crie uma conta e confirme pelo e-mail. Se o e-mail não chegar, veja
   [E-mails](#e-mails-não-chegam).
3. Importe um vídeo curto com legenda. Acompanhe com `dcp logs -f worker`.
4. Importe um vídeo sem legenda para testar o whisper (`dcp logs -f worker-whisper`). Na primeira
   vez o worker baixa o modelo (~500 MB para o `small`) antes de ficar saudável.
5. Confira os headers: `curl -sI https://<DOMAIN> | grep -iE 'strict-transport|content-security|x-content-type|referrer|permissions'`.

## 5. Atualizações

```bash
cd /opt/receita
scripts/backup-db.sh                 # antes de qualquer atualização
git pull
dcp up -d --build --wait             # reconstrói as imagens; o migrate roda antes da API
docker image prune -f                # apaga as imagens antigas
```

O `migrate` aplica as migrações novas antes de API e workers subirem. Durante a troca dos
containers a API fica fora por alguns segundos (o Caddy responde 502 nesse intervalo).

- **Mudou só o `deploy/Caddyfile`:** `dcp exec caddy caddy reload --config /etc/caddy/Caddyfile`.
- **Mudou o `.env.production`:** `dcp up -d` recria os containers afetados. `VITE_TURNSTILE_SITE_KEY`
  vai para o JS no build: depois de mudá-la, `dcp up -d --build caddy`.
- **Atualizar só o yt-dlp** (o YouTube muda com frequência): `cd backend && uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs`,
  faça commit e `dcp up -d --build worker worker-whisper` (veja [yt-dlp bloqueado](#yt-dlp-bloqueado-sign-in-to-confirm-youre-not-a-bot)).

## 6. Backups e restauração

`scripts/backup-db.sh` faz um `pg_dump` no formato custom (comprimido) de dentro do container do
Postgres, confere o arquivo com `pg_restore --list` e só então o grava em
`BACKUP_DIR/receita-<data UTC>.dump` (permissão 600). Os backups com mais de `BACKUP_KEEP_DAYS`
dias são apagados. As duas variáveis vêm do `.env.production` (padrão `/var/backups/receita` e 14).

```bash
sudo mkdir -p /var/backups/receita && sudo chown "$USER" /var/backups/receita
scripts/backup-db.sh
```

**Cron** (todo dia às 03:15 do horário da VPS), com `crontab -e` do usuário do deploy:

```cron
15 3 * * * cd /opt/receita && scripts/backup-db.sh >> /var/log/receita-backup.log 2>&1
```

(crie o log antes: `sudo touch /var/log/receita-backup.log && sudo chown "$USER" /var/log/receita-backup.log`)

**Cópia fora da VPS:** um backup que só existe no mesmo disco não protege contra a perda da VPS.
Copie a pasta para outro lugar, por exemplo com o [rclone](https://rclone.org/) para um bucket
S3/B2 numa segunda linha do cron:

```cron
45 3 * * * rclone copy /var/backups/receita remoto:receita-backups --max-age 48h
```

**Restaurar** (substitui o banco atual):

```bash
scripts/restore-db.sh /var/backups/receita/receita-20260101T031500Z.dump
```

O script confere o dump, pede confirmação (digite `restaurar`; `--yes` pula), faz um backup do
banco atual por segurança, para API e workers, recria o banco, aplica o dump e sobe tudo de novo
(o `migrate` leva um backup antigo até o schema atual).

O que **não** está no backup do banco: o Redis (fila de jobs, contadores de rate limit e sessões
revogadas; ele persiste em AOF no volume `redisdata`), o modelo do whisper (é baixado de novo) e
os certificados (o Caddy pede de novo). Os scripts aceitam `ENV_FILE` e `COMPOSE_FILES` para
outros arquivos (é assim que o teste local usa).

## 7. Monitoramento

**Saúde:** `dcp ps` mostra o estado de cada healthcheck. Para um monitor externo (UptimeRobot,
Healthchecks.io, Uptime Kuma), use `https://<DOMAIN>/api/health/ready`: 200 com
`{"status":"ok"}` ou 503 com `checks` dizendo se caiu o banco ou o Redis.

| Serviço | Healthcheck |
|---|---|
| `caddy` | API de administração do Caddy (`127.0.0.1:2019`, só dentro do container) |
| `api` | `GET /health/ready` (banco e Redis) |
| `worker`, `worker-whisper` | `arq ... --check`: a chave de saúde que o worker grava no Redis a cada 60 s |
| `db`, `redis` | `pg_isready` e `redis-cli ping` |

**Logs:** a API e os workers escrevem uma linha JSON por evento (`ts`, `level`, `logger`, `msg`
e campos extras). A API registra cada pedido no logger `app.access` (método, caminho sem query
string, status, duração e IP do cliente); o Caddy registra o acesso em JSON, com cookies e o
`token` dos links de e-mail ocultos.

```bash
dcp logs -f --since 10m api worker worker-whisper
dcp logs api | grep '"app.access"' | jq -r 'select(.status >= 500) | [.ts, .method, .path, .status] | @tsv'
dcp logs worker | grep -E '"level": "(WARNING|ERROR)"'
```

### Custo do Claude

Cada chamada paga ao Claude fica na tabela `llm_calls` (modelo e `usage`). O orçamento diário
(`DAILY_LLM_BUDGET_USD`, por dia UTC) é somado dali: ao atingir o teto, imports de vídeos novos
ficam `deferred` e voltam para a fila às 00:05 UTC; cópias de vídeos já processados continuam.

```bash
dcp exec api python -m app.cli llm-spend --days 14
```

```
orçamento diário (DAILY_LLM_BUDGET_USD): US$ 10.00
dia (UTC)    chamadas  falhas   gasto (US$)   % do orçamento
2026-01-15         42       1        2.9310       29%
...
```

Rotina sugerida:

- confira o `llm-spend` uma vez por semana e ajuste `DAILY_LLM_BUDGET_USD` e `DAILY_IMPORT_LIMIT`;
- configure também um **limite de gasto mensal no Console da Anthropic** (Settings → Limits):
  é a trava final, independente do app;
- imports adiados aparecem no log do worker (`import ... adiado`) e na consulta:
  `dcp exec db psql -U receita -c "select count(*) from imports where status = 'deferred'"`.

## 8. IP do cliente e rate limit

O rate limit por IP (cadastro, login, imports) precisa do IP do cliente, não do Caddy. A cadeia é:

1. O **Caddy** sobrescreve o `X-Forwarded-For` com `{client_ip}` (`header_up` no Caddyfile):
   qualquer `X-Forwarded-For` mandado pelo próprio cliente é descartado.
2. O **uvicorn** roda com `--proxy-headers --forwarded-allow-ips <CADDY_IP>`: só aceita os
   headers `X-Forwarded-*` vindos do IP fixo do Caddy na rede interna (`CADDY_IP`, numa
   `PROXY_SUBNET` própria).
3. A **API**, com `TRUST_PROXY_HEADERS=true`, usa o último endereço do `X-Forwarded-For`.

**Decisão: `X-Forwarded-For`, não `CF-Connecting-IP`.** A API só confia no header que o Caddy
escreve. Sem Cloudflare, `{client_ip}` é o IP que se conectou ao Caddy. Com o proxy do
Cloudflare, a conexão vem dos servidores dele; aí descomente o bloco `servers` no
`deploy/Caddyfile` (`trusted_proxies` com as faixas do Cloudflare e
`client_ip_headers CF-Connecting-IP`): o Caddy passa a ler o `CF-Connecting-IP`, **só** quando a
conexão vem de uma faixa do Cloudflare, e o repassa no mesmo `X-Forwarded-For`. Ler o
`CF-Connecting-IP` direto na API permitiria forjar o IP sempre que alguém acessasse a VPS sem
passar pelo Cloudflare. Atualize as faixas quando o Cloudflare mudar a lista
(https://www.cloudflare.com/ips/).

## 9. Segurança (o que já vem configurado)

- HTTPS automático com renovação; HTTP redireciona para HTTPS; HTTP/3.
- Headers: `Strict-Transport-Security` (`HSTS_MAX_AGE`, 1 ano), `Content-Security-Policy`
  (YouTube IFrame API, `i.ytimg.com`, Turnstile e Google Fonts liberados; scripts inline e
  `<object>` bloqueados; `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` (o embed do YouTube
  precisa da origem) e `Permissions-Policy` sem câmera, microfone, geolocalização etc.
- Cookie de sessão `Secure`, `HttpOnly`, `SameSite=Lax`; CSRF por `X-Requested-With` + `Origin`.
- `/api` com corpo de no máximo 1 MB e `Cache-Control: no-store`.
- A documentação interativa da API (`/docs`, `/openapi.json`) só existe em development.
- A API recusa subir em produção sem `SECRET_KEY` (32+ caracteres) ou sem `SMTP_HOST`.
- Os jobs vão para o Redis em JSON (não em pickle) e o Redis exige senha.
- Firewall da VPS: libere só 22, 80 e 443 (ex.: `ufw allow OpenSSH && ufw allow 80,443/tcp && ufw allow 443/udp && ufw enable`).
  O Docker publica só as portas do Caddy.

## 10. GPU (opcional)

Com uma GPU NVIDIA o whisper fica muito mais rápido (e dá para usar o modelo `medium`):

1. instale o driver e o [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) na VPS;
2. a imagem precisa das bibliotecas CUDA 12 e cuDNN 9 que o CTranslate2 usa: o caminho mais
   simples é acrescentar `nvidia-cublas-cu12` e `nvidia-cudnn-cu12==9.*` às dependências do backend
   (ou trocar a base do estágio `runtime` por `nvidia/cuda:12.x-cudnn-runtime`);
3. descomente o bloco `reservations.devices` do `worker-whisper` no `docker-compose.prod.yml`;
4. no `.env.production`: `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`.

## 11. Testar o stack de produção localmente

O `docker-compose.prod.test.yml` e o `deploy/local-test.env` sobem o mesmo stack com
`DOMAIN=localhost` (certificado da CA interna do Caddy), nas portas 8080/8443, com project name
próprio (`receita-prod-test`, não mexe no compose de dev) e um Mailpit recebendo os e-mails:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.prod.test.yml \
  --env-file deploy/local-test.env up -d --build --wait

curl -k https://localhost:8443/api/health/ready
# e-mails: http://localhost:8025

# Playwright (headers, CSP com o player do YouTube, cadastro com e-mail, cookie Secure, import)
cd frontend
docker run --rm --network host --ipc=host \
  -u $(id -u):$(id -g) --group-add $(getent group docker | cut -d: -f3) \
  -e HOME=/tmp -e npm_config_cache=/tmp/.npm \
  -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
  -v $PWD:/w -w /w mcr.microsoft.com/playwright:v1.64.0-noble \
  npx playwright test -c playwright.prod.config.ts

# backups contra o stack de teste
ENV_FILE=deploy/local-test.env COMPOSE_FILES=docker-compose.prod.yml:docker-compose.prod.test.yml \
  BACKUP_DIR=/tmp/receita-backups scripts/backup-db.sh

docker compose -f docker-compose.prod.yml -f docker-compose.prod.test.yml \
  --env-file deploy/local-test.env down -v
```

O `deploy/local-test.env` tem segredos falsos e está no git: **nunca** use na VPS.

## 12. Troubleshooting

### yt-dlp bloqueado ("Sign in to confirm you're not a bot")

Os imports falham com `youtube_blocked` ("O YouTube bloqueou temporariamente o acesso ao
vídeo...", depois das novas tentativas automáticas). O player
do site continua funcionando (é o embed oficial); só a busca de metadados, legendas e áudio pelo
servidor é afetada.

1. **Atualize o yt-dlp** (a correção costuma sair em dias): `uv lock --upgrade-package yt-dlp
   --upgrade-package yt-dlp-ejs` no `backend/`, commit e `dcp up -d --build worker worker-whisper`.
   A imagem já traz o deno, o runtime de JavaScript que o yt-dlp usa para os desafios do YouTube.
2. **Use cookies de uma conta** (de preferência uma conta só para isso): exporte os cookies do
   `youtube.com` em formato Netscape (extensão "Get cookies.txt LOCALLY", numa janela anônima
   logada que você fecha em seguida), copie para `deploy/secrets/youtube-cookies.txt`
   (`chmod 644`; a pasta está no `.gitignore`) e ponha `YTDLP_COOKIES_FILE=/run/receita/youtube-cookies.txt`
   no `.env.production`; depois `dcp up -d worker worker-whisper`. O yt-dlp usa uma cópia
   temporária a cada chamada, então o arquivo original fica só para leitura. Os cookies expiram:
   repita quando o bloqueio voltar.
3. Se persistir, o IP da VPS pode estar marcado: troque de região/provedor ou use um IPv6 novo.

### Whisper lento

- `dcp logs worker-whisper` mostra o tempo de cada job; `docker stats` mostra CPU e memória.
- Só um vídeo por vez (`WHISPER_MAX_JOBS=1`) é o mais rápido por vídeo; aumentar só ajuda com
  CPU sobrando, e cada job a mais pede ~1–2 GB de RAM (aumente o `memory` do serviço).
- Modelo menor (`WHISPER_MODEL=base`) é mais rápido e pior em português; `medium` só com GPU.
- O frontend mostra a posição na fila (`queue_position`) enquanto o import espera o whisper.
- Container reiniciando com `exit 137`: faltou memória; aumente o limite ou a RAM da VPS.

### E-mails não chegam

- `dcp logs api | grep -i smtp` mostra falhas de conexão/autenticação.
- Porta 587 com `SMTP_SECURITY=starttls` ou 465 com `ssl`. Alguns provedores de VPS bloqueiam a
  saída SMTP: use a porta do provedor de e-mail (ex.: 2587 no Resend) ou peça o desbloqueio.
- O domínio do `EMAIL_FROM` precisa estar verificado no provedor (SPF, DKIM e DMARC no DNS);
  sem isso as mensagens caem no spam ou são recusadas.
- Os links dos e-mails usam `FRONTEND_URL`: confira que é `https://<DOMAIN>`.

### Outros

- **Certificado não sai:** `dcp logs caddy`. O DNS precisa apontar para a VPS e as portas 80/443
  precisam estar abertas (o desafio do Let's Encrypt usa a 80 ou a 443). Muitas tentativas
  falhas geram limite temporário do Let's Encrypt.
- **403 `csrf_failed` em todo POST:** `CORS_ORIGINS` não tem a origem exata do site
  (`https://<DOMAIN>`, sem barra no fim).
- **API não sobe:** `dcp logs api migrate`. Sem `SECRET_KEY`/`SMTP_HOST` a API recusa subir em
  produção, com a mensagem do que falta.
- **Rede `172.31.250.0/24` já em uso:** mude `PROXY_SUBNET` e `CADDY_IP` no `.env.production`.
- **Imports parados:** o worker reenfileira imports sem job a cada 5 min e encerra os parados há
  mais de `IMPORT_STALE_AFTER_MIN`. `dcp restart worker worker-whisper` é seguro.
