import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import type { RecipeUpdate, StepIn } from '../api/types'
import { RequireAuth } from '../session/guards'
import { installFakeYouTube } from '../test/fakeYouTube'
import { makeMe, makeRecipe } from '../test/fixtures'
import { apiError, json, mockApi, type RecordedRequest } from '../test/http'
import { Route, renderApp } from '../test/render'
import { BookPage } from './BookPage'
import { RecipePage } from './RecipePage'

function renderRecipe() {
  return renderApp(
    <>
      <Route
        path="/receitas/:id"
        element={
          <RequireAuth>
            <RecipePage />
          </RequireAuth>
        }
      />
      <Route path="/livro" element={<BookPage />} />
    </>,
    { route: '/receitas/rec-1' },
  )
}

/** PATCH que devolve a receita com as mudanças aplicadas, como o backend. */
function patchEcho(request: RecordedRequest) {
  const body = request.body as RecipeUpdate
  const steps = body.steps?.map((step: StepIn, index) => ({
    order: index + 1,
    text: step.text,
    video_timestamp_s: step.video_timestamp_s ?? null,
  }))
  return json(200, makeRecipe({ ...(body as object), ...(steps ? { steps } : {}) }))
}

const baseRoutes = {
  'GET /api/auth/me': () => json(200, makeMe()),
  'GET /api/recipes/rec-1': () => json(200, makeRecipe()),
  'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
  'GET /api/recipes/tags': () => json(200, { tags: [] }),
}

async function openEditor() {
  await userEvent.click(await screen.findByRole('button', { name: 'Editar' }))
  return screen.findByRole('form', { name: /Bolo de cenoura com calda/ })
}

