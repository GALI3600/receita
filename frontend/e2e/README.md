# E2E (Playwright)

Rodam contra o Docker Compose da raiz já de pé (`docker compose up`), com `ENVIRONMENT=development`:
o link de confirmação é lido do log da API (`docker logs`), as receitas vêm do
`python -m app.cli seed-demo` e os contadores de rate limit são zerados no início. Por isso os
testes precisam do `docker` CLI e do socket do Docker.

Sem Node no host, use a imagem oficial do Playwright na mesma versão do `@playwright/test`:

```bash
cd frontend
docker run --rm --network host --ipc=host \
  -u $(id -u):$(id -g) --group-add $(getent group docker | cut -d: -f3) \
  -e HOME=/tmp -e npm_config_cache=/tmp/.npm \
  -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
  -v $PWD:/w -w /w mcr.microsoft.com/playwright:v1.64.0-noble \
  npx playwright test
```

As capturas de tela (360px e 1280px) ficam em `e2e/screenshots/`.
