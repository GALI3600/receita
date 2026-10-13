import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Cookie, type Page } from '@playwright/test'

import { createVerifiedUser, resetRateLimits } from './support/backend'

// Acessibilidade automática (axe-core, regras WCAG 2.1 A e AA) nas páginas principais, no tema
// claro e no "livro à noite", no desktop e no celular. O iframe do YouTube fica de fora (não é
// nosso).
let sessionCookies: Cookie[] = []
let emptyCookies: Cookie[] = []

test.beforeAll(async ({ browser }) => {
  resetRateLimits()
  const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'
  const seeded = await browser.newContext({ baseURL })
  await createVerifiedUser(seeded.request, { seed: true })
  sessionCookies = await seeded.cookies()
  await seeded.close()
  const empty = await browser.newContext({ baseURL })
  await createVerifiedUser(empty.request)
  emptyCookies = await empty.cookies()
  await empty.close()
})

async function expectNoViolations(page: Page, label: string) {
  await page.evaluate(() => document.fonts.ready)
  // Contraste medido no estado final, não no meio de uma animação de entrada (menu, diálogo).
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  )
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .exclude('iframe')
    .analyze()
  const summary = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact}): ${violation.nodes
        .slice(0, 3)
        .map((node) => node.target.join(' '))
        .join(' | ')}`,
  )
  expect(summary, `violações em ${label}`).toEqual([])
}

const SCHEMES = ['light', 'dark'] as const
const VIEWPORTS = [
  { name: '1280', width: 1280, height: 900 },
  { name: '360', width: 360, height: 780 },
] as const

for (const scheme of SCHEMES) {
  for (const viewport of VIEWPORTS) {
    test.describe(`${scheme} ${viewport.name}px`, () => {
      test.use({
        colorScheme: scheme,
        viewport: { width: viewport.width, height: viewport.height },
      })

      test('páginas públicas', async ({ page }) => {
        for (const [path, heading] of [
          ['/', /Do vídeo para a receita/],
          ['/entrar', 'Entrar'],
          ['/cadastro', 'Criar conta'],
          ['/esqueci-senha', /senha/i],
          ['/pagina-que-nao-existe', 'Esta página não está no livro'],
        ] as const) {
          await page.goto(path)
          await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
          await expectNoViolations(page, path)
        }
      })

      test('livro, receita, edição, nova e conta', async ({ page, context }) => {
        await context.addCookies(sessionCookies)
        await page.goto('/livro')
        await expect(page.getByRole('list', { name: 'Receitas' }).getByRole('article')).toHaveCount(
          3,
        )
        await expectNoViolations(page, '/livro')

        if (viewport.width < 640) {
          await page.getByRole('button', { name: 'Menu' }).click()
          await expect(page.locator('#menu-celular')).toBeVisible()
          await expectNoViolations(page, 'menu do celular')
          await page.keyboard.press('Escape')
        }

        await page.getByRole('link', { name: 'Pão de queijo de liquidificador' }).click()
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        await expect(page.locator('[data-player-status]')).not.toHaveAttribute(
          'data-player-status',
          'loading',
          { timeout: 30_000 },
        )
        await page.getByRole('checkbox').first().check()
        await page.getByRole('button', { name: 'Mais porções' }).click()
        await expectNoViolations(page, 'receita')

        await page.getByRole('button', { name: 'Restaurar receita original' }).click()
        await expect(page.getByRole('alertdialog')).toBeVisible()
        await expectNoViolations(page, 'confirmação de restaurar')
        await page.getByRole('button', { name: 'Cancelar' }).click()

        await page.getByRole('button', { name: 'Editar' }).click()
        await page.getByLabel('Título').fill('')
        await page.getByRole('button', { name: 'Salvar alterações' }).click()
        await expect(page.getByRole('alert')).toBeVisible()
        await expectNoViolations(page, 'edição com erros')
        await page.getByRole('button', { name: 'Cancelar' }).click()
        await page.getByRole('button', { name: 'Descartar' }).click()

        await page.goto('/nova')
        await expect(page.getByLabel('Link do vídeo no YouTube')).toBeVisible()
        await expectNoViolations(page, '/nova')

        await page.goto('/conta')
        await page.getByRole('button', { name: 'Quero excluir minha conta' }).click()
        await page.getByRole('button', { name: 'Excluir minha conta para sempre' }).click()
        await expect(page.getByText('Digite sua senha para confirmar.')).toBeVisible()
        await expectNoViolations(page, '/conta')
      })

      test('livro vazio', async ({ page, context }) => {
        await context.addCookies(emptyCookies)
        await page.goto('/livro')
        await expect(
          page.getByRole('heading', { name: 'Seu livro ainda está em branco' }),
        ).toBeVisible()
        await expectNoViolations(page, 'livro vazio')
      })
    })
  }
}
