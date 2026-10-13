import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { apiError, json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { ResetPasswordPage } from './ResetPasswordPage'
import { VerifyEmailPage } from './VerifyEmailPage'

// Os tokens de confirmação e de redefinição saem da barra de endereço (e do histórico) assim
// que a página abre; o pedido continua usando o token guardado.
describe('páginas com token na URL', () => {
  it('redefinir senha tira o token da URL e ainda o usa ao salvar', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => apiError(401, 'unauthorized', 'Entre na sua conta.'),
      'POST /api/auth/reset-password': () => new Response(null, { status: 204 }),
    })
    renderApp(<Route path="/redefinir-senha" element={<ResetPasswordPage />} />, {
      route: '/redefinir-senha?token=segredo-123',
    })

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(/^\/redefinir-senha$/),
    )
    await userEvent.type(screen.getByLabelText('Senha nova'), 'uma-senha-nova')
    await userEvent.type(screen.getByLabelText('Repita a senha nova'), 'uma-senha-nova')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar a senha nova' }))

    expect(await screen.findByText(/Pronto! Por segurança/)).toBeInTheDocument()
    const reset = calls.find((call) => call.path === '/api/auth/reset-password')
    expect(reset?.body).toEqual({ token: 'segredo-123', password: 'uma-senha-nova' })
  })

  it('confirmar e-mail tira o token da URL e confirma uma vez', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => apiError(401, 'unauthorized', 'Entre na sua conta.'),
      'POST /api/auth/verify': () => new Response(null, { status: 204 }),
    })
    renderApp(<Route path="/verificar-email" element={<VerifyEmailPage />} />, {
      route: '/verificar-email?token=segredo-456',
    })

    expect(await screen.findByRole('heading', { name: 'E-mail confirmado!' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/verificar-email$/)
    const verifies = calls.filter((call) => call.path === '/api/auth/verify')
    expect(verifies).toHaveLength(1)
    expect(verifies[0].body).toEqual({ token: 'segredo-456' })
  })

  it('sem token continua pedindo o link', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, null) })
    renderApp(<Route path="/redefinir-senha" element={<ResetPasswordPage />} />, {
      route: '/redefinir-senha',
    })
    expect(await screen.findByRole('heading', { name: 'Link incompleto' })).toBeInTheDocument()
  })
})
