import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { RequireAuth } from '../session/guards'
import { makeImport, makeMe } from '../test/fixtures'
import { apiError, json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { NewImportPage } from './NewImportPage'

// Polling acelerado nos testes; a lógica do intervalo tem testes próprios.
vi.mock('../lib/importStatus', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/importStatus')>()
  return {
    ...original,
    pollInterval: (...args: Parameters<typeof original.pollInterval>) =>
      original.pollInterval(...args) === false ? false : 20,
  }
})

function renderNew(route = '/nova') {
  return renderApp(
    <>
      <Route
        path="/nova"
        element={
          <RequireAuth>
            <NewImportPage />
          </RequireAuth>
        }
      />
      <Route path="/receitas/:id" element={<h1>Página da receita</h1>} />
    </>,
    { route },
  )
}

async function submit(url: string) {
  const input = await screen.findByLabelText('Link do vídeo no YouTube')
  await userEvent.type(input, url)
  await userEvent.click(screen.getByRole('button', { name: 'Importar receita' }))
}

const URL = 'https://www.youtube.com/watch?v=-pRC-FQXLEI'

describe('NewImportPage', () => {
  it('mostra a cota restante do dia', async () => {
    mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderNew()
    expect(await screen.findByTestId('quota-note')).toHaveTextContent(
      'Hoje você ainda pode importar 8 receitas novas (de 10).',
    )
  })

  it('valida o link antes de enviar', async () => {
    const { calls } = mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderNew()

    await submit('https://vimeo.com/123')

    expect(await screen.findByText(/só aceitamos vídeos do YouTube/)).toBeInTheDocument()
    expect(calls.some((call) => call.path === '/api/imports')).toBe(false)
  })

  it('acompanha as etapas por polling até a receita ficar pronta', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/imports': () => json(202, makeImport({ status: 'pending', queue_position: 2 })),
      'GET /api/imports/imp-1': [
        () => json(200, makeImport({ status: 'pending', queue_position: 2 })),
        () => json(200, makeImport({ status: 'fetching' })),
        () => json(200, makeImport({ status: 'transcribing' })),
        () => json(200, makeImport({ status: 'generating' })),
        () => json(200, makeImport({ status: 'done', recipe_id: 'rec-9' })),
      ],
    })
    renderNew()

    await submit(URL)

    const post = calls.find((call) => call.method === 'POST')
    expect(post?.body).toEqual({ url: URL })
    expect(post?.headers.get('X-Requested-With')).toBeTruthy()
    // O id vai para a URL, para o progresso sobreviver a um recarregamento.
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/nova?import=imp-1'),
    )
    expect(await screen.findByText('Seu vídeo está na fila: 2º lugar.')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Página da receita' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/receitas/rec-9')
    const polls = calls.filter((call) => call.path === '/api/imports/imp-1')
    expect(polls.length).toBeGreaterThanOrEqual(4)
  })

  it('mostra a etapa atual com aria-current e um aviso para leitores de tela', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/imports/imp-1': () => json(200, makeImport({ status: 'transcribing' })),
    })
    renderNew('/nova?import=imp-1')

    const current = await screen.findByText(/Transcrevendo/, { selector: 'li span' })
    expect(current.closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('Buscando vídeo').closest('li')).toHaveTextContent('(concluído)')
    expect(screen.getByText('Transcrevendo o vídeo.')).toHaveAttribute('aria-live', 'polite')
  })

  it('import concluído na hora (vídeo já existente) vai direto para a receita', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/imports': () => json(200, makeImport({ status: 'done', recipe_id: 'rec-1' })),
    })
    renderNew()

    await submit(URL)

    expect(await screen.findByRole('heading', { name: 'Página da receita' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/receitas/rec-1')
  })

  it('falha mostra a mensagem do backend e permite tentar outro link', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/imports/imp-1': () =>
        json(
          200,
          makeImport({
            status: 'failed',
            error: {
              code: 'llm_missing_key',
              message: 'A geração de receitas não está configurada.',
            },
          }),
        ),
    })
    renderNew('/nova?import=imp-1')

    expect(
      await screen.findByText('A geração de receitas não está configurada.'),
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar outro link' }))
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/nova$/)
    expect(screen.getByLabelText('Link do vídeo no YouTube')).toHaveValue('')
  })

  it('adiado mostra o motivo (orçamento do dia)', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/imports/imp-1': () =>
        json(
          200,
          makeImport({
            status: 'deferred',
            error: { code: 'llm_budget_exceeded', message: 'A sua vai ser escrita amanhã.' },
          }),
        ),
    })
    renderNew('/nova?import=imp-1')

    expect(await screen.findByText('Importação adiada')).toBeInTheDocument()
    expect(screen.getByText('A sua vai ser escrita amanhã.')).toBeInTheDocument()
  })

  it.each([
    ['quota_exceeded', 'Você chegou ao limite de receitas novas por hoje.', '7200', '2 horas'],
    ['rate_limited', 'Muitas tentativas em pouco tempo.', '120', '2 minutos'],
    ['too_many_failed_imports', 'Muitos dos vídeos não viraram receita.', '30', 'alguns segundos'],
  ])('429 %s mostra a mensagem e quando tentar de novo', async (code, message, retry, wait) => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/imports': () => apiError(429, code, message, { 'Retry-After': retry }),
    })
    renderNew()

    await submit(URL)

    expect(
      await screen.findByText(`${message} Você poderá tentar de novo em ${wait}.`),
    ).toBeInTheDocument()
  })

  it('avisa sobre o e-mail não confirmado', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe({ email_verified: false })),
      'POST /api/imports': () =>
        apiError(403, 'email_not_verified', 'Confirme seu e-mail para importar receitas.'),
    })
    renderNew()

    expect(
      await screen.findByText('Confirme seu e-mail para importar receitas'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reenviar o link' })).toBeInTheDocument()

    await submit(URL)
    expect(await screen.findByRole('alert')).toHaveTextContent('Confirme seu e-mail')
  })

  it('erro de link inválido do backend aparece no campo', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/imports': () =>
        apiError(422, 'invalid_url', 'Esse link não parece ser de um vídeo do YouTube.'),
    })
    renderNew()

    await submit('https://www.youtube.com/@canal')

    const input = screen.getByLabelText('Link do vídeo no YouTube')
    await waitFor(() => expect(input).toHaveAttribute('aria-invalid', 'true'))
    expect(input).toHaveAccessibleDescription(/Esse link não parece ser de um vídeo do YouTube/)
  })
})
