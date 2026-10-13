import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'

import { expect, test, type Page } from '@playwright/test'

// Fumaça do stack de produção local (Caddy + build estático + API com uvicorn de produção +
// workers + Postgres/Redis com senha + Mailpit). Precisa do docker CLI e do socket do Docker,
// como os outros E2E, para rodar o seed de demonstração no container da API.
const PROJECT = process.env.COMPOSE_PROJECT ?? 'receita-prod-test'
const MAILPIT_URL = process.env.MAILPIT_URL ?? 'http://localhost:8025'
const SCREENSHOTS = 'e2e/screenshots'
const PASSWORD = 'senha-de-teste-prod'
// Real, com legenda e fora do seed: sem ANTHROPIC_API_KEY termina em llm_missing_key depois de
// passar pelo yt-dlp (com o deno da imagem) no worker de produção.
const IMPORT_URL = 'https://www.youtube.com/watch?v=88syMwVL0dk'

function container(service: string): string {
  const id = execFileSync(
    'docker',
    [
      'ps',
      '-q',
      '--filter',
      `label=com.docker.compose.project=${PROJECT}`,
      '--filter',
      `label=com.docker.compose.service=${service}`,
    ],
    { encoding: 'utf8' },
  ).trim()
  if (!id) throw new Error(`serviço "${service}" do projeto ${PROJECT} não está rodando`)
  return id.split('\n')[0]
}

/** O seed só roda em development: aqui, só nesta execução, num stack de teste. */
function seedDemo(email: string): string {
  return execFileSync(
    'docker',
    [
      'exec',
      '-e',
      'ENVIRONMENT=development',
      container('api'),
      'python',
      '-m',
      'app.cli',
      'seed-demo',
      '--email',
      email,
    ],
    { encoding: 'utf8' },
  )
}

type MailpitList = { messages: { ID: string; To: { Address: string }[] }[] }

