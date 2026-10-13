import { screen, waitFor, within } from '@testing-library/react'
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
    const tags = screen.getByRole('group', { name: 'Tags' })
    await waitFor(() =>
      expect(
        within(tags)
          .getAllByRole('button')
          .map((button) => button.textContent),
      ).toEqual(['Todas', '#bolo', '#chocolate']),
    )
    const list = calls.find((call) => call.path === '/api/recipes')
    expect(list?.query.get('q')).toBe('zzzzzz')
  })

  it('tags, favoritas e busca se combinam e ficam na URL', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [makeRecipe()], next_cursor: null }),
      'GET /api/recipes/tags': () =>
        json(200, {
          tags: [
            { name: 'bolo', count: 1 },
            { name: 'sobremesa', count: 1 },
          ],
        }),
    })
    renderBook('/livro')
    const tags = await screen.findByRole('group', { name: 'Tags' })
    const lastList = () => calls.filter((call) => call.path === '/api/recipes').at(-1)

    await userEvent.click(await within(tags).findByRole('button', { name: '#bolo' }))
    expect(within(tags).getByRole('button', { name: '#bolo' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Favoritas' }))
    await userEvent.type(screen.getByLabelText('Buscar'), 'cenoura')

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/livro?tag=bolo&favoritas=1&q=cenoura',
      ),
    )
    await waitFor(() => {
      const query = lastList()?.query
      expect(query?.get('tag')).toBe('bolo')
      expect(query?.get('favorite')).toBe('true')
      expect(query?.get('q')).toBe('cenoura')
    })

    // Clicar de novo na tag escolhida tira o filtro.
    await userEvent.click(within(tags).getByRole('button', { name: '#bolo' }))
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/livro?favoritas=1&q=cenoura'),
    )
    await userEvent.click(screen.getAllByRole('button', { name: 'Limpar filtros' })[0])
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/livro$/))
    expect(screen.getByLabelText('Buscar')).toHaveValue('')
  })

  it('abre com os filtros da URL e a tag do card filtra', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [makeRecipe()], next_cursor: null }),
      'GET /api/recipes/tags': () => json(200, { tags: [{ name: 'bolo', count: 1 }] }),
    })
    renderBook('/livro?favoritas=1&q=bolo')

    expect(await screen.findByRole('button', { name: 'Favoritas' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByLabelText('Buscar')).toHaveValue('bolo')
    const card = await screen.findByRole('article')
    await userEvent.click(within(card).getByRole('button', { name: 'Filtrar pela tag sobremesa' }))
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/livro?favoritas=1&q=bolo&tag=sobremesa',
      ),
    )
    await waitFor(() =>
      expect(
        calls
          .filter((call) => call.path === '/api/recipes')
          .at(-1)
          ?.query.get('tag'),
      ).toBe('sobremesa'),
    )
  })

  it('livro vazio convida a importar a primeira receita', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
      'GET /api/recipes/tags': () => json(200, { tags: [] }),
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
      'GET /api/recipes/tags': () => json(200, { tags: [] }),
    })
    renderBook('/livro')
    await screen.findByRole('heading', { name: 'Seu livro ainda está em branco' })
    expect(screen.queryByRole('search')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Buscar')).not.toBeInTheDocument()
  })

  it('busca e tag maiores que os limites da API não viram erro', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [], next_cursor: null }),
      'GET /api/recipes/tags': () => json(200, { tags: [] }),
    })
    renderBook(`/livro?q=${'a'.repeat(250)}&tag=${'b'.repeat(41)}`)

    const search = await screen.findByLabelText('Buscar')
    expect(search).toHaveAttribute('maxLength', '200')
    expect(search).toHaveValue('a'.repeat(200))
    await waitFor(() => expect(calls.some((call) => call.path === '/api/recipes')).toBe(true))
    const list = calls.filter((call) => call.path === '/api/recipes')
    for (const call of list) {
      expect(call.query.get('q')).toBe('a'.repeat(200))
      expect(call.query.get('tag')).toBeNull()
    }
  })

  it('no celular, poucas tags à vista; as outras em "Mais"', async () => {
    const tags = Array.from({ length: 10 }, (_, i) => ({ name: `tag${i}`, count: 1 }))
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => json(200, { items: [makeRecipe({ tags: [] })], next_cursor: null }),
      'GET /api/recipes/tags': () => json(200, { tags }),
    })
    renderBook('/livro')

    // jsdom: matchMedia não casa com (min-width: 640px), como num celular.
    const group = await screen.findByRole('group', { name: 'Tags' })
    await waitFor(() => expect(within(group).getByRole('button', { name: '#tag0' })).toBeVisible())
    expect(within(group).queryByRole('button', { name: '#tag9' })).not.toBeInTheDocument()
    await userEvent.click(within(group).getByRole('button', { name: /^Mais \d+ tags$/ }))
    expect(within(group).getByRole('button', { name: '#tag9' })).toBeInTheDocument()
  })

  it('mostra esqueletos enquanto carrega', async () => {
    mockApi({
      'GET /api/auth/me': () => json(200, makeMe()),
      'GET /api/recipes': () => new Promise<Response>(() => undefined),
      'GET /api/recipes/tags': () => json(200, { tags: [] }),
    })
    renderBook('/livro')
    expect(await screen.findByText('Carregando as receitas…')).toBeInTheDocument()
  })
})
