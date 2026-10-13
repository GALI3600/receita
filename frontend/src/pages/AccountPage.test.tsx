import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { RedirectIfAuthenticated, RequireAuth } from '../session/guards'
import { makeMe } from '../test/fixtures'
import { apiError, json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { AccountPage } from './AccountPage'
import { LandingPage } from './LandingPage'

const routes = (
  <>
    <Route
      index
      element={
        <RedirectIfAuthenticated>
          <LandingPage />
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

    expect(
      await screen.findByRole('heading', { level: 1, name: /Do vídeo para a receita/ }),
    ).toBeInTheDocument()
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

  it('mostra a cota com barra de progresso', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderApp(routes, { route: '/conta' })

    const bar = await screen.findByRole('progressbar', { name: /Cota de receitas novas/ })
    expect(bar).toHaveAttribute('aria-valuenow', '2')
    expect(bar).toHaveAttribute('aria-valuemax', '10')
    expect(screen.getByText(/Você usou/)).toHaveTextContent('Você usou 2 de 10; restam 8.')
  })

  it('exportar baixa o JSON da conta', async () => {
    const created: Blob[] = []
    const createObjectURL = vi.fn((blob: Blob) => {
      created.push(blob)
      return 'blob:receita'
    })
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const data = { user: { email: 'ana@example.com' }, recipes: [], imports: [] }
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/account/export': () => json(200, data),
    })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Exportar meus dados' }))

    expect(await screen.findByText(/receita-meus-dados.json foi baixado/)).toBeInTheDocument()
    expect(calls.some((call) => call.path === '/api/account/export')).toBe(true)
    expect(click).toHaveBeenCalled()
    const anchor = click.mock.contexts[0] as HTMLAnchorElement
    expect(anchor.download).toBe('receita-meus-dados.json')
    expect(JSON.parse(await created[0].text())).toEqual(data)
  })

  it('erro ao exportar aparece na tela', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/account/export': () => apiError(500, 'internal_error', 'Erro do servidor.'),
    })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Exportar meus dados' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Erro do servidor.')
  })

  it('excluir a conta exige senha e confirmação e termina na apresentação', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'DELETE /api/account': [
        () => apiError(403, 'invalid_password', 'Senha incorreta.'),
        () => new Response(null, { status: 204 }),
      ],
    })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Quero excluir minha conta' }))
    const password = screen.getByLabelText('Sua senha')
    await waitFor(() => expect(password).toHaveFocus())
    const submit = screen.getByRole('button', { name: 'Excluir minha conta para sempre' })

    // Sem senha nem confirmação: nada é enviado.
    await userEvent.click(submit)
    expect(password).toHaveAccessibleDescription('Digite sua senha para confirmar.')
    await userEvent.type(password, 'errada')
    await userEvent.click(submit)
    const confirm = screen.getByRole('checkbox', { name: /serão apagadas para sempre/ })
    expect(confirm).toHaveAccessibleDescription('Marque a caixa para confirmar.')
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    // Senha errada: erro no campo.
    await userEvent.click(confirm)
    await userEvent.click(submit)
    await waitFor(() => expect(password).toHaveAccessibleDescription('Senha incorreta.'))

    await userEvent.clear(password)
    await userEvent.type(password, 'senha-certa')
    await userEvent.click(submit)

    expect(await screen.findByText('Sua conta foi excluída')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/)
    const deletes = calls.filter((call) => call.method === 'DELETE')
    expect(deletes.map((call) => call.body)).toEqual([
      { password: 'errada' },
      { password: 'senha-certa' },
    ])
    expect(deletes[1].headers.get('X-Requested-With')).toBeTruthy()
  })

  it('cancelar a exclusão fecha o formulário', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderApp(routes, { route: '/conta' })

    await userEvent.click(await screen.findByRole('button', { name: 'Quero excluir minha conta' }))
    const section = screen.getByRole('region', { name: 'Excluir conta' })
    await userEvent.click(within(section).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByLabelText('Sua senha')).not.toBeInTheDocument()
  })
})
