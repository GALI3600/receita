import { expect, test, type BrowserContext, type Cookie, type Page } from '@playwright/test'

import { PASSWORD, createVerifiedUser, resetRateLimits } from './support/backend'

// Regressões da revisão da fase 5 (sessão expirada na edição, foco escondido, diálogos, menu,
// impressão, filtros), no navegador de verdade contra o backend do Compose.
let sessionCookies: Cookie[] = []

test.beforeAll(async ({ browser }) => {
  resetRateLimits()
  const context = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
  })
  await createVerifiedUser(context.request, { seed: true })
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

/** Conta própria (com as receitas de demonstração) para os testes que encerram a sessão. */
async function ownAccount(page: Page, context: BrowserContext): Promise<string> {
  resetRateLimits()
  await context.clearCookies()
  const { email } = await createVerifiedUser(page.request, { seed: true })
  return email
}

async function loginAgain(page: Page, email: string) {
  await expect(page).toHaveURL(/\/entrar\?next=%2Freceitas%2F/)
  await page.getByLabel('E-mail').fill(email)
  await page.getByLabel('Senha').fill(PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/receitas\/[\w-]+$/)
}

test.describe('sessão expirada no meio da edição', () => {
  test('salvar a edição com a sessão expirada não perde o rascunho', async ({ page, context }) => {
    const email = await ownAccount(page, context)
    await openRecipe(page, 'Brigadeiro de panela')
    await page.getByRole('button', { name: 'Editar' }).click()
    await page.getByLabel('Título').fill('Brigadeiro editado longo')
    await page.getByLabel('Preparo (min)').fill('12')

    await context.clearCookies()
    await page.getByRole('button', { name: 'Salvar alterações' }).click()
    await loginAgain(page, email)

    // De volta à receita: o editor reabre com o que a pessoa tinha digitado.
    await expect(page.getByText(/Recuperamos as alterações/)).toBeVisible()
    await expect(page.getByLabel('Título')).toHaveValue('Brigadeiro editado longo')
    await expect(page.getByLabel('Preparo (min)')).toHaveValue('12')
    await page.getByRole('button', { name: 'Salvar alterações' }).click()
    await expect(
      page.getByRole('heading', { level: 1, name: 'Brigadeiro editado longo' }),
    ).toBeVisible()

    // Salvo: abrir de novo não "recupera" nada.
    await page.reload()
    await expect(
      page.getByRole('heading', { level: 1, name: 'Brigadeiro editado longo' }),
    ).toBeVisible()
    await expect(page.getByLabel('Título')).toHaveCount(0)
  })

  test('nota digitada com a sessão expirada volta depois de entrar', async ({ page, context }) => {
    const email = await ownAccount(page, context)
    await openRecipe(page, 'Pão de queijo de liquidificador')
    await context.clearCookies()
    await page.getByRole('textbox', { name: 'Minhas notas' }).fill('Usei queijo canastra.')
    await loginAgain(page, email)

    const notes = page.getByRole('textbox', { name: 'Minhas notas' })
    await expect(notes).toHaveValue('Usei queijo canastra.')
    await expect(page.getByText(/^Salvo às \d{2}:\d{2}\.$/)).toBeVisible({ timeout: 5000 })
    await page.reload()
    await expect(notes).toHaveValue('Usei queijo canastra.')
  })

  test('sair da conta apaga as marcações de ingredientes deste navegador', async ({
    page,
    context,
  }) => {
    await ownAccount(page, context)
    await openRecipe(page, 'Pão de queijo de liquidificador')
    await page.getByRole('checkbox', { name: '1 ovo' }).check()
    const marked = () =>
      page.evaluate(
        () => Object.keys(localStorage).filter((key) => key.startsWith('receita:marcados:')).length,
      )
    expect(await marked()).toBe(1)

    await page.goto('/conta')
    await page.getByRole('button', { name: 'Sair da conta' }).click()
    await expect(page).toHaveURL(/\/$/)
    expect(await marked()).toBe(0)
  })
})

