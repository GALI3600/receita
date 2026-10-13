import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { onlineManager } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
  afterEach(() => onlineManager.setOnline(true))

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

  it('e-mail não confirmado: avisa, desabilita o envio e não mostra a cota', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe({ email_verified: false })),
    })
    renderNew()

    expect(
      await screen.findByText('Confirme seu e-mail para importar receitas'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reenviar o link' })).toBeEnabled()
    expect(screen.getByLabelText('Link do vídeo no YouTube')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Importar receita' })).toBeDisabled()
    expect(screen.queryByTestId('quota-note')).not.toBeInTheDocument()
    expect(calls.some((call) => call.path === '/api/imports')).toBe(false)
  })

  it('403 email_not_verified (sessão desatualizada) mostra o aviso em destaque', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'POST /api/imports': () =>
        apiError(403, 'email_not_verified', 'Confirme seu e-mail para importar receitas.'),
    })
    renderNew()

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

  it.each([
    ['404', () => apiError(404, 'import_not_found', 'Importação não encontrada.')],
    ['422', () => apiError(422, 'validation_error', 'Dados inválidos.')],
  ])('import com erro %s mostra a mensagem e para o polling', async (_status, handler) => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/imports/nao-existe': handler,
    })
    renderNew('/nova?import=nao-existe')

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 200))
    const polls = calls.filter((call) => call.path === '/api/imports/nao-existe')
    expect(polls).toHaveLength(1)
  })

  it('falha passageira no polling mantém o progresso e continua acompanhando', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/imports/imp-1': [
        () => json(200, makeImport({ status: 'transcribing' })),
        () => apiError(502, 'http_502', 'O servidor está com problemas.'),
        () => apiError(502, 'http_502', 'O servidor está com problemas.'),
        () => json(200, makeImport({ status: 'generating' })),
      ],
    })
    renderNew('/nova?import=imp-1')

    expect(await screen.findByRole('list', { name: 'Etapas da importação' })).toBeInTheDocument()
    expect(await screen.findByText(/Reconectando/)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Etapas da importação' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Importar outro vídeo' })).not.toBeInTheDocument()

    const generating = screen.getByText(/Escrevendo a receita/, { selector: 'li span' })
    await waitFor(() => expect(generating.closest('li')).toHaveAttribute('aria-current', 'step'))
    await waitFor(() => expect(screen.queryByText(/Reconectando/)).not.toBeInTheDocument())
    expect(calls.filter((call) => call.path === '/api/imports/imp-1').length).toBeGreaterThan(3)
  })

  it('o link do vídeo é montado pelo youtube_id, não pela URL digitada', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/imports/imp-1': () =>
        json(200, makeImport({ status: 'fetching', url: 'youtube.com/watch?v=-pRC-FQXLEI' })),
    })
    renderNew('/nova?import=imp-1')

    const link = await screen.findByRole('link', { name: 'youtube.com/watch?v=-pRC-FQXLEI' })
    expect(link).toHaveAttribute('href', 'https://www.youtube.com/watch?v=-pRC-FQXLEI')
  })

  it('429 de cota atualiza a cota mostrada', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': [
        () => json(200, makeMe()),
        () =>
          json(
            200,
            makeMe({
              quota: { used: 10, limit: 10, remaining: 0, resets_at: '2026-10-14T00:00:00Z' },
            }),
          ),
      ],
      'POST /api/imports': () =>
        apiError(429, 'quota_exceeded', 'Você chegou ao limite de receitas novas por hoje.'),
    })
    renderNew()
    expect(await screen.findByTestId('quota-note')).toHaveTextContent('8 receitas novas')

    await submit(URL)

    expect(await screen.findByText('Você usou todas as receitas novas de hoje')).toBeInTheDocument()
    expect(screen.queryByTestId('quota-note')).not.toBeInTheDocument()
    expect(calls.filter((call) => call.path === '/api/auth/me')).toHaveLength(2)
  })

  it('sem internet, o envio falha com aviso em vez de ficar parado em "Enviando…"', async () => {
    const { fetchMock } = mockApi({ 'GET /api/auth/me': () => json(200, makeMe()) })
    renderNew()
    await screen.findByTestId('quota-note')
    onlineManager.setOnline(false)
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await submit(URL)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Não conseguimos falar com o servidor',
    )
    expect(screen.getByRole('button', { name: 'Importar receita' })).toBeEnabled()
  })
})
