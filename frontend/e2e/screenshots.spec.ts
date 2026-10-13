import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type Page } from '@playwright/test'

import { createVerifiedUser, resetRateLimits } from './support/backend'

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), 'screenshots')
mkdirSync(OUT_DIR, { recursive: true })

const VIEWPORTS = [
  { name: '360', width: 360, height: 780 },
  { name: '1280', width: 1280, height: 860 },
] as const

async function shot(page: Page, name: string) {
  // Fontes carregadas e sem animação de spinner no meio da captura.
  await page.evaluate(async () => {
    await document.fonts.ready
    await Promise.all(
      [...document.images].map((img) =>
        img.complete
          ? null
          : new Promise((resolve) => {
              img.loading = 'eager'
              img.addEventListener('load', resolve)
              img.addEventListener('error', resolve)
              setTimeout(resolve, 5000)
            }),
      ),
    )
  })
  await page.screenshot({ path: join(OUT_DIR, `${name}.png`), fullPage: true })
}

// O cadastro tem limite por IP (5 por hora) e cada teste cria contas novas.
test.beforeEach(() => resetRateLimits())

/** Espera o player do YouTube mostrar a capa do vídeo (para a captura não pegar o spinner). */
async function waitForPlayer(page: Page, videoTitle: string) {
  const player = page.locator('[data-player-status]')
  await expect(player).toHaveAttribute('data-player-status', 'ready', { timeout: 30_000 })
  await expect(
    page.frameLocator('[data-player-status] iframe').getByText(videoTitle).first(),
  ).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(1500)
}