describe('edição da receita', () => {
  beforeEach(() => installFakeYouTube())

  it('edita campos, ingredientes, passos e tags e salva com PATCH', async () => {
    const { calls } = mockApi({ ...baseRoutes, 'PATCH /api/recipes/rec-1': patchEcho })
    renderRecipe()
    await openEditor()

    const title = screen.getByLabelText('Título')
    expect(title).toHaveFocus()
    await userEvent.clear(title)
    await userEvent.type(title, 'Bolo da vovó')
    await userEvent.clear(screen.getByLabelText('Preparo (min)'))
    await userEvent.type(screen.getByLabelText('Preparo (min)'), '25')
    await userEvent.selectOptions(screen.getByLabelText('Dificuldade'), 'Média')

    // Novo ingrediente (herda o grupo do último) e remoção do "sal".
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar ingrediente' }))
    const novo = screen.getByRole('group', { name: 'Ingrediente 5' })
    await waitFor(() => expect(within(novo).getByLabelText('Quantidade')).toHaveFocus())
    await userEvent.type(within(novo).getByLabelText('Quantidade'), '1')
    await userEvent.type(within(novo).getByLabelText('Unidade'), 'colher de sopa')
    await userEvent.type(within(novo).getByLabelText('Ingrediente'), 'fermento')
    await userEvent.click(screen.getByRole('button', { name: 'Remover ingrediente 4 (sal)' }))
    expect(screen.queryByRole('group', { name: 'Ingrediente 5' })).not.toBeInTheDocument()

    // Passo 3 sobe para o lugar do 2; tempo do passo 1 em mm:ss.
    await userEvent.click(screen.getByRole('button', { name: 'Mover passo 3 para cima' }))
    const passo1 = screen.getByRole('group', { name: 'Passo 1' })
    await userEvent.clear(within(passo1).getByLabelText('Tempo no vídeo'))
    await userEvent.type(within(passo1).getByLabelText('Tempo no vídeo'), '0:30')

    // Dica nova e tags.
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar dica' }))
    await userEvent.type(screen.getByLabelText('Dica 2'), 'Use cenouras bem laranjas.')
    await userEvent.click(screen.getByRole('button', { name: 'Remover a tag sobremesa' }))
    await userEvent.type(screen.getByLabelText('Nova tag'), '#Festa{Enter}')
    expect(screen.getByRole('list', { name: 'Tags da receita' })).toHaveTextContent('#festa')

    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Bolo da vovó' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Alterações salvas.')).toBeInTheDocument()
    const patch = calls.find((call) => call.method === 'PATCH')
    expect(patch?.headers.get('X-Requested-With')).toBeTruthy()
    const body = patch?.body as RecipeUpdate
    expect(body).toMatchObject({
      title: 'Bolo da vovó',
      prep_time_min: 25,
      cook_time_min: 40,
      difficulty: 'média',
      servings: '12 fatias',
      tips: ['Teste o fermento antes.', 'Use cenouras bem laranjas.'],
      tags: ['bolo', 'festa'],
    })
    expect(body.ingredients?.map((item) => item.name)).toEqual([
      'farinha de trigo',
      'cenoura',
      'chocolate em pó',
      'fermento',
    ])
    expect(body.ingredients?.[3]).toEqual({
      name: 'fermento',
      quantity: '1',
      unit: 'colher de sopa',
      note: null,
      group: 'massa',
    })
    expect(body.steps).toEqual([
      { text: 'Preaqueça o forno a 180 °C.', video_timestamp_s: 30 },
      { text: 'Sirva com a calda.', video_timestamp_s: null },
      { text: 'Bata as cenouras com os ovos.', video_timestamp_s: 113 },
    ])
  })

  it('valida antes de enviar e leva ao campo com erro', async () => {
    const { calls } = mockApi({ ...baseRoutes, 'PATCH /api/recipes/rec-1': patchEcho })
    renderRecipe()
    await openEditor()

    await userEvent.clear(screen.getByLabelText('Título'))
    const passo2 = screen.getByRole('group', { name: 'Passo 2' })
    const tempo = within(passo2).getByLabelText('Tempo no vídeo')
    await userEvent.clear(tempo)
    await userEvent.type(tempo, '1:5')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    const summary = await screen.findByRole('alert')
    expect(summary).toHaveTextContent('Falta corrigir 2 campos antes de salvar')
    await waitFor(() => expect(summary).toHaveFocus())
    expect(screen.getByLabelText('Título')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Título')).toHaveAccessibleDescription('Dê um nome à receita.')
    expect(tempo).toHaveAccessibleDescription(/Use minutos:segundos, como 1:53/)

    await userEvent.click(within(summary).getByRole('link', { name: /Passo 2, tempo no vídeo/ }))
    await waitFor(() => expect(tempo).toHaveFocus())
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false)
  })

  it('mostra no campo certo os erros de validação do servidor (422)', async () => {
    mockApi({
      ...baseRoutes,
      'PATCH /api/recipes/rec-1': () =>
        json(422, {
          error: {
            code: 'validation_error',
            message: 'Alguns dados enviados são inválidos.',
            details: [
              {
                field: 'body.ingredients.1.note',
                type: 'string_too_long',
                message: 'String should have at most 200 characters',
              },
            ],
          },
        }),
    })
    renderRecipe()
    await openEditor()
    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    const row = screen.getByRole('group', { name: 'Ingrediente 2' })
    await waitFor(() =>
      expect(within(row).getByLabelText('Observação')).toHaveAccessibleDescription(
        'Use no máximo 200 caracteres.',
      ),
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Ingrediente 2, observação')
  })

  it('um erro sem campo (ex.: rede) aparece no resumo e o formulário continua', async () => {
    mockApi({
      ...baseRoutes,
      'PATCH /api/recipes/rec-1': () => apiError(500, 'internal_error', 'Erro do servidor.'),
    })
    renderRecipe()
    await openEditor()
    await userEvent.type(screen.getByLabelText('Título'), '!')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Erro do servidor.')
    expect(screen.getByLabelText('Título')).toHaveValue('Bolo de cenoura com calda!')
  })

  it('cancelar com alterações pede confirmação', async () => {
    const { calls } = mockApi(baseRoutes)
    renderRecipe()
    await openEditor()
    await userEvent.type(screen.getByLabelText('Título'), ' especial')
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    const dialog = screen.getByRole('alertdialog', { name: 'Descartar as alterações?' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Continuar editando' }))
    expect(screen.getByLabelText('Título')).toHaveValue('Bolo de cenoura com calda especial')

    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Descartar' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Bolo de cenoura com calda' }),
    ).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false)
  })

  it('cancelar sem alterações volta direto para a receita', async () => {
    mockApi(baseRoutes)
    renderRecipe()
    await openEditor()
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Editar' })).toBeInTheDocument()
  })

  it('avisa ao sair da página com alterações não salvas', async () => {
    mockApi(baseRoutes)
    renderRecipe()
    await openEditor()
    await userEvent.type(screen.getByLabelText('Título'), ' especial')

    await userEvent.click(screen.getByRole('link', { name: '← Meu livro' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Sair sem salvar?' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Continuar editando' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/receitas/rec-1')
    expect(screen.getByLabelText('Título')).toHaveValue('Bolo de cenoura com calda especial')

    await userEvent.click(screen.getByRole('link', { name: '← Meu livro' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Sair sem salvar' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/))
  })

  it('sem alterações, sair da página não pergunta nada', async () => {
    mockApi(baseRoutes)
    renderRecipe()
    await openEditor()
    await userEvent.click(screen.getByRole('link', { name: '← Meu livro' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/))
  })
})

describe('sessão expirada no meio da edição', () => {
  beforeEach(() => installFakeYouTube())

  it('salvar com 401 leva ao login sem perder o rascunho, que volta ao reabrir a receita', async () => {
    let loggedIn = true
    const { calls } = mockApi({
      ...baseRoutes,
      'GET /api/auth/me': () =>
        loggedIn ? json(200, makeMe()) : apiError(401, 'unauthorized', 'Entre na sua conta.'),
      'PATCH /api/recipes/rec-1': () => {
        loggedIn = false
        return apiError(401, 'unauthorized', 'Entre na sua conta.')
      },
    })
    const first = renderRecipe()
    await openEditor()
    await userEvent.clear(screen.getByLabelText('Título'))
    await userEvent.type(screen.getByLabelText('Título'), 'Bolo editado longo')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    // O 401 desloga a interface e manda para o login (com volta para a receita)...
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/entrar?next=%2Freceitas%2Frec-1'),
    )
    expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(1)
    first.unmount()

    // ...e, depois de entrar de novo, a receita reabre no editor com o que tinha sido digitado.
    loggedIn = true
    mockApi({ ...baseRoutes, 'PATCH /api/recipes/rec-1': patchEcho })
    renderRecipe()
    expect(await screen.findByText(/Recuperamos as alterações/)).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toHaveValue('Bolo editado longo')

    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Bolo editado longo' }),
    ).toBeInTheDocument()
    expect(window.sessionStorage.length).toBe(0)
  })

  it('cancelar o rascunho recuperado descarta o que estava guardado', async () => {
    mockApi(baseRoutes)
    const first = renderRecipe()
    await openEditor()
    await userEvent.type(screen.getByLabelText('Título'), ' especial')
    first.unmount()

    mockApi(baseRoutes)
    renderRecipe()
    expect(await screen.findByLabelText('Título')).toHaveValue('Bolo de cenoura com calda especial')
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Descartar' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Bolo de cenoura com calda' }),
    ).toBeInTheDocument()
    expect(window.sessionStorage.length).toBe(0)
  })
})

