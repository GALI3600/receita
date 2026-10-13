import { defineConfig, devices } from '@playwright/test'

// Fumaça do stack de PRODUÇÃO rodando localmente (docker-compose.prod.yml + .prod.test.yml):
// https://localhost:8443 com o certificado da CA interna do Caddy e e-mails no Mailpit.
// Veja docs/DEPLOY.md, "Testar o stack de produção localmente".
export default defineConfig({
  testDir: './e2e/prod',
  outputDir: './test-results/prod',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 6 * 60_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://localhost:8443',
    ignoreHTTPSErrors: true,
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
