import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Recipe, RecipeUpdate } from '../api/types'
import { checkedStorageKey } from '../lib/checkedIngredients'
import { RequireAuth } from '../session/guards'
import { installFakeYouTube } from '../test/fakeYouTube'
import { makeMe, makeRecipe } from '../test/fixtures'
import { apiError, json, mockApi, type RecordedRequest } from '../test/http'
import { Route, renderApp } from '../test/render'
import { RecipePage } from './RecipePage'

function renderRecipe() {
  return renderApp(
    <Route
      path="/receitas/:id"
      element={
        <RequireAuth>
          <RecipePage />
        </RequireAuth>
      }
    />,
    { route: '/receitas/rec-1' },
  )
}

function routes(recipe: Recipe = makeRecipe()) {
  return {
    'GET /api/auth/me': () => json(200, makeMe()),
    'GET /api/recipes/rec-1': () => json(200, recipe),
    'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
    'GET /api/recipes/tags': () => json(200, { tags: [] }),
    'PATCH /api/recipes/rec-1': (request: RecordedRequest) =>
      json(200, { ...recipe, ...(request.body as RecipeUpdate) }),
  }
}

function patches(calls: RecordedRequest[]) {
  return calls.filter((call) => call.method === 'PATCH').map((call) => call.body)
}

describe('notas pessoais', () => {
  beforeEach(() => installFakeYouTube())

  it('salvam sozinhas depois de uma pausa na digitação', async () => {
    const { calls } = mockApi(routes())
    renderRecipe()

    const notes = await screen.findByLabelText('Minhas notas')
    await userEvent.type(notes, 'Menos açúcar  ')
    expect(screen.getByText('Alterações por salvar…')).toBeInTheDocument()

    await waitFor(() => expect(patches(calls)).toEqual([{ user_notes: 'Menos açúcar' }]), {
      timeout: 3000,
    })
    expect(await screen.findByText(/^Salvo às \d{2}:\d{2}\.$/)).toBeInTheDocument()
    const patch = calls.find((call) => call.method === 'PATCH')
    expect(patch?.headers.get('X-Requested-With')).toBeTruthy()
  })

  it('sair do campo salva na hora, sem pedido repetido depois', async () => {
    const { calls } = mockApi(routes())
    renderRecipe()

    const notes = await screen.findByLabelText('Minhas notas')
    await userEvent.type(notes, 'Forno mais baixo')
    await userEvent.tab()
    await waitFor(() => expect(patches(calls)).toEqual([{ user_notes: 'Forno mais baixo' }]))
    await new Promise((resolve) => setTimeout(resolve, 1300))
    expect(patches(calls)).toHaveLength(1)
  })

  it('apagar as notas manda null', async () => {
    const { calls } = mockApi(routes(makeRecipe({ user_notes: 'antiga' })))
    renderRecipe()

    const notes = await screen.findByLabelText('Minhas notas')
    expect(notes).toHaveValue('antiga')
    await userEvent.clear(notes)
    await userEvent.tab()
    await waitFor(() => expect(patches(calls)).toEqual([{ user_notes: null }]))
  })

  it('erro ao salvar avisa e permite tentar de novo', async () => {
    const recipe = makeRecipe()
    const { calls } = mockApi({
      ...routes(recipe),
      'PATCH /api/recipes/rec-1': [
        () => apiError(500, 'internal_error', 'Erro do servidor.'),
        (request: RecordedRequest) => json(200, { ...recipe, ...(request.body as object) }),
      ],
    })
    renderRecipe()

    await userEvent.type(await screen.findByLabelText('Minhas notas'), 'Teste')
    await userEvent.tab()
    expect(await screen.findByText(/Não conseguimos salvar: Erro do servidor/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByText(/^Salvo às/)).toBeInTheDocument()
    expect(patches(calls)).toHaveLength(2)
  })

  it('com a sessão expirada o texto não se perde: volta depois do login e é salvo', async () => {
    let loggedIn = true
    mockApi({
      ...routes(),
      'GET /api/auth/me': () =>
        loggedIn ? json(200, makeMe()) : apiError(401, 'unauthorized', 'Entre na sua conta.'),
      'PATCH /api/recipes/rec-1': () => {
        loggedIn = false
        return apiError(401, 'unauthorized', 'Entre na sua conta.')
      },
    })
    const first = renderRecipe()
    await userEvent.type(await screen.findByLabelText('Minhas notas'), 'Usei canastra')
    await userEvent.tab()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/entrar?next='))
    first.unmount()

    loggedIn = true
    const { calls } = mockApi(routes())
    renderRecipe()
    expect(await screen.findByLabelText('Minhas notas')).toHaveValue('Usei canastra')
    expect(screen.getByText('Recuperamos uma nota que você não tinha salvado.')).toBeVisible()
    await waitFor(() => expect(patches(calls)).toEqual([{ user_notes: 'Usei canastra' }]), {
      timeout: 3000,
    })
    expect(await screen.findByText(/^Salvo às/)).toBeInTheDocument()
    await waitFor(() => expect(window.sessionStorage.length).toBe(0))
  })

  it('conta caracteres como o backend: emoji vale 1', async () => {
    const { calls } = mockApi(routes(makeRecipe({ user_notes: '🍰'.repeat(4999) })))
    renderRecipe()

    const notes = await screen.findByLabelText('Minhas notas')
    expect(screen.getByText('4.999/5.000')).toBeInTheDocument()
    await userEvent.type(notes, 'x')
    await userEvent.tab()
    expect(notes).not.toHaveAttribute('aria-invalid')
    await waitFor(() => expect(patches(calls)).toHaveLength(1))
  })

  it('texto longo demais não é enviado', async () => {
    const { calls } = mockApi(routes(makeRecipe({ user_notes: 'x'.repeat(5000) })))
    renderRecipe()

    const notes = await screen.findByLabelText('Minhas notas')
    await userEvent.type(notes, 'y')
    await userEvent.tab()
    expect(notes).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(/As notas podem ter até 5.000 caracteres/)).toBeInTheDocument()
    expect(patches(calls)).toHaveLength(0)
  })
})

