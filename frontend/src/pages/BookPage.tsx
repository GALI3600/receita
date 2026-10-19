import { useEffect, useId, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useRecipes } from '../api/queries'
import type { RecipeFilters } from '../api/types'
import { RecipeCard, RecipeCardSkeleton } from '../components/recipe/RecipeCard'
import { HeartIcon } from '../components/recipe/RecipeMeta'
import { Alert, Spinner } from '../components/ui'
import { describeError } from '../lib/errors'
import { charCount } from '../lib/text'
import { useDebouncedValue } from '../lib/useDebouncedValue'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useCurrentUser } from '../session/context'

// Limite do GET /recipes (backend/app/api/recipes.py): acima dele a API responde 422.
const SEARCH_MAX = 200

/** Corta o texto em `max` caracteres (contados como o backend: code points). */
function clip(text: string, max: number): string {
  return charCount(text) > max ? Array.from(text).slice(0, max).join('') : text
}

function ClearIcon() {
  return (
    <svg viewBox="0 0 20 20" className="size-4" aria-hidden="true">
      <path
        d="M5 5l10 10M15 5 5 15"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

function OpenBookArt() {
  return (
    <svg viewBox="0 0 160 96" className="mx-auto h-24 w-40 text-terracotta" aria-hidden="true">
      <path
        d="M80 20c-18-10-40-12-64-6v70c24-6 46-4 64 6 18-10 40-12 64-6V14c-24-6-46-4-64 6z"
        fill="var(--color-card)"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <path d="M80 20v70" stroke="currentColor" strokeWidth="2.5" />
      <g stroke="var(--color-line)" strokeWidth="2.5" strokeLinecap="round">
        <path d="M30 34h36M30 44h30M30 54h34M30 64h24" />
        <path d="M94 34h36M94 44h22" />
      </g>
      <path
        d="M104 58c4-8 18-8 22 0M100 60h30l-3 10h-24z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const EMPTY_STEPS = [
  'Copie o link de um vídeo de receita no YouTube.',
  'Cole em “Nova receita” e espere a gente escrever.',
  'Cozinhe com a receita e o vídeo lado a lado.',
]

function EmptyBook() {
  return (
    <div className="page-sheet mx-auto max-w-xl px-6 py-10 text-center sm:px-10">
      <OpenBookArt />
      <h2 className="mt-4 text-2xl font-semibold sm:text-3xl">Seu livro ainda está em branco</h2>
      <p className="mt-2 text-ink-soft">
        Que tal começar pela receita que você sempre quis aprender? A gente transforma o vídeo em
        ingredientes e passo a passo, com o vídeo junto.
      </p>
      <ol className="mx-auto mt-6 max-w-sm space-y-2 text-left">
        {EMPTY_STEPS.map((step, index) => (
          <li key={step} className="flex items-baseline gap-3">
            <span className="font-serif text-xl font-semibold text-terracotta" aria-hidden="true">
              {index + 1}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      <Link to="/nova" className="btn-primary mt-8">
        Importar minha primeira receita
      </Link>
    </div>
  )
}

export function BookPage() {
  useDocumentTitle('Meu livro')
  const user = useCurrentUser()
  const searchId = useId()
  const location = useLocation()
  const deletedTitle = (location.state as { deleted?: string } | null)?.deleted
  const [params, setParams] = useSearchParams()
  // Um link com busca maior que o limite da API não vira erro: a busca é cortada.
  const q = clip(params.get('q') ?? '', SEARCH_MAX)
  const favorite = params.get('favoritas') === '1'
  const [search, setSearch] = useState(q)
  const debouncedSearch = useDebouncedValue(search, 350)

  // `q` mudou por fora (voltar do navegador, limpar filtros): o campo acompanha.
  const [syncedQ, setSyncedQ] = useState(q)
  if (q !== syncedQ) {
    setSyncedQ(q)
    if (q !== search.trim()) setSearch(q)
  }

  // A busca vai para a URL depois que a pessoa para de digitar (dá para voltar e compartilhar).
  useEffect(() => {
    // `debouncedSearch` ainda não assentou no valor atual de `search` (ex.: alguém limpou a
    // busca na hora pelo botão "×", que já atualizou a URL direto): esperar o debounce também
    // alcançar esse valor, senão este efeito reaplicaria um valor antigo por cima.
    if (debouncedSearch !== search) return
    const trimmed = debouncedSearch.trim()
    if (trimmed === q) return
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (trimmed) next.set('q', trimmed)
        else next.delete('q')
        return next
      },
      { replace: true },
    )
  }, [debouncedSearch, search, q, setParams])

  /** Limpa a busca na hora (sem esperar o debounce): usado pelo botão "×" do campo. */
  function clearSearch() {
    setSearch('')
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('q')
        return next
      },
      { replace: true },
    )
  }

  const filters: RecipeFilters = useMemo(
    () => ({ q: q || undefined, favorite: favorite || undefined }),
    [q, favorite],
  )
  const recipes = useRecipes(filters)
  const items = useMemo(
    () => recipes.data?.pages.flatMap((page) => page.items) ?? [],
    [recipes.data],
  )
  const hasFilters = Boolean(q || favorite)
  // Livro vazio (sem filtros): não há o que buscar nem filtrar.
  const emptyBook = recipes.isSuccess && items.length === 0 && !hasFilters
  const fetchMoreError = recipes.isFetchNextPageError ? recipes.error : null

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

      {!emptyBook && (
        <div
          role="search"
          aria-label="Filtrar receitas"
          className="mt-6 rounded-lg border border-line bg-card/70 p-3 sm:p-4"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label htmlFor={searchId} className="mb-1 block text-sm font-semibold">
                Buscar
              </label>
              <div className="relative">
                <input
                  id={searchId}
                  type="text"
                  className="field-input pr-9"
                  placeholder="Título ou ingrediente"
                  maxLength={SEARCH_MAX}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {search && (
                  <button
                    type="button"
                    onClick={clearSearch}
                    aria-label="Limpar busca"
                    className="absolute inset-y-0 right-1 flex items-center px-2 text-ink-soft hover:text-ink"
                  >
                    <ClearIcon />
                  </button>
                )}
              </div>
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
        </div>
      )}

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
                  <RecipeCard recipe={recipe} />
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