async function verificationLinkFromMailpit(page: Page, email: string): Promise<string> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const list = (await (
      await page.request.get(
        `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
      )
    ).json()) as MailpitList
    const message = list.messages.find((m) => m.To.some((to) => to.Address === email))
    if (message) {
      const full = (await (
        await page.request.get(`${MAILPIT_URL}/api/v1/message/${message.ID}`)
      ).json()) as { Text: string }
      const match = full.Text.match(/https:\/\/\S+\/verificar-email\?token=[\w.-]+/)
      if (match) return match[0]
    }
    await page.waitForTimeout(500)
  }
  throw new Error(`o e-mail de confirmação para ${email} não chegou ao Mailpit`)
}

/** Violações de CSP da nossa página (as de dentro do iframe do YouTube não contam). */
async function cspViolations(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? [])
}

test.beforeAll(() => mkdirSync(SCREENSHOTS, { recursive: true }))

test('headers de segurança, healthchecks e SPA servida pelo Caddy', async ({ request }) => {
  const home = await request.get('/')
  expect(home.status()).toBe(200)
  const headers = home.headers()
  expect(headers['strict-transport-security']).toMatch(/^max-age=\d+; includeSubDomains$/)
  expect(headers['x-content-type-options']).toBe('nosniff')
  expect(headers['x-frame-options']).toBe('DENY')
  expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
  expect(headers['permissions-policy']).toContain('camera=()')
  const csp = headers['content-security-policy']
  expect(csp).toContain("default-src 'self'")
  expect(csp).toContain('https://www.youtube.com')
  expect(csp).toContain('https://www.youtube-nocookie.com')
  expect(csp).toContain('https://i.ytimg.com')
  expect(csp).toContain('https://challenges.cloudflare.com')
  expect(csp).toContain("frame-ancestors 'none'")
  expect(headers['server']).toBeUndefined()

  // Rota da SPA (fallback para o index.html) e assets com cache longo.
  const deep = await request.get('/receitas/qualquer-coisa')
  expect(deep.status()).toBe(200)
  expect(await deep.text()).toContain('<div id="root"></div>')
  const asset = (await home.text()).match(/\/assets\/[\w.-]+\.js/)?.[0]
  expect(asset).toBeDefined()
  const js = await request.get(asset!)
  expect(js.headers()['cache-control']).toBe('public, max-age=31536000, immutable')

  // /api → API sem o prefixo; documentação interativa desligada em produção.
  expect(await (await request.get('/api/health')).json()).toEqual({ status: 'ok' })
  expect(await (await request.get('/api/health/ready')).json()).toEqual({
    status: 'ok',
    checks: { database: 'ok', redis: 'ok' },
  })
  expect((await request.get('/api/docs')).status()).toBe(404)
  expect((await request.get('/api/health')).headers()['cache-control']).toBe('no-store')
})

test('cadastro com e-mail real (Mailpit) → login → receita com o player do YouTube → import', async ({
  page,
  context,
}) => {
  await context.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      const w = window as unknown as { __csp?: string[] }
      ;(w.__csp ??= []).push(`${event.violatedDirective} ${event.blockedURI}`)
    })
  })
  const email = `prod+${Date.now()}@example.com`

  await test.step('cadastro pelo site manda o e-mail pelo SMTP', async () => {
    await page.goto('/cadastro')
    await page.getByLabel('Nome').fill('Ana Produção')
    await page.getByLabel('E-mail').fill(email)
    await page.getByLabel('Senha').fill(PASSWORD)
    await page.getByRole('button', { name: 'Criar conta' }).click()
    await expect(page.getByRole('heading', { name: 'Verifique seu e-mail' })).toBeVisible()

    const link = await verificationLinkFromMailpit(page, email)
    expect(new URL(link).origin).toBe(new URL(page.url()).origin)
    await page.goto(link)
    await expect(page.getByRole('heading', { name: 'E-mail confirmado!' })).toBeVisible()
  })

  await test.step('login: cookie de sessão Secure, HttpOnly e SameSite=Lax', async () => {
    await page.goto('/entrar')
    await page.getByLabel('E-mail').fill(email)
    await page.getByLabel('Senha').fill(PASSWORD)
    await page.getByRole('button', { name: 'Entrar' }).click()
    await expect(page).toHaveURL(/\/livro$/)
    const session = (await context.cookies()).find((c) => c.name === 'receita_session')
    expect(session).toMatchObject({ secure: true, httpOnly: true, sameSite: 'Lax' })
  })

  await test.step('receita: o player do YouTube carrega com a CSP e o passo leva ao tempo', async () => {
    seedDemo(email)
    await page.reload()
    await expect(page.getByRole('list', { name: 'Receitas' }).getByRole('article')).toHaveCount(3)
    // As capas vêm de i.ytimg.com (img-src).
    const cover = page.getByRole('list', { name: 'Receitas' }).locator('img').first()
    await expect
      .poll(() => cover.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth))
      .toBeGreaterThan(0)
    await page.screenshot({ path: `${SCREENSHOTS}/prod-livro-1280.png`, fullPage: true })

    await page.getByRole('link', { name: 'Bolo de cenoura com calda de chocolate' }).click()
    const player = page.locator('[data-player-status]')
    await expect(player).toHaveAttribute('data-player-status', 'ready', { timeout: 30_000 })
    await expect(player.locator('iframe')).toHaveAttribute(
      'src',
      /youtube-nocookie\.com\/embed\/-pRC-FQXLEI/,
    )
    await page.getByRole('button', { name: 'Ver o passo 4 no vídeo, em 1:53' }).click()
    const videoFrame = page.frames().find((frame) => frame.url().includes('youtube-nocookie.com'))
    expect(videoFrame).toBeDefined()
    await expect
      .poll(() => videoFrame!.evaluate(() => document.querySelector('video')?.currentTime ?? -1), {
        timeout: 20_000,
      })
      .toBeGreaterThanOrEqual(112)
    await page.screenshot({ path: `${SCREENSHOTS}/prod-receita-1280.png` })
    expect(await cspViolations(page)).toEqual([])
  })

  await test.step('import real passa pelos workers de produção (yt-dlp) e para no Claude', async () => {
    await page.goto('/nova')
    await page.getByLabel('Link do vídeo no YouTube').fill(IMPORT_URL)
    await page.getByRole('button', { name: 'Importar receita' }).click()
    await expect(page).toHaveURL(/\/nova\?import=[0-9a-f-]{36}$/)
    await expect(page.getByText('Não conseguimos importar esse vídeo')).toBeVisible({
      timeout: 4 * 60_000,
    })
    await expect(
      page.getByText('A geração de receitas não está configurada no servidor.'),
    ).toBeVisible()
    await page.screenshot({ path: `${SCREENSHOTS}/prod-import-1280.png` })
    expect(await cspViolations(page)).toEqual([])
  })
})

test('celular (360px): receita com o player', async ({ browser }) => {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: 360, height: 780 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: 'pt-BR',
  })
  const page = await context.newPage()
  const email = `prod360+${Date.now()}@example.com`
  const csrf = { 'X-Requested-With': 'playwright' }
  const register = await page.request.post('/api/auth/register', {
    headers: csrf,
    data: { name: 'Bia', email, password: PASSWORD },
  })
  expect(register.status()).toBe(202)
  const token = new URL(await verificationLinkFromMailpit(page, email)).searchParams.get('token')
  expect(
    (await page.request.post('/api/auth/verify', { headers: csrf, data: { token } })).status(),
  ).toBe(204)
  const login = await page.request.post('/api/auth/login', {
    headers: csrf,
    data: { email, password: PASSWORD },
  })
  expect(login.ok()).toBe(true)
  seedDemo(email)

  await page.goto('/livro')
  await page.getByRole('link', { name: 'Pão de queijo de liquidificador' }).click()
  await expect(page.locator('[data-player-status]')).toHaveAttribute(
    'data-player-status',
    'ready',
    {
      timeout: 30_000,
    },
  )
  await page.locator('[data-player-status]').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SCREENSHOTS}/prod-receita-360.png` })
  await context.close()
})
