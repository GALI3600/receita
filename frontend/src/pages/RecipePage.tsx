import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { isApiError } from '../api/client'
import { useDeleteRecipe, useRecipe, useResetRecipe, useUpdateRecipe } from '../api/queries'
import type { Recipe, Step } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { IngredientList } from '../components/recipe/IngredientList'
import { PersonalNotes } from '../components/recipe/PersonalNotes'
import { RatingStars } from '../components/recipe/RatingStars'
import { DifficultyBadge, HeartIcon } from '../components/recipe/RecipeMeta'
import { ServingsControl } from '../components/recipe/ServingsControl'
import { StepList } from '../components/recipe/StepList'
import { RecipeEditor } from '../components/recipe/editor/RecipeEditor'
import { Alert } from '../components/ui'
import { YouTubePlayer, type YouTubePlayerHandle } from '../components/youtube/YouTubePlayer'
import { isPlayerUnavailable, type PlayerStatus } from '../components/youtube/playerStatus'
import { describeError } from '../lib/errors'
import { formatMinutes, totalMinutes, youtubeWatchUrl } from '../lib/format'
import { parseServings } from '../lib/quantity'
import { useDocumentTitle } from '../lib/useDocumentTitle'

function PencilIcon() {
  return (
    <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
      <path
        d="m12.5 4.5 3 3m-11 8.5.8-3.6 8.4-8.4a1.4 1.4 0 0 1 2 0l.8.8a1.4 1.4 0 0 1 0 2l-8.4 8.4z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function PrinterIcon() {
  return (
    <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
      <path
        d="M6 7V3.5h8V7M6 14H4.5A1.5 1.5 0 0 1 3 12.5v-4A1.5 1.5 0 0 1 4.5 7h11A1.5 1.5 0 0 1 17 8.5v4a1.5 1.5 0 0 1-1.5 1.5H14M6 11.5h8v5H6z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function TimeFacts({ recipe, showServings }: { recipe: Recipe; showServings: boolean }) {
  const total = totalMinutes(recipe)
  const facts = [
    showServings && recipe.servings ? { label: 'Rende', value: recipe.servings } : null,
    recipe.prep_time_min !== null
      ? { label: 'Preparo', value: formatMinutes(recipe.prep_time_min) }
      : null,
    recipe.cook_time_min !== null
      ? { label: 'Forno/fogo', value: formatMinutes(recipe.cook_time_min) }
      : null,
    total !== null && recipe.prep_time_min !== null && recipe.cook_time_min !== null
      ? { label: 'Total', value: formatMinutes(total) }
      : null,
  ].filter((fact) => fact !== null)

  if (facts.length === 0 && !recipe.difficulty) return null
  return (
    <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-line py-4 sm:flex sm:flex-wrap sm:gap-x-10">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dt className="text-xs font-semibold tracking-wider text-ink-soft uppercase">
            {fact.label}
          </dt>
          <dd className="font-serif text-lg">{fact.value}</dd>
        </div>
      ))}
      {recipe.difficulty && (
        <div>
          <dt className="text-xs font-semibold tracking-wider text-ink-soft uppercase">
            Dificuldade
          </dt>
          <dd className="font-serif text-lg">
            <DifficultyBadge difficulty={recipe.difficulty} srLabel={false} />
          </dd>
        </div>
      )}
    </dl>
  )
}

/** Restaurar a original e excluir, cada um com confirmação. */
function RecipeManagement({ recipe, onRestored }: { recipe: Recipe; onRestored: () => void }) {
  const navigate = useNavigate()
  const remove = useDeleteRecipe(recipe.id)
  const reset = useResetRecipe(recipe.id)
  const [confirming, setConfirming] = useState<'reset' | 'delete' | null>(null)

  return (
    <section
      aria-labelledby="gerenciar"
      className="border-t border-dashed border-line pt-6 print:hidden"
    >
      <h2 id="gerenciar" className="text-lg font-semibold">
        Esta receita no seu livro
      </h2>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            reset.reset()
            setConfirming('reset')
          }}
        >
          Restaurar receita original
        </button>
        <button
          type="button"
          className="btn-ghost text-danger hover:text-danger"
          onClick={() => {
            remove.reset()
            setConfirming('delete')
          }}
        >
          Excluir
        </button>
      </div>

      <ConfirmDialog
        open={confirming === 'reset'}
        title="Restaurar a receita original?"
        confirmLabel={reset.isPending ? 'Restaurando…' : 'Restaurar'}
        busy={reset.isPending}
        error={reset.isError ? describeError(reset.error) : null}
        onCancel={() => setConfirming(null)}
        onConfirm={() =>
          reset.mutate(undefined, {
            onSuccess: () => {
              setConfirming(null)
              onRestored()
            },
          })
        }
      >
        Título, ingredientes, passos, dicas e tags voltam a ser os da receita escrita a partir do
        vídeo. Suas notas, a avaliação e o favorito continuam.
      </ConfirmDialog>

      <ConfirmDialog
        open={confirming === 'delete'}
        title={`Excluir “${recipe.title}” do seu livro?`}
        confirmLabel={remove.isPending ? 'Excluindo…' : 'Sim, excluir'}
        tone="danger"
        busy={remove.isPending}
        error={remove.isError ? describeError(remove.error) : null}
        onCancel={() => setConfirming(null)}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () =>
              navigate('/livro', { replace: true, state: { deleted: recipe.title } }),
          })
        }
      >
        Suas anotações e o favorito somem junto.
      </ConfirmDialog>
    </section>
  )
}