describe('avaliação e favorito', () => {
  beforeEach(() => installFakeYouTube())

  it('escolher estrelas manda a avaliação e dá para limpar', async () => {
    const { calls } = mockApi(routes())
    renderRecipe()

    const group = await screen.findByRole('group', { name: 'Sua avaliação' })
    const four = within(group).getByRole('radio', { name: '4 estrelas, Muito boa' })
    await userEvent.click(four)
    expect(four).toBeChecked()
    await waitFor(() => expect(patches(calls)).toEqual([{ rating: 4 }]))

    // Teclado: setas mudam a escolha no grupo de rádios.
    await userEvent.keyboard('{ArrowRight}')
    await waitFor(() => expect(patches(calls)).toEqual([{ rating: 4 }, { rating: 5 }]))

    await userEvent.click(screen.getByRole('button', { name: 'Limpar avaliação' }))
    await waitFor(() => expect(patches(calls).at(-1)).toEqual({ rating: null }))
    expect(within(group).getByText('Ainda sem avaliação')).toBeInTheDocument()
  })

  it('a avaliação volta atrás se a API recusar', async () => {
    mockApi({
      ...routes(makeRecipe({ rating: 2 })),
      'PATCH /api/recipes/rec-1': () => apiError(500, 'internal_error', 'Erro do servidor.'),
    })
    renderRecipe()

    const group = await screen.findByRole('group', { name: 'Sua avaliação' })
    expect(within(group).getByRole('radio', { name: /^2 estrelas/ })).toBeChecked()
    await userEvent.click(within(group).getByRole('radio', { name: /^5 estrelas/ }))
    expect(await screen.findByText('Erro do servidor.')).toBeInTheDocument()
    expect(within(group).getByRole('radio', { name: /^2 estrelas/ })).toBeChecked()
  })

  it('favoritar é otimista e desfaz se a API recusar', async () => {
    let release: () => void = () => undefined
    mockApi({
      ...routes(),
      'PATCH /api/recipes/rec-1': () =>
        new Promise<Response>((resolve) => {
          release = () => resolve(apiError(500, 'internal_error', 'Erro do servidor.'))
        }),
    })
    renderRecipe()

    await userEvent.click(await screen.findByRole('button', { name: 'Favoritar' }))
    // Antes da resposta já aparece como favorita (o rótulo diz o estado, sem aria-pressed).
    const favorited = screen.getByRole('button', { name: 'Favorita: tirar dos favoritos' })
    expect(favorited).not.toHaveAttribute('aria-pressed')
    // O coração pula porque a pessoa acabou de favoritar.
    expect(favorited.querySelector('svg')).toHaveClass('heart-pop')
    release()
    expect(await screen.findByRole('button', { name: 'Favoritar' })).not.toHaveAttribute(
      'aria-pressed',
    )
    expect(screen.getByText('Erro do servidor.')).toBeInTheDocument()
  })

  it('receita já favorita abre sem a animação do coração', async () => {
    mockApi(routes(makeRecipe({ is_favorite: true })))
    renderRecipe()
    const button = await screen.findByRole('button', { name: 'Favorita: tirar dos favoritos' })
    expect(button.querySelector('svg')).not.toHaveClass('heart-pop')
  })
})