describe('restaurar a receita original', () => {
  beforeEach(() => installFakeYouTube())

  it('pede confirmação e mostra a receita restaurada', async () => {
    const { calls } = mockApi({
      ...baseRoutes,
      'GET /api/recipes/rec-1': () => json(200, makeRecipe({ title: 'Meu bolo editado' })),
      'POST /api/recipes/rec-1/reset': () => json(200, makeRecipe()),
    })
    renderRecipe()

    await userEvent.click(await screen.findByRole('button', { name: 'Restaurar receita original' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Restaurar a receita original?' })
    expect(within(dialog).getByText(/Suas notas, a avaliação e o favorito continuam/)).toBeVisible()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Restaurar' }))

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Bolo de cenoura com calda' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Receita restaurada/)).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    const reset = calls.find((call) => call.path === '/api/recipes/rec-1/reset')
    expect(reset?.headers.get('X-Requested-With')).toBeTruthy()
  })

  it('mostra o erro (ex.: sem receita original) dentro da confirmação', async () => {
    mockApi({
      ...baseRoutes,
      'POST /api/recipes/rec-1/reset': () =>
        apiError(409, 'no_original_recipe', 'A receita original desse vídeo não está disponível.'),
    })
    renderRecipe()

    await userEvent.click(await screen.findByRole('button', { name: 'Restaurar receita original' }))
    await userEvent.click(screen.getByRole('button', { name: 'Restaurar' }))

    const dialog = screen.getByRole('alertdialog')
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'A receita original desse vídeo não está disponível.',
    )
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Restaurar receita original' })).toHaveFocus(),
    )
  })
})
