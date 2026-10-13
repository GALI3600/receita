import { expect, test } from '@playwright/test'

import { PASSWORD, seedDemo, uniqueEmail, verificationLink } from './support/backend'

// Vídeo real, curto e com legenda, que não está no seed: sem ANTHROPIC_API_KEY o import passa
// pela busca e pela transcrição e termina em failed / llm_missing_key.
const IMPORT_URL = 'https://www.youtube.com/watch?v=88syMwVL0dk'

test('cadastro → confirmação → login → livro → receita → favoritar → import com falha', async ({
  page,
}) => {
  test.setTimeout(6 * 60_000)
  const email = uniqueEmail()

  await test.step('cadastro mostra o aviso de verificar o e-mail', async () => {
    const since = new Date(Date.now() - 2000).toISOString()
    await page.goto('/')
    await page.getByRole('link', { name: 'Criar meu livro' }).click()
    await expect(page).toHaveURL(/\/cadastro$/)
    await page.getByLabel('Nome').fill('Ana Teste')
    await page.getByLabel('E-mail').fill(email)
    await page.getByLabel('Senha').fill(PASSWORD)
    await page.getByRole('button', { name: 'Criar conta' }).click()
    await expect(page.getByRole('heading', { name: 'Verifique seu e-mail' })).toBeVisible()
    await expect(page.getByText(email)).toBeVisible()

    const link = await verificationLink(email, since)
    expect(new URL(link).pathname).toBe('/verificar-email')
    await page.goto(link)
    await expect(page.getByRole('heading', { name: 'E-mail confirmado!' })).toBeVisible()
  })

  await test.step('login volta para /nova (next) e mostra a cota', async () => {
    await page.getByRole('link', { name: 'Entrar' }).last().click()
    await expect(page).toHaveURL(/\/entrar\?next=%2Fnova$/)
    await page.getByLabel('E-mail').fill(email)
    await page.getByLabel('Senha').fill(PASSWORD)
    await page.getByRole('button', { name: 'Entrar' }).click()
    await expect(page).toHaveURL(/\/nova$/)
    await expect(page.getByTestId('quota-note')).toContainText('10 receitas novas')
  })

  await test.step('livro vazio, depois o seed-demo, mostra as receitas', async () => {
    await page.getByRole('link', { name: 'Meu livro' }).click()
    await expect(
      page.getByRole('heading', { name: 'Seu livro ainda está em branco' }),
    ).toBeVisible()

    seedDemo(email)
    await page.reload()
    const cards = page.getByRole('list', { name: 'Receitas' }).getByRole('article')
    await expect(cards).toHaveCount(3)
    await expect(page.getByRole('link', { name: 'Pão de queijo de liquidificador' })).toBeVisible()

    await page.getByLabel('Buscar').fill('polvilho')
    await expect(cards).toHaveCount(1)
    await expect(page).toHaveURL(/q=polvilho/)
    await page.getByRole('button', { name: 'Limpar filtros' }).first().click()
    await expect(cards).toHaveCount(3)
  })

  await test.step('abrir a receita e pular para um passo no vídeo', async () => {
    await page.getByRole('link', { name: 'Bolo de cenoura com calda de chocolate' }).click()
    await expect(
      page.getByRole('heading', { level: 1, name: 'Bolo de cenoura com calda de chocolate' }),
    ).toBeVisible()
    await expect(page.getByRole('region', { name: 'massa' }).getByRole('checkbox')).toHaveCount(8)

    const player = page.locator('[data-player-status]')
    await expect(player).toHaveAttribute('data-player-status', 'ready', { timeout: 30_000 })
    const iframe = player.locator('iframe')
    await expect(iframe).toHaveAttribute('src', /youtube-nocookie\.com\/embed\/-pRC-FQXLEI/)

    const stepButton = page.getByRole('button', { name: 'Ver o passo 4 no vídeo, em 1:53' })
    await stepButton.click()
    await expect(player).toHaveAttribute('data-last-seek', '113')
    // O vídeo de verdade (dentro do iframe do YouTube) foi para 1:53.
    const videoFrame = page.frames().find((frame) => frame.url().includes('youtube-nocookie.com'))
    expect(videoFrame).toBeDefined()
    await expect
      .poll(() => videoFrame!.evaluate(() => document.querySelector('video')?.currentTime ?? -1), {
        timeout: 20_000,
      })
      .toBeGreaterThanOrEqual(112)
    await expect(page.locator('li[aria-current="step"]')).toContainText(
      'Coloque as cenouras picadas no liquidificador.',
    )
  })

  await test.step('favoritar persiste e aparece no filtro de favoritas', async () => {
    await page.getByRole('button', { name: 'Favoritar' }).click()
    await expect(page.getByRole('button', { name: 'Favorita' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await page.reload()
    await expect(page.getByRole('button', { name: 'Favorita' })).toBeVisible()

    await page.goto('/livro')
    await page.getByRole('button', { name: 'Favoritas' }).click()
    await expect(page).toHaveURL(/favoritas=1/)
    const cards = page.getByRole('list', { name: 'Receitas' }).getByRole('article')
    await expect(cards).toHaveCount(1)
    await expect(cards.first()).toContainText('Bolo de cenoura')
  })

  await test.step('import de um vídeo real termina em llm_missing_key com a mensagem', async () => {
    await page.goto('/nova')
    await page.getByLabel('Link do vídeo no YouTube').fill(IMPORT_URL)
    await page.getByRole('button', { name: 'Importar receita' }).click()
    await expect(page).toHaveURL(/\/nova\?import=[0-9a-f-]{36}$/)
    await expect(page.getByRole('list', { name: 'Etapas da importação' })).toBeVisible()

    // O progresso sobrevive a recarregar a página (o id está na URL).
    await page.reload()
    await expect(
      page
        .getByRole('list', { name: 'Etapas da importação' })
        .or(page.getByText('Não conseguimos importar esse vídeo')),
    ).toBeVisible()

    await expect(page.getByText('Não conseguimos importar esse vídeo')).toBeVisible({
      timeout: 4 * 60_000,
    })
    await expect(
      page.getByText('A geração de receitas não está configurada no servidor.'),
    ).toBeVisible()
    await page.getByRole('button', { name: 'Tentar outro link' }).click()
    await expect(page).toHaveURL(/\/nova$/)
    await expect(page.getByLabel('Link do vídeo no YouTube')).toHaveValue('')
  })
})
