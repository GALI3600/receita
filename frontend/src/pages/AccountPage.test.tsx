import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { RedirectIfAuthenticated, RequireAuth } from '../session/guards'
import { makeMe } from '../test/fixtures'
import { apiError, json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { AccountPage } from './AccountPage'

const routes = (
  <>
    <Route
      index
      element={
        <RedirectIfAuthenticated>
          <h1>Apresentação</h1>
        </RedirectIfAuthenticated>
      }
    />
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
          <AccountPage />
        </RequireAuth>
      }
    />
    <Route path="/entrar" element={<h1>Entrar</h1>} />
  </>
)

describe('AccountPage', () => {
  it('sair da conta termina na apresentação, não no login', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/auth/logout': () => new Response(null, { status: 204 }),
    })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Sair da conta' }))

    expect(await screen.findByRole('heading', { name: 'Apresentação' })).toBeInTheDocument()
    // Espera um pouco: nenhum redirecionamento tardio para /livro ou /entrar.
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/)
    const logout = calls.find((call) => call.path === '/api/auth/logout')
    expect(logout?.headers.get('X-Requested-With')).toBeTruthy()
  })

  it('se o logout falhar, a sessão continua e o erro aparece', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/auth/logout': () => apiError(500, 'internal_error', 'Erro interno.'),
    })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Sair da conta' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não conseguimos sair da conta')
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/conta$/)
    expect(screen.getByRole('heading', { name: 'Olá, Ana Souza' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sair da conta' })).toBeEnabled()
  })

  it('logout com a sessão já expirada (401) também sai', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/auth/logout': () => apiError(401, 'unauthorized', 'Entre na sua conta.'),
    })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Sair da conta' }))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/))
  })
})
