import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { LoginPage } from '../pages/LoginPage'
import { makeMe } from '../test/fixtures'
import { apiError, json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { RedirectIfAuthenticated, RequireAuth } from './guards'

const routes = (
  <>
    <Route
      path="/nova"
      element={
        <RequireAuth>
          <h1>Nova receita</h1>
        </RequireAuth>
      }
    />
    <Route path="/livro" element={<h1>Livro</h1>} />
    <Route
      path="/entrar"
      element={
        <RedirectIfAuthenticated>
          <LoginPage />
        </RedirectIfAuthenticated>
      }
    />
  </>
)

describe('rotas protegidas', () => {
  it('sem sessão, vai para /entrar com o caminho de volta em next', async () => {
    mockApi({ 'GET /api/auth/me': () => apiError(401, 'unauthorized', 'Entre na sua conta.') })
    renderApp(routes, { route: '/nova?import=abc' })

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/entrar?next=%2Fnova%3Fimport%3Dabc',
      ),
    )
    expect(screen.getByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
  })

  it('depois do login volta para o next', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => apiError(401, 'unauthorized', 'Entre na sua conta.'),
      'POST /api/auth/login': () => json(200, makeMe()),
    })
    renderApp(routes, { route: '/entrar?next=%2Fnova%3Fimport%3Dabc' })

    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'uma-senha-boa')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('heading', { name: 'Nova receita' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/nova?import=abc')
    const login = calls.find((call) => call.path === '/api/auth/login')
    expect(login?.body).toEqual({ email: 'ana@example.com', password: 'uma-senha-boa' })
    expect(login?.headers.get('X-Requested-With')).toBeTruthy()
  })

  it('ignora um next externo (open redirect) e vai para o livro', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderApp(routes, { route: '/entrar?next=%2F%2Fevil.example%2Fphish' })

    expect(await screen.findByRole('heading', { name: 'Livro' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/)
  })

  it.each([
    '%2F.%2F%2Fevil.example%2Fphish',
    '%2Fa%2F..%2F%2Fevil.example',
    '%2F%252e%2F%2Fevil.example',
  ])(
    'next que normaliza para //host (%s) também vai para o livro, sem tela em branco',
    async (next) => {
      mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
      renderApp(routes, { route: `/entrar?next=${next}` })

      expect(await screen.findByRole('heading', { name: 'Livro' })).toBeInTheDocument()
      expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/)
    },
  )

  it('login errado mostra a mensagem do backend', async () => {
    mockApi({
      'GET /api/auth/me': () => apiError(401, 'unauthorized', 'Entre na sua conta.'),
      'POST /api/auth/login': () =>
        apiError(401, 'invalid_credentials', 'E-mail ou senha incorretos.'),
    })
    renderApp(routes, { route: '/entrar' })

    await userEvent.type(await screen.findByLabelText('E-mail'), 'ana@example.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
  })
})
