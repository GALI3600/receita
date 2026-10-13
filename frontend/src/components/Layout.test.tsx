import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { RequireAuth } from '../session/guards'
import { makeMe } from '../test/fixtures'
import { json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { Layout } from './Layout'

function renderLayout() {
  return renderApp(
    <Route element={<Layout />}>
      <Route
        path="/livro"
        element={
          <RequireAuth>
            <h1>Livro</h1>
          </RequireAuth>
        }
      />
      <Route
        path="/conta"
        element={
          <RequireAuth>
            <h1>Conta</h1>
          </RequireAuth>
        }
      />
    </Route>,
    { route: '/livro' },
  )
}

describe('Layout: menu do celular', () => {
  it('abre, navega e fecha; Esc fecha e devolve o foco', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderLayout()

    const button = await screen.findByRole('button', { name: 'Menu' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const panel = document.getElementById('menu-celular')!
    expect(panel).not.toBeVisible()

    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(panel).toBeVisible()
    await userEvent.keyboard('{Escape}')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(button).toHaveFocus()

    await userEvent.click(button)
    const links = panel.querySelectorAll('a')
    expect([...links].map((link) => link.textContent)).toEqual([
      'Meu livro',
      'Nova receita',
      'Conta',
    ])
    expect(links[0]).toHaveAttribute('aria-current', 'page')
    await userEvent.click(links[2])
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/conta'))
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })
})