for (const viewport of VIEWPORTS) {
  test.describe(`telas em ${viewport.name}px`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } })

    test('landing, livro, nova (em progresso) e receita', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('heading', { level: 1 })).toContainText('Do vídeo para a receita')
      await shot(page, `landing-${viewport.name}`)

      await createVerifiedUser(page.request, { seed: true })

      await page.goto('/livro')
      await expect(page.getByRole('list', { name: 'Receitas' }).getByRole('article')).toHaveCount(3)
      await page.waitForLoadState('networkidle')
      await shot(page, `livro-${viewport.name}`)

      // Import em andamento simulado (o real passa rápido demais por cada etapa para a captura).
      const now = new Date().toISOString()
      await page.route('**/api/imports/demo-em-andamento', (route) =>
        route.fulfill({
          json: {
            id: 'demo-em-andamento',
            url: 'https://www.youtube.com/watch?v=88syMwVL0dk',
            youtube_id: '88syMwVL0dk',
            status: 'transcribing',
            recipe_id: null,
            error: null,
            queue_position: 2,
            created_at: now,
            updated_at: now,
          },
        }),
      )
      await page.goto('/nova?import=demo-em-andamento')
      await expect(page.getByText('Aguardando a vez na transcrição: 2º na fila.')).toBeVisible()
      await page.waitForLoadState('networkidle')
      await shot(page, `nova-progresso-${viewport.name}`)

      await page.goto('/livro')
      await page.getByRole('link', { name: 'Brigadeiro de panela' }).click()
      const player = page.locator('[data-player-status]')
      await expect(player).toHaveAttribute('data-player-status', 'ready', { timeout: 30_000 })
      // Espera a capa do vídeo aparecer dentro do iframe e captura antes do play.
      await expect(
        page
          .frameLocator('[data-player-status] iframe')
          .getByText('A receita de brigadeiro da Rita Lobo')
          .first(),
      ).toBeVisible({ timeout: 20_000 })
      await page.waitForTimeout(1500)
      await shot(page, `receita-${viewport.name}`)

      await page.getByRole('button', { name: /Ver o passo 3 no vídeo/ }).click()
      await expect(player).toHaveAttribute('data-last-seek', '197')
      if (viewport.width < 1024) {
        // No celular o player rola para a vista ao escolher um passo.
        await expect(player).toBeInViewport()
      }
      await page.evaluate(() => window.scrollTo(0, 0))
      await shot(page, `receita-passo-${viewport.name}`)
    })

    test('entrar, cadastro, 404, nova, edição, porções, conta e livro vazio', async ({ page }) => {
      await page.goto('/entrar')
      await expect(page.getByRole('heading', { level: 1, name: 'Entrar' })).toBeVisible()
      await shot(page, `entrar-${viewport.name}`)
      await page.goto('/cadastro')
      await expect(page.getByRole('heading', { level: 1, name: 'Criar conta' })).toBeVisible()
      await shot(page, `cadastro-${viewport.name}`)
      await page.goto('/pagina-que-nao-existe')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await shot(page, `404-${viewport.name}`)

      await createVerifiedUser(page.request)
      await page.goto('/livro')
      await expect(
        page.getByRole('heading', { name: 'Seu livro ainda está em branco' }),
      ).toBeVisible()
      await shot(page, `livro-vazio-${viewport.name}`)

      await page.goto('/nova')
      await expect(page.getByLabel('Link do vídeo no YouTube')).toBeVisible()
      await shot(page, `nova-${viewport.name}`)

      await page.context().clearCookies()
      await createVerifiedUser(page.request, { seed: true })
      await page.goto('/livro?tag=chocolate')
      await expect(page.getByRole('list', { name: 'Receitas' }).getByRole('article')).toHaveCount(2)
      await page.waitForLoadState('networkidle')
      await shot(page, `livro-filtrado-${viewport.name}`)

      if (viewport.width < 640) {
        await page.getByRole('button', { name: 'Menu' }).click()
        await page.waitForTimeout(300)
        await page.screenshot({ path: join(OUT_DIR, `menu-${viewport.name}.png`) })
        await page.keyboard.press('Escape')
      }

      await page.goto('/livro')
      await page.getByRole('link', { name: 'Pão de queijo de liquidificador' }).click()
      await waitForPlayer(page, 'Pão de queijo fácil')
      const control = page.getByRole('group', { name: 'Rende' })
      for (let i = 0; i < 6; i++)
        await control.getByRole('button', { name: 'Mais porções' }).click()
      await page.getByRole('checkbox').nth(1).check()
      await page.getByRole('group', { name: 'Sua avaliação' }).locator('label').nth(4).click()
      await page
        .getByRole('textbox', { name: 'Minhas notas' })
        .fill('Dobrei a receita para o lanche da escola.\nFicou melhor com queijo canastra.')
      await expect(page.getByText(/^Salvo às/)).toBeVisible({ timeout: 5000 })
      await page.evaluate(() => window.scrollTo(0, 0))
      await shot(page, `receita-porcoes-${viewport.name}`)

      // Impressão: a mesma página em mídia print (PNG para conferir e PDF A4 de verdade).
      await page.emulateMedia({ media: 'print' })
      await shot(page, `receita-impressao-${viewport.name}`)
      if (viewport.width > 1000) {
        await page.pdf({ path: join(OUT_DIR, 'receita-impressao.pdf'), format: 'A4' })
        // Largura de uma folha A4 (210 mm a 96 dpi), como o PDF.
        await page.setViewportSize({ width: 794, height: 1123 })
        await shot(page, 'receita-impressao-a4')
        await page.setViewportSize({ width: viewport.width, height: viewport.height })
      }
      await page.emulateMedia({ media: 'screen' })

      await page.getByRole('button', { name: 'Editar' }).click()
      await page.getByLabel('Título').fill('')
      await page.getByRole('button', { name: 'Salvar alterações' }).click()
      await expect(page.getByRole('alert')).toBeVisible()
      await page.evaluate(() => window.scrollTo(0, 0))
      await shot(page, `receita-editar-${viewport.name}`)
      await page.getByRole('button', { name: 'Cancelar' }).click()
      await page.getByRole('button', { name: 'Descartar' }).click()

      await page.getByRole('button', { name: 'Restaurar receita original' }).click()
      await expect(page.getByRole('alertdialog')).toBeVisible()
      await page.waitForTimeout(300)
      await page.screenshot({ path: join(OUT_DIR, `receita-restaurar-${viewport.name}.png`) })
      await page.getByRole('button', { name: 'Cancelar' }).click()

      await page.goto('/conta')
      await expect(page.getByRole('progressbar')).toBeVisible()
      await shot(page, `conta-${viewport.name}`)
      await page.getByRole('button', { name: 'Quero excluir minha conta' }).click()
      await shot(page, `conta-excluir-${viewport.name}`)
    })

    test('livro à noite (modo escuro)', async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'dark' })
      await createVerifiedUser(page.request, { seed: true })
      await page.goto('/livro')
      await expect(page.getByRole('list', { name: 'Receitas' }).getByRole('article')).toHaveCount(3)
      await page.waitForLoadState('networkidle')
      await shot(page, `escuro-livro-${viewport.name}`)
      await page.getByRole('link', { name: 'Bolo de cenoura com calda de chocolate' }).click()
      await waitForPlayer(page, 'Bolo de cenoura')
      await shot(page, `escuro-receita-${viewport.name}`)
    })
  })
}
