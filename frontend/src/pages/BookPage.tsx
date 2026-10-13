import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useRecipeTags, useRecipes } from '../api/queries'
import type { RecipeFilters } from '../api/types'
import { RecipeCard, RecipeCardSkeleton } from '../components/recipe/RecipeCard'
import { HeartIcon } from '../components/recipe/RecipeMeta'
import { Alert, Spinner } from '../components/ui'
import { describeError } from '../lib/errors'
import { useDebouncedValue } from '../lib/useDebouncedValue'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useCurrentUser } from '../session/context'

function EmptyBook() {
  return (
    <div className="page-sheet mx-auto max-w-xl px-6 py-12 text-center">
      <p className="ornament font-serif text-2xl" aria-hidden="true">
        ❦
      </p>
      <h2 className="mt-4 text-2xl font-semibold">Seu livro ainda está em branco</h2>
      <p className="mt-2 text-ink-soft">
        Cole o link de um vídeo de receita do YouTube e a gente escreve a receita para você, com
        ingredientes, passo a passo e o vídeo junto.
      </p>
      <Link to="/nova" className="btn-primary mt-6">
        Importar minha primeira receita
      </Link>
    </div>
  )
}

export function BookPage() {
  useDocumentTitle('Meu livro')
  const user = useCurrentUser()
  const searchId = useId()
  const tagId = useId()
  const location = useLocation()
  const deletedTitle = (location.state as { deleted?: string } | null)?.deleted
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const tag = params.get('tag') ?? ''
  const favorite = params.get('favoritas') === '1'
  const [search, setSearch] = useState(q)
  const debouncedSearch = useDebouncedValue(search, 350)
  const lastAppliedSearch = useRef(debouncedSearch)

  // `q` mudou por fora (voltar do navegador, limpar filtros): o campo acompanha.
  const [syncedQ, setSyncedQ] = useState(q)
  if (q !== syncedQ) {
    setSyncedQ(q)
    if (q !== search.trim()) setSearch(q)
  }

  // A busca vai para a URL depois que a pessoa para de digitar (dá para voltar e compartilhar).
  useEffect(() => {
    if (debouncedSearch === lastAppliedSearch.current) return
    lastAppliedSearch.current = debouncedSearch
    if (debouncedSearch.trim() === q) return
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (debouncedSearch.trim()) next.set('q', debouncedSearch.trim())
        else next.delete('q')
        return next
      },
      { replace: true },
    )
  }, [debouncedSearch, q, setParams])

  const filters: RecipeFilters = useMemo(
    () => ({ q: q || undefined, tag: tag || undefined, favorite: favorite || undefined }),
    [q, tag, favorite],
  )
  const recipes = useRecipes(filters)
  const items = useMemo(
    () => recipes.data?.pages.flatMap((page) => page.items) ?? [],
    [recipes.data],
  )
  const hasFilters = Boolean(q || tag || favorite)
  const fetchMoreError = recipes.isFetchNextPageError ? recipes.error : null

  // As opções vêm de todas as tags do livro (não só das receitas carregadas com a busca atual),
  // com as das receitas na tela como reserva caso a lista de tags não carregue.
  const bookTags = useRecipeTags()
  const tagOptions = useMemo(() => {
    const all = new Set([...(bookTags.data ?? []), ...items.flatMap((recipe) => recipe.tags)])
    if (tag) all.add(tag)
    return [...all].sort((a, b) => a.localeCompare(b, 'pt-BR'))
  }, [bookTags.data, items, tag])

  function updateParam(key: string, value: string | null) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    })
  }

  function clearFilters() {
    setSearch('')
    setParams({})
  }

  const firstName = user.name.split(/\s+/)[0]

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Livro de receitas de {firstName}</p>
          <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">Meu livro</h1>
        </div>
        <Link to="/nova" className="btn-primary">
          <span aria-hidden="true">+</span> Nova receita
        </Link>
      </div>

      {deletedTitle && (
        <Alert tone="success" className="mt-6">
          “{deletedTitle}” foi excluída do seu livro.
        </Alert>
      )}

      <div
        role="search"
        className="mt-6 flex flex-col gap-3 rounded-lg border border-line bg-card/70 p-3 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <label htmlFor={searchId} className="mb-1 block text-sm font-semibold">
            Buscar
          </label>
          <input
            id={searchId}
            type="search"
            className="field-input"
            placeholder="Título, ingrediente ou tag"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="sm:w-48">
          <label htmlFor={tagId} className="mb-1 block text-sm font-semibold">
            Tag
          </label>
          <select
            id={tagId}
            className="field-input"
            value={tag}
            onChange={(e) => updateParam('tag', e.target.value || null)}
          >
            <option value="">Todas</option>
            {tagOptions.map((option) => (
              <option key={option} value={option}>
                #{option}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          aria-pressed={favorite}
          onClick={() => updateParam('favoritas', favorite ? null : '1')}
          className={`btn min-h-11 rounded-lg border px-4 ${
            favorite
              ? 'border-terracotta bg-terracotta-tint text-terracotta-dark'
              : 'border-ink/55 bg-card text-ink hover:bg-paper-deep'
          }`}
        >
          <HeartIcon filled={favorite} className="size-5 text-terracotta" />
          Favoritas
        </button>
      </div>

      <p className="sr-only" aria-live="polite">
        {recipes.isSuccess &&
          (items.length === 0
            ? 'Nenhuma receita encontrada.'
            : `${items.length} ${items.length === 1 ? 'receita' : 'receitas'} na lista.`)}
      </p>

      {hasFilters && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink-soft">
          <span>Filtrando:</span>
          {q && <span className="tag-chip">“{q}”</span>}
          {tag && <span className="tag-chip">#{tag}</span>}
          {favorite && <span className="tag-chip">favoritas</span>}
          <button
            type="button"
            className="link inline-flex min-h-11 items-center"
            onClick={clearFilters}
          >
            Limpar filtros
          </button>
        </div>
      )}

      <div className="mt-6">
        {recipes.isPending ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3" role="status">
            <span className="sr-only">Carregando as receitas…</span>
            {Array.from({ length: 6 }, (_, i) => (
              <RecipeCardSkeleton key={i} />
            ))}
          </div>
        ) : recipes.isError ? (
          <Alert tone="error" title="Não conseguimos abrir o seu livro">
            <p>{describeError(recipes.error)}</p>
            <button type="button" className="btn-secondary mt-3" onClick={() => recipes.refetch()}>
              Tentar de novo
            </button>
          </Alert>
        ) : items.length === 0 ? (
          hasFilters ? (
            <div className="py-12 text-center">
              <h2 className="text-2xl font-semibold">Nenhuma receita encontrada</h2>
              <p className="mt-2 text-ink-soft">Tente outra palavra ou limpe os filtros.</p>
              <button type="button" className="btn-secondary mt-4" onClick={clearFilters}>
                Limpar filtros
              </button>
            </div>
          ) : (
            <EmptyBook />
          )
        ) : (
          <>
            <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3" aria-label="Receitas">
              {items.map((recipe) => (
                <li key={recipe.id}>
                  <RecipeCard recipe={recipe} onTagClick={(value) => updateParam('tag', value)} />
                </li>
              ))}
            </ul>
            {recipes.hasNextPage && (
              <div className="mt-8 text-center">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => recipes.fetchNextPage()}
                  disabled={recipes.isFetchingNextPage}
                >
                  {recipes.isFetchingNextPage ? (
                    <>
                      <Spinner /> Carregando…
                    </>
                  ) : (
                    'Carregar mais receitas'
                  )}
                </button>
              </div>
            )}
            {fetchMoreError && (
              <Alert tone="error" className="mt-4">
                {describeError(fetchMoreError)}
              </Alert>
            )}
          </>
        )}
      </div>
    </div>
  )
}
