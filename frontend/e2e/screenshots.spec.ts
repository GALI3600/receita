import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type Page } from '@playwright/test'

import { createVerifiedUser } from './support/backend'

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
  })
}
