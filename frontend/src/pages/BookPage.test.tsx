import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RequireAuth } from '../session/guards'
import { makeMe } from '../test/fixtures'
import { json, mockApi } from '../test/http'
import { Route, renderApp } from '../test/render'
import { BookPage } from './BookPage'

function renderBook(route: string) {
  return renderApp(
    <Route
      path="/livro"
      element={
        <RequireAuth>
          <BookPage />
        </RequireAuth>
      }
    />,
    { route },
  )
}

describe('BookPage', () => {
  it('o filtro de tag lista todas as tags do livro, mesmo com uma busca sem resultados', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
      'GET /api/recipes/tags': () =>
        json(200, {
          tags: [
            { name: 'bolo', count: 2 },
            { name: 'chocolate', count: 1 },
          ],
        }),
    })
    renderBook('/livro?q=zzzzzz')

    expect(
      await screen.findByRole('heading', { name: 'Nenhuma receita encontrada' }),
    ).toBeInTheDocument()
    const select = screen.getByLabelText('Tag')
    await waitFor(() =>
      expect(
        within(select)
          .getAllByRole('option')
          .map((o) => o.textContent),
      ).toEqual(['Todas', '#bolo', '#chocolate']),
    )
    const list = calls.find((call) => call.path === '/api/recipes')
    expect(list?.query.get('q')).toBe('zzzzzz')
  })
})
