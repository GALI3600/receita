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
- `a11y.spec.ts`: axe-core (WCAG 2.1 A/AA) nas páginas principais, tema claro e escuro, 360px e
  1280px;
- `screenshots.spec.ts`: capturas de tela (360px e 1280px, inclusive impressão em PNG/PDF A4 e
  modo escuro) em `e2e/screenshots/`.

Para rodar um arquivo só, passe o caminho no fim: `npx playwright test e2e/a11y.spec.ts`.
