import { readFileSync } from 'node:fs'

import { expect, test, type Cookie, type Page } from '@playwright/test'

import { PASSWORD, createVerifiedUser, resetRateLimits } from './support/backend'

// Fase 5: edição e restauração, notas, avaliação, porções, marcações, filtros na URL,
// impressão, exportar e excluir a conta, contra o backend de verdade (seed-demo).
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

test.describe.serial('receita', () => {
  test('editar, salvar, avisar ao sair sem salvar e restaurar a original', async ({ page }) => {
    await openRecipe(page, 'Brigadeiro de panela')
    await page.getByRole('button', { name: 'Editar' }).click()
    await expect(page.getByLabel('Título')).toBeFocused()
    await expect(page).toHaveTitle('Editando: Brigadeiro de panela · Receita')

    await page.getByLabel('Título').fill('Brigadeiro da vó')
    await page.getByLabel('Rendimento').fill('20 unidades')
    await page.getByRole('button', { name: 'Adicionar ingrediente' }).click()
    const novo = page.getByRole('group', { name: 'Ingrediente 7' })
    await novo.getByLabel('Quantidade').fill('1')
    await novo.getByLabel('Unidade').fill('pitada')
    await novo.getByLabel('Ingrediente', { exact: true }).fill('sal')
    await page.getByRole('button', { name: 'Mover passo 2 para cima' }).click()
    const passo1 = page.getByRole('group', { name: 'Passo 1' })
    await expect(passo1.getByLabel('O que fazer')).toHaveValue(
      'Junte o leite condensado e misture bem.',
    )
    await passo1.getByLabel('Tempo no vídeo').fill('1:20')

    // Sair com alterações pede confirmação; "Continuar editando" mantém tudo.
    await page.getByRole('link', { name: 'Meu livro', exact: true }).first().click()
    const dialog = page.getByRole('alertdialog', { name: 'Sair sem salvar?' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Continuar editando' }).click()
    await expect(page).toHaveURL(/\/receitas\//)
    await expect(page.getByLabel('Título')).toHaveValue('Brigadeiro da vó')

    // Erro de validação aparece antes de enviar.
    await page.getByRole('group', { name: 'Passo 2' }).getByLabel('Tempo no vídeo').fill('99')
    await page.getByRole('button', { name: 'Salvar alterações' }).click()
    await expect(page.getByRole('alert')).toContainText('Passo 2, tempo no vídeo')
    await page.getByRole('group', { name: 'Passo 2' }).getByLabel('Tempo no vídeo').fill('0:59')

    await page.getByRole('button', { name: 'Salvar alterações' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Brigadeiro da vó' })).toBeVisible()
    await expect(page.getByText('Alterações salvas.')).toBeVisible()

    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: 'Brigadeiro da vó' })).toBeVisible()
    await expect(page.getByRole('checkbox', { name: '1 pitada sal' })).toBeVisible()
    const steps = page.getByRole('region', { name: 'Modo de preparo' }).getByRole('listitem')
    await expect(steps.first()).toContainText('Junte o leite condensado')
    await expect(
      page.getByRole('button', { name: 'Ver o passo 1 no vídeo, em 1:20' }),
    ).toBeVisible()

    await page.getByRole('button', { name: 'Restaurar receita original' }).click()
    const reset = page.getByRole('alertdialog', { name: 'Restaurar a receita original?' })
    await expect(reset.getByRole('button', { name: 'Cancelar' })).toBeFocused()
    await reset.getByRole('button', { name: 'Restaurar' }).click()
    await expect(
      page.getByRole('heading', { level: 1, name: 'Brigadeiro de panela' }),
    ).toBeVisible()
    await expect(page.getByText(/Receita restaurada/)).toBeVisible()
    await expect(page.getByRole('checkbox', { name: '1 pitada sal' })).toHaveCount(0)
  })

  test('notas salvam sozinhas e a avaliação fica guardada', async ({ page }) => {
    await openRecipe(page, 'Bolo de cenoura com calda de chocolate')
    const notes = page.getByRole('textbox', { name: 'Minhas notas' })
    await notes.fill('Assei 40 minutos na forma de 22 cm.')
    await expect(page.getByText(/^Salvo às \d{2}:\d{2}\.$/)).toBeVisible({ timeout: 5000 })

    const rating = page.getByRole('group', { name: 'Sua avaliação' })
    await rating.locator('label').nth(3).click()
    await expect(rating.getByRole('radio', { name: /^4 estrelas/ })).toBeChecked()

    await page.reload()
    await expect(notes).toHaveValue('Assei 40 minutos na forma de 22 cm.')
    await expect(rating.getByRole('radio', { name: /^4 estrelas/ })).toBeChecked()

    // O teclado também escolhe as estrelas.
    await rating.getByRole('radio', { name: /^4 estrelas/ }).focus()
    await page.keyboard.press('ArrowRight')
    await expect(rating.getByRole('radio', { name: /^5 estrelas/ })).toBeChecked()

    await page.goto('/livro')
    const card = page.getByRole('article').filter({ hasText: 'Bolo de cenoura' })
    await expect(card.getByText('Avaliação: 5 de 5')).toBeAttached()
  })

  test('porções escalam as quantidades e as marcações persistem', async ({ page }) => {
    await openRecipe(page, 'Pão de queijo de liquidificador')
    const control = page.getByRole('group', { name: 'Rende' })
    await expect(control.getByRole('status')).toHaveText('6 unidades')

    for (let i = 0; i < 3; i++) await control.getByRole('button', { name: 'Menos porções' }).click()
    await expect(control.getByRole('status')).toHaveText('3 unidades')
    await expect(
      page.getByRole('checkbox', { name: '3/8 xícara (chá) polvilho azedo' }),
    ).toBeVisible()
    await expect(page.getByRole('checkbox', { name: '1/2 ovo' })).toBeVisible()
    await expect(
      page.getByRole('checkbox', { name: '1 colher de sopa óleo, e mais um pouco para untar' }),
    ).toBeVisible()

    for (let i = 0; i < 9; i++) await control.getByRole('button', { name: 'Mais porções' }).click()
    await expect(control.getByRole('status')).toHaveText('12 unidades')
    await expect(
      page.getByRole('checkbox', { name: '1 1/2 xícara (chá) polvilho azedo' }),
    ).toBeVisible()
    await expect(
      page.getByRole('checkbox', { name: '2 xícaras (chá) queijo meia-cura, ralado grosso' }),
    ).toBeVisible()
    await control.getByRole('button', { name: 'Voltar para 6 unidades' }).click()
    await expect(page.getByRole('checkbox', { name: '1 ovo' })).toBeVisible()

    await page.getByRole('checkbox', { name: '1 ovo' }).check()
    await page.getByRole('checkbox', { name: '1/2 colher de chá sal' }).check()
    await expect(page.getByText('2 de 6 separados.')).toBeVisible()
    await page.reload()
    await expect(page.getByRole('checkbox', { name: '1 ovo' })).toBeChecked()
    await page.getByRole('button', { name: 'Limpar marcações' }).click()
    await expect(page.getByRole('checkbox', { name: '1 ovo' })).not.toBeChecked()
    await page.reload()
    await expect(page.getByRole('checkbox', { name: '1 ovo' })).not.toBeChecked()
  })

  test('impressão: sem player nem navegação, sem tempos, com o link do vídeo', async ({ page }) => {
    await openRecipe(page, 'Pão de queijo de liquidificador')
    await page.emulateMedia({ media: 'print' })
    await expect(page.locator('[data-player-status]')).toBeHidden()
    await expect(page.getByRole('navigation', { name: 'Principal' })).toBeHidden()
    await expect(page.getByRole('button', { name: /Ver o passo 1 no vídeo/ })).toBeHidden()
    await expect(page.getByRole('button', { name: 'Editar' })).toBeHidden()
    await expect(page.getByText(/youtube\.com\/watch\?v=p_UZdXhjeVQ/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Modo de preparo' })).toBeVisible()
    await expect(page.getByRole('checkbox', { name: '1 ovo' })).toBeVisible()
  })
})

test('filtros do livro ficam na URL: compartilhar, voltar e recarregar', async ({ page }) => {
  await page.goto('/livro')
  const cards = page.getByRole('list', { name: 'Receitas' }).getByRole('article')
  await expect(cards).toHaveCount(3)
  const tags = page.getByRole('group', { name: 'Tags' })

  await tags.getByRole('button', { name: '#chocolate' }).click()
  await expect(page).toHaveURL(/\?tag=chocolate$/)
  await expect(cards).toHaveCount(2)
  await expect(tags.getByRole('button', { name: '#chocolate' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )

  await page.getByLabel('Buscar').fill('leite condensado')
  await expect(page).toHaveURL(/\?tag=chocolate&q=leite\+condensado$/)
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('Brigadeiro')

  // Link compartilhado abre com os mesmos filtros.
  const shared = page.url()
  const other = await page.context().newPage()
  await other.goto(shared)
  await expect(other.getByLabel('Buscar')).toHaveValue('leite condensado')
  await expect(other.getByRole('list', { name: 'Receitas' }).getByRole('article')).toHaveCount(1)
  await other.close()

  // Voltar desfaz a tag (a busca troca a entrada atual do histórico).
  await page.goBack()
  await expect(page).toHaveURL(/\/livro$/)
  await expect(cards).toHaveCount(3)
  await expect(page.getByLabel('Buscar')).toHaveValue('')
  await page.goForward()
  await expect(cards).toHaveCount(1)

  await page.getByRole('button', { name: 'Favoritas' }).click()
  await expect(page).toHaveURL(/favoritas=1/)
  await expect(page.getByRole('heading', { name: 'Nenhuma receita encontrada' })).toBeVisible()
  await page.getByRole('button', { name: 'Limpar filtros' }).first().click()
  await expect(page).toHaveURL(/\/livro$/)
  await expect(cards).toHaveCount(3)
})

test('exportar os dados baixa o JSON da conta', async ({ page }) => {
  await page.goto('/conta')
  await expect(page.getByRole('progressbar', { name: /Cota/ })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Exportar meus dados' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('receita-meus-dados.json')
  const data = JSON.parse(readFileSync(await download.path(), 'utf8'))
  expect(data.recipes).toHaveLength(3)
  expect(data.user.email).toMatch(/@example\.com$/)
  await expect(page.getByText(/foi baixado/)).toBeVisible()
})

test('excluir a conta pede a senha e termina na apresentação', async ({ page, context }) => {
  // Conta própria: depois de excluída, a sessão comum dos outros testes continua valendo.
  await context.clearCookies()
  const { email } = await createVerifiedUser(page.request, { seed: true })
  await page.goto('/conta')
  await page.getByRole('button', { name: 'Quero excluir minha conta' }).click()
  await expect(page.getByLabel('Sua senha')).toBeFocused()

  await page.getByLabel('Sua senha').fill('senha-errada')
  await page.getByRole('checkbox', { name: /serão apagadas para sempre/ }).check()
  await page.getByRole('button', { name: 'Excluir minha conta para sempre' }).click()
  await expect(page.getByText('Senha incorreta.')).toBeVisible()
  await expect(page.getByLabel('Sua senha')).toBeFocused()

  await page.getByLabel('Sua senha').fill(PASSWORD)
  await page.getByRole('button', { name: 'Excluir minha conta para sempre' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByText('Sua conta foi excluída')).toBeVisible()

  // A conta não existe mais: o login falha e o livro pede para entrar.
  const login = await page.request.post('/api/auth/login', {
    headers: { 'X-Requested-With': 'playwright' },
    data: { email, password: PASSWORD },
  })
  expect(login.status()).toBe(401)
  await page.goto('/livro')
  await expect(page).toHaveURL(/\/entrar\?next=%2Flivro$/)
})