describe('escala de porções', () => {
  beforeEach(() => installFakeYouTube())

  it('+ e − ajustam as quantidades numéricas e mantêm "a gosto"', async () => {
    mockApi(routes(makeRecipe({ servings: '2 porções' })))
    renderRecipe()

    const control = await screen.findByRole('group', { name: 'Rende' })
    expect(within(control).getByRole('status')).toHaveTextContent('2 porções')
    await userEvent.click(within(control).getByRole('button', { name: 'Mais porções' }))
    expect(within(control).getByRole('status')).toHaveTextContent('3 porções')

    // A observação não é quantidade: fica como está.
    expect(
      screen.getByRole('checkbox', { name: '3 xícaras farinha de trigo, peneirada' }),
    ).toBeVisible()
    expect(screen.getByRole('checkbox', { name: /^4 1\/2 cenoura/ })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: /^3\/4 xícara chocolate em pó/ })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: 'sal, a gosto' })).toBeVisible()

    await userEvent.click(within(control).getByRole('button', { name: 'Menos porções' }))
    await userEvent.click(within(control).getByRole('button', { name: 'Menos porções' }))
    expect(within(control).getByRole('status')).toHaveTextContent('1 porção')
    expect(screen.getByRole('checkbox', { name: /^1 xícara farinha de trigo/ })).toBeVisible()
    expect(within(control).getByRole('button', { name: 'Menos porções' })).toBeDisabled()

    await userEvent.click(within(control).getByRole('button', { name: 'Voltar para 2 porções' }))
    expect(within(control).getByRole('status')).toHaveTextContent('2 porções')
    expect(screen.getByRole('checkbox', { name: /^2 xícaras farinha de trigo/ })).toBeVisible()
  })

  it('a escala não mexe na observação nem na unidade sem quantidade, mas esconde equivalências', async () => {
    const ingredient = { quantity: null, unit: null, note: null, group: null }
    mockApi(
      routes(
        makeRecipe({
          servings: '2 porções',
          ingredients: [
            { ...ingredient, name: 'leite', quantity: '1', unit: 'copo', note: 'copo de 300 ml' },
            // Receita antiga: unidade sem quantidade.
            { ...ingredient, name: 'queijo', unit: 'fatia', note: 'para servir' },
            {
              ...ingredient,
              name: 'farinha',
              quantity: '200',
              unit: 'g',
              note: 'peneirada, ≈ 1⅔ xícara',
            },
          ],
        }),
      ),
    )
    renderRecipe()
    expect(
      await screen.findByRole('checkbox', { name: '200 g farinha, peneirada, ≈ 1⅔ xícara' }),
    ).toBeVisible()

    const control = await screen.findByRole('group', { name: 'Rende' })
    await userEvent.click(within(control).getByRole('button', { name: 'Mais porções' }))
    await userEvent.click(within(control).getByRole('button', { name: 'Mais porções' }))
    expect(within(control).getByRole('status')).toHaveTextContent('4 porções')
    expect(screen.getByRole('checkbox', { name: '2 copos leite, copo de 300 ml' })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: 'queijo, fatia, para servir' })).toBeVisible()
    // A equivalência vale para a quantidade original: sai quando a receita é escalada.
    expect(screen.getByRole('checkbox', { name: '400 g farinha, peneirada' })).toBeVisible()
  })

  it('rendimento sem número não tem controle de porções', async () => {
    mockApi(routes(makeRecipe({ servings: 'uma travessa' })))
    renderRecipe()

    expect(await screen.findByText('uma travessa')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mais porções' })).not.toBeInTheDocument()
  })
})

describe('ingredientes marcados', () => {
  beforeEach(() => installFakeYouTube())

  it('ficam guardados no navegador, por receita, e dá para limpar', async () => {
    mockApi(routes())
    const first = renderRecipe()

    const farinha = await screen.findByRole('checkbox', { name: /farinha de trigo/ })
    await userEvent.click(farinha)
    expect(farinha).toBeChecked()
    expect(screen.getByText('1 de 4 separados.')).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(checkedStorageKey('rec-1')) ?? '[]')).toEqual([
      '0:farinha de trigo',
    ])
    first.unmount()

    renderRecipe()
    const again = await screen.findByRole('checkbox', { name: /farinha de trigo/ })
    expect(again).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Limpar marcações' }))
    expect(again).not.toBeChecked()
    expect(again).toHaveFocus()
    expect(localStorage.getItem(checkedStorageKey('rec-1'))).toBeNull()
  })

  it('marcações que não batem mais com a lista (receita editada) são ignoradas', async () => {
    localStorage.setItem(checkedStorageKey('rec-1'), JSON.stringify(['0:outro', '1:cenoura']))
    mockApi(routes())
    renderRecipe()

    expect(await screen.findByRole('checkbox', { name: /^3 cenoura/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /farinha de trigo/ })).not.toBeChecked()
  })

  it('sem localStorage (bloqueado) a página funciona do mesmo jeito', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    mockApi(routes())
    renderRecipe()

    const farinha = await screen.findByRole('checkbox', { name: /farinha de trigo/ })
    await userEvent.click(farinha)
    expect(farinha).toBeChecked()
  })
})

describe('impressão', () => {
  beforeEach(() => installFakeYouTube())

  it('a folha impressa traz o link do vídeo e as notas', async () => {
    const print = vi.fn()
    vi.stubGlobal('print', print)
    mockApi(routes(makeRecipe({ user_notes: 'Usei forma de 22 cm.' })))
    renderRecipe()

    await userEvent.click(await screen.findByRole('button', { name: 'Imprimir' }))
    expect(print).toHaveBeenCalled()
    expect(
      screen.getByText(/Receita do vídeo .*https:\/\/www\.youtube\.com\/watch\?v=-pRC-FQXLEI/),
    ).toBeInTheDocument()
    expect(screen.getByText('Usei forma de 22 cm.', { selector: 'p' })).toBeInTheDocument()
  })
})
