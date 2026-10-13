import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { RequireAuth } from '../session/guards'
import { FakePlayer, installFakeYouTube } from '../test/fakeYouTube'
import { makeMe, makeRecipe } from '../test/fixtures'
import { json, mockApi } from '../test/http'
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

describe('RecipePage', () => {
  beforeEach(() => installFakeYouTube())

  it('mostra a receita como página de livro', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes/rec-1': () => json(200, makeRecipe()),
    })
    renderRecipe()

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Bolo de cenoura com calda' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Bolo fofinho de liquidificador.')).toBeInTheDocument()
    expect(screen.getByText('12 fatias')).toBeInTheDocument()
    expect(screen.getByText('1 h')).toBeInTheDocument() // total: 20 + 40 min
    expect(screen.getByText('Teste o fermento antes.')).toBeInTheDocument()

    // Ingredientes agrupados, na ordem em que os grupos aparecem.
    const massa = screen.getByRole('region', { name: 'massa' })
    const calda = screen.getByRole('region', { name: 'calda' })
    expect(within(massa).getAllByRole('checkbox')).toHaveLength(3)
    expect(within(calda).getByLabelText(/chocolate em pó/)).toBeInTheDocument()
    expect(within(massa).getByLabelText(/sal \(a gosto\)/)).toBeInTheDocument()

    const farinha = within(massa).getByRole('checkbox', { name: /farinha de trigo/ })
    await userEvent.click(farinha)
    expect(farinha).toBeChecked()

    // Passos numerados; o passo sem tempo não tem botão.
    const steps = within(screen.getByRole('region', { name: 'Modo de preparo' })).getAllByRole(
      'listitem',
    )
    expect(steps).toHaveLength(3)
    expect(within(steps[2]).queryByRole('button')).not.toBeInTheDocument()
  })

  it('clicar no tempo do passo pula o vídeo e marca o passo atual', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes/rec-1': () => json(200, makeRecipe()),
    })
    renderRecipe()
    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))
    const player = FakePlayer.active[0]
    player.ready()

    const button = screen.getByRole('button', { name: 'Ver o passo 2 no vídeo, em 1:53' })
    await userEvent.click(button)

    expect(player.seekTo).toHaveBeenCalledWith(113, true)
    expect(player.playVideo).toHaveBeenCalled()
    expect(button.closest('li')).toHaveAttribute('aria-current', 'step')
  })

  it('favoritar manda PATCH com o header anti-CSRF', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes/rec-1': () => json(200, makeRecipe()),
      'PATCH /api/recipes/rec-1': () => json(200, makeRecipe({ is_favorite: true })),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
    })
    renderRecipe()

    await userEvent.click(await screen.findByRole('button', { name: 'Favoritar' }))

    expect(await screen.findByRole('button', { name: 'Favorita' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    const patch = calls.find((call) => call.method === 'PATCH')
    expect(patch?.body).toEqual({ is_favorite: true })
    expect(patch?.headers.get('X-Requested-With')).toBeTruthy()
  })

  it('excluir pede confirmação e volta para o livro', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes/rec-1': () => json(200, makeRecipe()),
      'DELETE /api/recipes/rec-1': () => new Response(null, { status: 204 }),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
    })
    renderRecipe()

    await userEvent.click(await screen.findByRole('button', { name: 'Excluir' }))
    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/Excluir “Bolo de cenoura com calda”/)).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Sim, excluir' }))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/livro'))
    expect(await screen.findByText(/foi excluída do seu livro/)).toBeInTheDocument()
  })

  it('receita inexistente mostra "não encontrada"', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes/rec-1': () =>
        json(404, { error: { code: 'not_found', message: 'Receita não encontrada.' } }),
    })
    renderRecipe()

    expect(
      await screen.findByRole('heading', { name: 'Receita não encontrada' }),
    ).toBeInTheDocument()
  })
})
