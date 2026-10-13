import { defineConfig, devices } from '@playwright/test'

// E2E contra o Docker Compose da raiz já rodando (frontend em :5173, API atrás do proxy /api).
// Veja e2e/README.md para rodar com a imagem oficial do Playwright.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  globalSetup: './e2e/support/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
