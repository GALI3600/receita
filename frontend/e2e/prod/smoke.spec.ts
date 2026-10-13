import { execFileSync, spawnSync } from 'node:child_process'
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

/** stdout + stderr do container desde `since` (o Caddy e a API usam os dois). */
function dockerLogs(service: string, since: string): string {
  const result = spawnSync('docker', ['logs', '--since', since, container(service)], {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  })
  return `${result.stdout}\n${result.stderr}`
}

/**
 * Visitante IPv6 "de fora": um netns ligado ao host por um veth (não por uma bridge do Docker)
 * acessa a porta publicada pelo IPv6 do host. Roda num container privilegiado na rede do host e
 * desfaz tudo no fim. Do próprio host (::1) a conexão passaria pelo docker-proxy de qualquer jeito.
 */
const IPV6_CLIENT = `
set -e
apk add -q --no-cache iproute2 curl >/dev/null
ip netns add rcpv6
trap 'ip link del rcpv6-host 2>/dev/null; ip netns del rcpv6 2>/dev/null' EXIT
ip link add rcpv6-host type veth peer name rcpv6-peer
ip link set rcpv6-peer netns rcpv6
ip addr add fd99:6::1/64 dev rcpv6-host nodad
ip link set rcpv6-host up
ip -n rcpv6 addr add fd99:6::2/64 dev rcpv6-peer nodad
ip -n rcpv6 link set rcpv6-peer up
ip -n rcpv6 -6 route add default via fd99:6::1
ip netns exec rcpv6 curl -sk -m 10 --resolve "localhost:$PORT:[fd99:6::1]" \
  -o /dev/null -w '%{http_code}' "https://localhost:$PORT/api/auth/me?ipv6=$PROBE"
`

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

test('erros do Caddy (asset inexistente) com os headers de segurança e sem cache longo', async ({
  request,
}) => {
  const missing = await request.get('/assets/nao-existe-123.js')
  expect(missing.status()).toBe(404)
  const headers = missing.headers()
  expect(headers['content-security-policy']).toContain("frame-ancestors 'none'")
  expect(headers['strict-transport-security']).toMatch(/^max-age=\d+/)
  expect(headers['x-content-type-options']).toBe('nosniff')
  expect(headers['x-frame-options']).toBe('DENY')
  expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
  expect(headers['permissions-policy']).toContain('camera=()')
  expect(headers['server']).toBeUndefined()
  expect(headers['cache-control']).toBe('no-store')
})

test('Caddy sem root e sem escrita no site (/srv)', () => {
  const caddy = container('caddy')
  expect(execFileSync('docker', ['exec', caddy, 'id', '-u'], { encoding: 'utf8' }).trim()).toBe(
    '10002',
  )
  const write = spawnSync('docker', ['exec', caddy, 'touch', '/srv/index.html', '/srv/novo.js'], {
    encoding: 'utf8',
  })
  expect(write.status).not.toBe(0)
  expect(write.stderr).toMatch(/Read-only file system|Permission denied/)
})

test('o token do link de e-mail não vaza no log do Caddy pelo Referer dos assets', async ({
  page,
}) => {
  const since = new Date(Date.now() - 1000).toISOString()
  const token = `TOKENVAZADO${Date.now()}`
  const assets: string[] = []
  page.on('request', (req) => {
    if (req.url().includes('/assets/') && req.headers()['referer']?.includes(token)) {
      assets.push(req.url())
    }
  })
  await page.goto(`/redefinir-senha?token=${token}`)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  // O navegador manda mesmo a URL com o token no Referer dos assets (mesma origem).
  expect(assets.length).toBeGreaterThan(0)

  await expect
    .poll(() => dockerLogs('caddy', since).includes('"uri":"/assets/'), { timeout: 10_000 })
    .toBe(true)
  const logs = dockerLogs('caddy', since)
  expect(logs).not.toContain(token)
  expect(logs).toContain('/redefinir-senha?token=REDACTED')
})

test('visitante IPv6 chega à API com o próprio IP (não o gateway da rede Docker)', () => {
  test.skip(process.env.E2E_SKIP_IPV6 === '1', 'E2E_SKIP_IPV6=1')
  const since = new Date(Date.now() - 1000).toISOString()
  const probe = `${Date.now()}`
  const port = new URL(test.info().project.use.baseURL ?? 'https://localhost:8443').port || '443'
  const status = execFileSync(
    'docker',
    [
      'run',
      '--rm',
      '-i',
      '--privileged',
      '--network',
      'host',
      '-e',
      `PORT=${port}`,
      '-e',
      `PROBE=${probe}`,
      'alpine:3.23',
      'sh',
      '-s',
    ],
    { input: IPV6_CLIENT, encoding: 'utf8' },
  )
  // 401 (sem sessão): o /health não entra no log de acesso da API.
  expect(status).toBe('401')

  const caddyLine = dockerLogs('caddy', since)
    .split('\n')
    .find((line) => line.includes(`ipv6=${probe}`))
  expect(caddyLine).toBeDefined()
  expect(JSON.parse(caddyLine!).request.client_ip).toBe('fd99:6::2')
  const apiLines = dockerLogs('api', since)
    .split('\n')
    .filter((line) => line.includes('"app.access"') && line.includes('"/auth/me"'))
    .map((line) => JSON.parse(line) as { client_ip: string })
  expect(apiLines.map((line) => line.client_ip)).toContain('fd99:6::2')
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