test.describe('edição: foco e diálogos', () => {
  for (const viewport of [
    { width: 360, height: 780 },
    { width: 768, height: 1024 },
    { width: 1280, height: 860 },
  ]) {
    test(`a barra de ações não esconde o campo com foco (${viewport.width}px)`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport)
      await openRecipe(page, 'Bolo de cenoura com calda de chocolate')
      await page.getByRole('button', { name: 'Editar' }).click()
      await expect(page.getByLabel('Título')).toBeFocused()

      const covered: string[] = []
      for (let i = 0; i < 45; i++) {
        await page.keyboard.press('Tab')
        const result = await page.evaluate(() => {
          const element = document.activeElement as HTMLElement | null
          const bar = document.querySelector('.editor-actions')
          if (!element || !bar || bar.contains(element)) return null
          const box = element.getBoundingClientRect()
          const barBox = bar.getBoundingClientRect()
          const overlap = Math.max(
            0,
            Math.min(box.bottom, barBox.bottom) - Math.max(box.top, barBox.top),
          )
          return {
            id: element.id || element.getAttribute('aria-label') || element.tagName,
            overlap,
          }
        })
        if (result && result.overlap > 0) covered.push(`${result.id} (${result.overlap}px)`)
      }
      expect(covered).toEqual([])
    })
  }

  for (const width of [360, 1280]) {
    test(`"Sair sem salvar?" fica centralizado na tela (${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await openRecipe(page, 'Brigadeiro de panela')
      await page.getByRole('button', { name: 'Editar' }).click()
      await page.getByLabel('Título').fill('Brigadeiro mexido')

      for (const open of [
        () => page.getByRole('link', { name: '← Meu livro' }).click(),
        () => page.getByRole('button', { name: 'Cancelar' }).click(),
      ]) {
        await open()
        const dialog = page.getByRole('alertdialog')
        await expect(dialog).toBeVisible()
        // A folha entra com uma animação (sobe 8px): mede depois que ela termina.
        await dialog.evaluate((element) =>
          Promise.all(element.getAnimations().map((animation) => animation.finished)),
        )
        const box = await dialog.boundingBox()
        if (!box) throw new Error('diálogo sem caixa')
        const expectedTop = (800 - box.height) / 2
        expect(Math.abs(box.y - expectedTop)).toBeLessThan(4)
        await dialog.getByRole('button', { name: 'Continuar editando' }).click()
        await expect(dialog).toHaveCount(0)
      }
    })
  }

  test('o × de remover tag tem 44px', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 })
    await openRecipe(page, 'Pão de queijo de liquidificador')
    await page.getByRole('button', { name: 'Editar' }).click()
    const remove = page.getByRole('button', { name: 'Remover a tag pão de queijo' })
    await remove.scrollIntoViewIfNeeded()
    // A área de toque (o botão e o ::after dele) cobre 44x44px em volta do centro.
    const hits = await remove.evaluate((button) => {
      const box = button.getBoundingClientRect()
      const x = box.left + box.width / 2
      const y = box.top + box.height / 2
      return [
        [x - 21.5, y],
        [x + 21.5, y],
        [x, y - 21.5],
        [x, y + 21.5],
      ].map(([px, py]) => document.elementFromPoint(px, py)?.closest('button') === button)
    })
    expect(hits).toEqual([true, true, true, true])
  })
})

test.describe('página da receita', () => {
  test('desktop: a lista de ingredientes cortada avisa que há mais itens', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 700 })
    await openRecipe(page, 'Bolo de cenoura com calda de chocolate')
    // A coluna fixa gruda no topo depois de rolar a página.
    await page.mouse.wheel(0, 600)
    const more = page.getByRole('button', { name: /Mais ingredientes/ })
    await expect(more).toBeVisible()
    const list = page.locator('.recipe-ingredients')
    await expect(list).toHaveAttribute('data-more-below', 'true')

    // O botão rola a lista; no fim, o aviso some.
    for (let i = 0; i < 6 && (await more.isVisible()); i++) {
      await more.click()
      // Espera a rolagem suave terminar antes de clicar de novo.
      await page.waitForTimeout(800)
    }
    await expect(more).toBeHidden()
    await expect(page.getByRole('checkbox', { name: /^1\/3 xícara água/ })).toBeInViewport()
  })

  test('impressão: ingredientes marcados saem com a caixa vazia e sem risco', async ({ page }) => {
    await openRecipe(page, 'Pão de queijo de liquidificador')
    const egg = page.getByRole('checkbox', { name: '1 ovo' })
    await egg.check()
    await page.emulateMedia({ media: 'print' })
    const text = page.locator('label', { has: egg }).locator('> span')
    await expect(text).toHaveCSS('text-decoration-line', 'none')
    await expect(egg).toHaveCSS('appearance', 'none')
    await expect(egg).toHaveCSS('background-image', 'none')
    await page.emulateMedia({ media: 'screen' })
    await egg.uncheck()
  })

  test('receita inexistente: o título da aba diz o que aconteceu', async ({ page }) => {
    await page.goto('/receitas/00000000-0000-0000-0000-000000000000')
    await expect(page.getByRole('heading', { name: 'Receita não encontrada' })).toBeVisible()
    await expect(page).toHaveTitle('Receita não encontrada · Receita')
  })
})

test.describe('menu e livro no celular', () => {
  test.use({ viewport: { width: 360, height: 780 } })

  test('Tab depois do último link do menu fecha o menu', async ({ page }) => {
    await page.goto('/livro')
    await page.getByRole('button', { name: 'Menu' }).click()
    const panel = page.locator('#menu-celular')
    await expect(panel).toBeVisible()
    for (let i = 0; i < 3; i++) await page.keyboard.press('Tab')
    await expect(page.locator('#menu-celular').getByRole('link', { name: 'Conta' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(panel).toBeHidden()
    await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  test('a primeira capa aparece na primeira tela do livro', async ({ page }) => {
    await page.goto('/livro')
    const first = page.getByRole('list', { name: 'Receitas' }).getByRole('article').first()
    await expect(first).toBeVisible()
    const box = await first.boundingBox()
    expect(box?.y).toBeLessThan(560)
  })

  test('busca longa demais não quebra a lista', async ({ page }) => {
    await page.goto(`/livro?q=${'a'.repeat(250)}&tag=${'b'.repeat(60)}`)
    await expect(page.getByText('Não conseguimos abrir o seu livro')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Nenhuma receita encontrada' })).toBeVisible()
    await expect(page.getByLabel('Buscar')).toHaveAttribute('maxlength', '200')
  })
})
