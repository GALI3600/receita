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

- `journey.spec.ts` e `review.spec.ts`: jornada principal e regressões da fase 4;
- `phase5.spec.ts`: edição e restauração, notas, avaliação, porções, marcações, filtros na URL,
  impressão, exportar e excluir a conta;
- `review5.spec.ts`: regressões da revisão da fase 5 (sessão expirada no meio da edição, foco
  atrás da barra fixa, diálogos centralizados, menu do celular, impressão, limites da busca);
- `a11y.spec.ts`: axe-core (WCAG 2.1 A/AA) nas páginas principais, tema claro e escuro, 360px e
  1280px;
- `screenshots.spec.ts`: capturas de tela (360px e 1280px, inclusive impressão em PNG/PDF A4 e
  modo escuro) em `e2e/screenshots/`.

Para rodar um arquivo só, passe o caminho no fim: `npx playwright test e2e/a11y.spec.ts`.

## Fumaça do stack de produção (`e2e/prod`)

`e2e/prod/smoke.spec.ts` roda com a própria configuração (`playwright.prod.config.ts`, fora da
suíte padrão) contra o stack de produção local (`https://localhost:8443`, certificado da CA
interna do Caddy, e-mails no Mailpit em `http://localhost:8025`): headers de segurança e CSP,
healthchecks, fallback da SPA e cache dos assets, cadastro com o link lido do Mailpit, cookie
`Secure`, o player do YouTube carregando sem violações de CSP, um import real passando pelos
workers de produção e capturas `e2e/screenshots/prod-*.png`. Como subir o stack:
[`docs/DEPLOY.md`](../../docs/DEPLOY.md#11-testar-o-stack-de-produção-localmente).

```bash
docker run ... mcr.microsoft.com/playwright:v1.64.0-noble npx playwright test -c playwright.prod.config.ts
```
