import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { RequireAuth } from '../session/guards'
import { makeMe, makeRecipe } from '../test/fixtures'
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
  it('favoritas e busca se combinam e ficam na URL', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [makeRecipe()], next_cursor: null }),
    })
    renderBook('/livro')
    const lastList = () => calls.filter((call) => call.path === '/api/recipes').at(-1)

    await userEvent.click(await screen.findByRole('button', { name: 'Favoritas' }))
    await userEvent.type(screen.getByLabelText('Buscar'), 'cenoura')

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/livro?favoritas=1&q=cenoura'),
    )
    await waitFor(() => {
      const query = lastList()?.query
      expect(query?.get('favorite')).toBe('true')
      expect(query?.get('q')).toBe('cenoura')
    })

    await userEvent.click(screen.getAllByRole('button', { name: 'Limpar filtros' })[0])
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/))
    expect(screen.getByLabelText('Buscar')).toHaveValue('')
  })

  it('o botão "×" limpa a busca na hora, sem esperar o debounce', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [makeRecipe()], next_cursor: null }),
    })
    renderBook('/livro?q=cenoura')
    const lastList = () => calls.filter((call) => call.path === '/api/recipes').at(-1)

    expect(await screen.findByLabelText('Buscar')).toHaveValue('cenoura')
    await waitFor(() => expect(lastList()?.query.get('q')).toBe('cenoura'))

    await userEvent.click(screen.getByRole('button', { name: 'Limpar busca' }))

    expect(screen.getByLabelText('Buscar')).toHaveValue('')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/))
    await waitFor(() => expect(lastList()?.query.get('q')).toBeNull())
    expect(screen.queryByRole('button', { name: 'Limpar busca' })).not.toBeInTheDocument()
  })

  it('abre com os filtros da URL', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [makeRecipe()], next_cursor: null }),
    })
    renderBook('/livro?favoritas=1&q=bolo')

    expect(await screen.findByRole('button', { name: 'Favoritas' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByLabelText('Buscar')).toHaveValue('bolo')
  })

  it('livro vazio convida a importar a primeira receita', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
    })
    renderBook('/livro')

    expect(
      await screen.findByRole('heading', { name: 'Seu livro ainda está em branco' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Importar minha primeira receita' })).toHaveAttribute(
      'href',
      '/nova',
    )
  })

  it('livro vazio esconde a busca e os filtros (não há o que filtrar)', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
    })
    renderBook('/livro')
    await screen.findByRole('heading', { name: 'Seu livro ainda está em branco' })
    expect(screen.queryByRole('search')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Buscar')).not.toBeInTheDocument()
  })

  it('busca maior que o limite da API não vira erro', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
    })
    renderBook(`/livro?q=${'a'.repeat(250)}`)

    const search = await screen.findByLabelText('Buscar')
    expect(search).toHaveAttribute('maxLength', '200')
    expect(search).toHaveValue('a'.repeat(200))
    await waitFor(() => expect(calls.some((call) => call.path === '/api/recipes')).toBe(true))
    const list = calls.filter((call) => call.path === '/api/recipes')
    for (const call of list) {
      expect(call.query.get('q')).toBe('a'.repeat(200))
    }
  })

  it('mostra esqueletos enquanto carrega', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => new Promise<Response>(() => undefined),
    })
    renderBook('/livro')
    expect(await screen.findByText('Carregando as receitas…')).toBeInTheDocument()
  })
})