/** Quantas porções mostrar; volta ao original quando o rendimento da receita muda. */
function useServingsScale(servings: string | null) {
  const base = parseServings(servings)
  const [state, setState] = useState({ servings, count: base })
  if (state.servings !== servings) setState({ servings, count: base })
  const count = state.servings === servings ? state.count : base
  return {
    base,
    count,
    factor: base && count ? count / base : 1,
    setCount: (value: number) => setState({ servings, count: value }),
  }
}

function RecipeView({
  recipe,
  notice,
  onEdit,
  onRestored,
}: {
  recipe: Recipe
  notice: string | null
  onEdit: () => void
  onRestored: () => void
}) {
  const location = useLocation()
  const playerRef = useRef<YouTubePlayerHandle>(null)
  const [activeStep, setActiveStep] = useState<number | null>(null)
  const [playerStatus, setPlayerStatus] = useState<PlayerStatus>('loading')
  const favorite = useUpdateRecipe(recipe.id)
  const rating = useUpdateRecipe(recipe.id)
  const scale = useServingsScale(recipe.servings)
  const justImported = (location.state as { imported?: boolean } | null)?.imported === true
  // Sem vídeo, os tempos dos passos viram texto e o player deixa de ficar fixo no celular.
  const videoUnavailable = isPlayerUnavailable(playerStatus)
  const videoUrl = youtubeWatchUrl(recipe.video.youtube_id)

  function seekToStep(step: Step) {
    if (step.video_timestamp_s === null) return
    setActiveStep(step.order)
    playerRef.current?.seekTo(step.video_timestamp_s)
  }

  return (
    <>
      {justImported && !notice && (
        <Alert tone="success" className="mb-4 print:hidden">
          Receita salva no seu livro.
        </Alert>
      )}
      {notice && (
        <Alert tone="success" className="mb-4 print:hidden">
          {notice}
        </Alert>
      )}

      <div className="page-sheet recipe-sheet relative px-3 py-6 sm:px-8 sm:py-10 lg:px-12">
        <header className="max-w-3xl">
          {recipe.tags.length > 0 && (
            <p className="eyebrow">{recipe.tags.slice(0, 3).join(' · ')}</p>
          )}
          <h1
            id="titulo-receita"
            tabIndex={-1}
            className="mt-2 text-3xl leading-tight font-semibold focus:outline-none sm:text-5xl"
          >
            {recipe.title}
          </h1>
          {recipe.summary && (
            <p className="mt-3 font-serif text-lg text-ink-soft italic sm:text-xl">
              {recipe.summary}
            </p>
          )}
          <p className="mt-3 text-sm text-ink-soft print:hidden">
            Do vídeo{' '}
            <a className="link font-normal" href={videoUrl} target="_blank" rel="noreferrer">
              {recipe.video.title}
            </a>
            {recipe.video.channel && <> · {recipe.video.channel}</>}
          </p>
          <TimeFacts recipe={recipe} showServings={scale.base === null} />
          <div className="mt-4 flex flex-wrap items-center gap-2 print:hidden">
            <button type="button" className="btn-primary" onClick={onEdit}>
              <PencilIcon />
              Editar
            </button>
            <button
              type="button"
              className="btn-secondary"
              aria-pressed={recipe.is_favorite}
              onClick={() => favorite.mutate({ is_favorite: !recipe.is_favorite })}
            >
              <HeartIcon
                filled={recipe.is_favorite}
                className={`size-5 text-terracotta ${recipe.is_favorite ? 'heart-pop' : ''}`}
              />
              {recipe.is_favorite ? 'Favorita' : 'Favoritar'}
            </button>
            <button type="button" className="btn-ghost" onClick={() => window.print()}>
              <PrinterIcon />
              Imprimir
            </button>
          </div>
          {favorite.isError && (
            <Alert tone="error" className="mt-3 print:hidden">
              {describeError(favorite.error)}
            </Alert>
          )}
        </header>

        {/*
          Celular e tablet (uma coluna): o player fica fixo no topo enquanto se lê a receita; a
          coluna da esquerda vira `contents` para o player poder grudar ao longo da página toda.
          Desktop: player e ingredientes fixos à esquerda; se não couberem na altura da tela, só a
          lista de ingredientes rola, e o player continua à vista. A coluna da direita tem a
          sombra da dobra do livro.
        */}
        <div className="mt-8 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] print:mt-6 print:block">
          <div className="recipe-aside max-lg:contents lg:sticky lg:top-4 lg:flex lg:max-h-[calc(100dvh-2rem)] lg:flex-col lg:gap-8 lg:self-start lg:pr-10 print:pr-0">
            <div
              data-sticky-player={!videoUnavailable}
              className={`print:hidden lg:shrink-0 ${
                videoUnavailable
                  ? ''
                  : 'max-lg:sticky max-lg:top-0 max-lg:z-20 max-lg:-mx-3 max-lg:border-b max-lg:border-line max-lg:bg-card max-lg:px-3 max-lg:py-2 sm:max-lg:-mx-8 sm:max-lg:px-8'
              }`}
            >
              <div className="mx-auto max-lg:max-w-[calc(35dvh*16/9)]">
                <YouTubePlayer
                  ref={playerRef}
                  videoId={recipe.video.youtube_id}
                  title={recipe.video.title}
                  thumbnailUrl={recipe.video.thumbnail_url}
                  onStatusChange={setPlayerStatus}
                />
              </div>
            </div>
            <section
              aria-labelledby="ingredientes"
              className="max-lg:mt-8 lg:flex lg:min-h-0 lg:flex-col print:mt-0"
            >
              <h2 id="ingredientes" className="mb-3 text-2xl font-semibold">
                Ingredientes
              </h2>
              {scale.base !== null && recipe.servings && scale.count !== null && (
                <div className="mb-3">
                  <ServingsControl
                    servings={recipe.servings}
                    base={scale.base}
                    count={scale.count}
                    onChange={scale.setCount}
                  />
                </div>
              )}
              <div className="recipe-ingredients lg:-mr-2 lg:min-h-0 lg:overflow-y-auto lg:pr-2">
                <IngredientList
                  recipeId={recipe.id}
                  ingredients={recipe.ingredients}
                  factor={scale.factor}
                />
              </div>
            </section>
          </div>

          <div className="book-gutter space-y-10 max-lg:mt-10 lg:pl-10 print:mt-8 print:pl-0">
            <section aria-labelledby="preparo">
              <h2 id="preparo" className="mb-1 text-2xl font-semibold">
                Modo de preparo
              </h2>
              {!videoUnavailable && (
                <p className="mb-4 text-sm text-ink-soft print:hidden">
                  Toque no tempo de um passo para ver esse momento no vídeo.
                </p>
              )}
              <StepList
                steps={recipe.steps}
                activeOrder={activeStep}
                onSeek={videoUnavailable ? undefined : seekToStep}
              />
            </section>

            {recipe.tips.length > 0 && (
              <section
                aria-labelledby="dicas"
                className="rounded-lg border border-dashed border-terracotta/40 bg-terracotta-tint/50 px-5 py-4 print:break-inside-avoid print:bg-transparent"
              >
                <h2 id="dicas" className="mb-2 text-xl font-semibold">
                  Dicas
                </h2>
                <ul className="list-disc space-y-1.5 pl-5 marker:text-terracotta">
                  {recipe.tips.map((tip, index) => (
                    <li key={index}>{tip}</li>
                  ))}
                </ul>
              </section>
            )}

            <section aria-labelledby="anotacoes" className="space-y-5 print:hidden">
              <h2 id="anotacoes" className="text-xl font-semibold">
                Suas anotações
              </h2>
              <RatingStars
                value={recipe.rating}
                onChange={(value) => rating.mutate({ rating: value })}
              />
              {rating.isError && <Alert tone="error">{describeError(rating.error)}</Alert>}
              <PersonalNotes key={recipe.id} recipe={recipe} />
            </section>

            {recipe.user_notes && (
              <section aria-labelledby="notas-impressas" className="hidden print:block">
                <h2 id="notas-impressas" className="mb-1 text-xl font-semibold">
                  Anotações
                </h2>
                <p className="whitespace-pre-line">{recipe.user_notes}</p>
              </section>
            )}

            {recipe.tags.length > 0 && (
              <section aria-labelledby="tags" className="print:hidden">
                <h2 id="tags" className="sr-only">
                  Tags
                </h2>
                <ul className="flex flex-wrap gap-2">
                  {recipe.tags.map((tag) => (
                    <li key={tag}>
                      <Link
                        to={`/livro?tag=${encodeURIComponent(tag)}`}
                        className="tag-chip tag-chip-action hover:border-terracotta/50 hover:text-terracotta"
                      >
                        #{tag}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <RecipeManagement recipe={recipe} onRestored={onRestored} />
          </div>
        </div>

        {/* Na folha impressa, de onde veio a receita. */}
        <footer className="mt-10 hidden border-t border-line pt-3 text-sm print:block">
          <p>
            Receita do vídeo “{recipe.video.title}”
            {recipe.video.channel && <> ({recipe.video.channel})</>}: {videoUrl}
          </p>
        </footer>
      </div>
    </>
  )
}

export function RecipePage() {
  const { id = '' } = useParams()
  const recipe = useRecipe(id)
  const [editing, setEditing] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ id: string; text: string } | null>(null)
  const isEditing = editing === id
  useDocumentTitle(
    recipe.data ? (isEditing ? `Editando: ${recipe.data.title}` : recipe.data.title) : 'Receita',
  )

  function focusTitle() {
    requestAnimationFrame(() => {
      document.getElementById('titulo-receita')?.focus({ preventScroll: false })
    })
  }

  if (recipe.isPending) return <RecipeSkeleton />
  if (recipe.isError) {
    const notFound =
      isApiError(recipe.error) && (recipe.error.status === 404 || recipe.error.status === 422)
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <h1 className="text-3xl font-semibold">
          {notFound ? 'Receita não encontrada' : 'Não conseguimos abrir a receita'}
        </h1>
        <p className="mt-2 text-ink-soft">
          {notFound ? 'Ela pode ter sido excluída do seu livro.' : describeError(recipe.error)}
        </p>
        <Link to="/livro" className="btn-primary mt-6">
          Voltar para o livro
        </Link>
      </div>
    )
  }

  return (
    <article className="mx-auto w-full max-w-6xl px-4 py-6 sm:py-10 print:max-w-none print:p-0">
      <p className="mb-4 print:hidden">
        <Link to="/livro" className="link">
          ← Meu livro
        </Link>
      </p>
      {isEditing ? (
        <div className="page-sheet px-3 pt-6 sm:px-8 sm:pt-10 lg:px-12">
          <RecipeEditor
            recipe={recipe.data}
            onClose={(saved) => {
              setEditing(null)
              setNotice(saved ? { id, text: 'Alterações salvas.' } : null)
              window.scrollTo({ top: 0 })
              focusTitle()
            }}
          />
        </div>
      ) : (
        <RecipeView
          key={recipe.data.id}
          recipe={recipe.data}
          notice={notice?.id === id ? notice.text : null}
          onEdit={() => {
            setNotice(null)
            setEditing(id)
            window.scrollTo({ top: 0 })
            requestAnimationFrame(() => document.getElementById('editar-title')?.focus())
          }}
          onRestored={() => {
            setNotice({ id, text: 'Receita restaurada: voltou a ser a original do vídeo.' })
            window.scrollTo({ top: 0 })
            focusTitle()
          }}
        />
      )}
    </article>
  )
}

/** Esqueleto da página enquanto a receita carrega (mesma forma, sem pular o layout). */
function RecipeSkeleton() {
  const bar = 'animate-pulse rounded bg-paper-deep'
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:py-10" role="status">
      <span className="sr-only">Abrindo a receita…</span>
      <div className="mb-4 h-6 w-28" />
      <div className="page-sheet px-3 py-6 sm:px-8 sm:py-10 lg:px-12" aria-hidden="true">
        <div className={`h-4 w-40 ${bar}`} />
        <div className={`mt-4 h-10 w-3/4 ${bar}`} />
        <div className={`mt-4 h-5 w-2/3 ${bar}`} />
        <div className="mt-8 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-20">
          <div>
            <div className={`aspect-video w-full ${bar}`} />
            <div className={`mt-8 h-7 w-40 ${bar}`} />
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className={`mt-4 h-5 w-5/6 ${bar}`} />
            ))}
          </div>
          <div className="max-lg:mt-10">
            <div className={`h-7 w-48 ${bar}`} />
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className={`mt-6 h-14 w-full ${bar}`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
