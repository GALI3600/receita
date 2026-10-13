import { expect, test, type Cookie, type Locator, type Page } from '@playwright/test'

import { PASSWORD, createVerifiedUser, resetRateLimits } from './support/backend'

// Regressões da revisão da fase 4, conferidas no navegador de verdade (layout, foco, rede).
// Uma conta só (com as receitas de demonstração) para o arquivo todo: o cadastro tem limite
// por IP. Cada teste começa logado com o cookie dessa conta.
let sessionCookies: Cookie[] = []
let email = ''

test.beforeAll(async ({ browser }) => {
  resetRateLimits()
  const context = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
  })
  ;({ email } = await createVerifiedUser(context.request, { seed: true }))
  sessionCookies = await context.cookies()
  await context.close()
})

test.beforeEach(async ({ context }) => {
  await context.addCookies(sessionCookies)
})

async function openRecipe(page: Page, title: string) {
  await page.goto('/livro')
  await page.getByRole('link', { name: title }).click()
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
}

async function height(locator: Locator): Promise<number> {
  const box = await locator.boundingBox()
  if (!box) throw new Error('elemento sem caixa')
  return box.height
}

test.describe('sessão e navegação', () => {
  test('next que normaliza para //host vai para o livro, sem tela em branco', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))

    for (const next of ['%2F.%2F%2Fevil.example%2Fphish', '%2Fa%2F..%2F%2Fevil.example%2Fx']) {
      await page.goto(`/entrar?next=${next}`)
      await expect(page).toHaveURL(/\/livro$/)
      await expect(page.getByRole('heading', { name: 'Meu livro' })).toBeVisible()
    }
    expect(errors).toEqual([])
  })

  test('sair da conta termina na apresentação', async ({ page, context }) => {
    // Sessão própria: o logout revoga a sessão no servidor e os outros testes usam a comum.
    await context.clearCookies()
    const login = await page.request.post('/api/auth/login', {
      headers: { 'X-Requested-With': 'playwright' },
      data: { email, password: PASSWORD },
    })
    expect(login.ok()).toBe(true)
    await page.goto('/conta')
    await page.getByRole('button', { name: 'Sair da conta' }).click()

    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('link', { name: 'Criar meu livro' })).toBeVisible()
    await page.waitForTimeout(500)
    await expect(page).toHaveURL(/\/$/)
  })
})

test.describe('importação', () => {
  test('import inexistente mostra o erro e para o polling', async ({ page }) => {
    let polls = 0
    page.on('request', (request) => {
      if (request.url().includes('/api/imports/')) polls++
    })

    await page.goto('/nova?import=00000000-0000-4000-8000-000000000000')
    await expect(page.getByText('Importação não encontrada.')).toBeVisible()
    // (No dev, o StrictMode monta duas vezes e pode fazer 2 pedidos na abertura.)
    const atError = polls
    expect(atError).toBeLessThanOrEqual(2)
    await page.waitForTimeout(4000)
    expect(polls).toBe(atError)
  })

  test('sem internet o envio avisa em vez de ficar parado', async ({ page, context }) => {
    await page.goto('/nova')
    await expect(page.getByTestId('quota-note')).toBeVisible()

    await context.setOffline(true)
    await page.getByLabel('Link do vídeo no YouTube').fill('https://youtu.be/-pRC-FQXLEI')
    await page.getByRole('button', { name: 'Importar receita' }).click()

    await expect(page.getByRole('alert')).toContainText('Não conseguimos falar com o servidor')
    await expect(page.getByRole('button', { name: 'Importar receita' })).toBeEnabled()
    await context.setOffline(false)
  })

  test('campos mostram o anel de foco do teclado', async ({ page }) => {
    await page.goto('/nova')
    const input = page.getByLabel('Link do vídeo no YouTube')
    await input.focus()
    await expect(input).toHaveCSS('outline-style', 'solid')
    await expect(input).toHaveCSS('outline-width', '3px')
  })
})

test.describe('página da receita', () => {
  test('desktop baixo: player e todos os ingredientes alcançáveis enquanto se lê o preparo', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 })
    await openRecipe(page, 'Bolo de cenoura com calda de chocolate')
    const player = page.locator('[data-player-status]')

    // Lendo os últimos passos (o passo 11 inteiro na tela), o player continua inteiro à vista.
    const lastStep = page.locator('li', { hasText: 'Quando a calda começar a desgrudar' })
    await lastStep.scrollIntoViewIfNeeded()
    await expect(lastStep).toBeInViewport({ ratio: 1 })
    await expect(player).toBeInViewport({ ratio: 1 })

    // A última linha dos ingredientes aparece rolando a lista (o player continua à vista).
    const last = page.getByRole('checkbox', { name: /^1\/3 xícara água/ })
    await last.scrollIntoViewIfNeeded()
    await expect(last).toBeInViewport({ ratio: 1 })
    await expect(player).toBeInViewport({ ratio: 1 })
  })

  test('celular: o player fica fixo no topo e o passo escolhido continua na tela', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 780 })
    await openRecipe(page, 'Bolo de cenoura com calda de chocolate')
    const player = page.locator('[data-player-status]')
    await expect(page.locator('[data-sticky-player]')).toHaveAttribute('data-sticky-player', 'true')

    const button = page.getByRole('button', { name: /Ver o passo 10 no vídeo/ })
    await button.scrollIntoViewIfNeeded()
    await button.click()

    await expect(player).toBeInViewport({ ratio: 1 })
    await expect(page.locator('li[aria-current="step"]')).toBeInViewport()
    await expect(button).toBeInViewport()
    // Alvos de toque de 44px: tempo do passo e linha do ingrediente.
    expect(await height(button)).toBeGreaterThanOrEqual(44)
    const label = page.locator('label', { has: page.getByRole('checkbox') }).first()
    expect(await height(label)).toBeGreaterThanOrEqual(44)
  })

  test('grupo de ingredientes com espaço tem nome acessível', async ({ page }) => {
    await openRecipe(page, 'Brigadeiro de panela')
    await expect(
      page.getByRole('region', { name: 'para enrolar' }).getByRole('checkbox'),
    ).toHaveCount(2)
  })

  test('vídeo indisponível: os tempos viram texto', async ({ page }) => {
    await page.route('**/api/recipes/*', async (route) => {
      if (route.request().method() !== 'GET' || route.request().url().endsWith('/tags')) {
        return route.fallback()
      }
      const response = await route.fetch()
      const body = await response.json()
      body.video.youtube_id = 'zzzzzzzzzzz'
      await route.fulfill({ response, json: body })
    })
    await openRecipe(page, 'Pão de queijo de liquidificador')

    await expect(page.locator('[data-player-status]')).toHaveAttribute(
      'data-player-status',
      /unavailable|error/,
      { timeout: 30_000 },
    )
    await expect(page.getByRole('button', { name: /no vídeo, em/ })).toHaveCount(0)
    await expect(page.getByText('No vídeo em 0:17')).toBeVisible()
  })
})

test('alvos da navegação do topo têm 44px', async ({ page, context }) => {
  await page.goto('/livro')
  const nav = page.getByRole('navigation', { name: 'Principal' })
  for (const name of ['Meu livro', 'Nova receita', 'Conta']) {
    expect(await height(nav.getByRole('link', { name }))).toBeGreaterThanOrEqual(44)
  }

  await context.clearCookies()
  await page.goto('/')
  for (const name of ['Entrar', 'Criar conta']) {
    expect(await height(nav.getByRole('link', { name }))).toBeGreaterThanOrEqual(44)
  }
})
