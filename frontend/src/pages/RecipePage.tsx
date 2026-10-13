import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { isApiError } from '../api/client'
import { useDeleteRecipe, useRecipe, useUpdateRecipe } from '../api/queries'
import type { Recipe, Step } from '../api/types'
import { IngredientList } from '../components/recipe/IngredientList'
import { DifficultyBadge, HeartIcon } from '../components/recipe/RecipeMeta'
import { StepList } from '../components/recipe/StepList'
import { Alert, LoadingPage } from '../components/ui'
import { YouTubePlayer, type YouTubePlayerHandle } from '../components/youtube/YouTubePlayer'
import { isPlayerUnavailable, type PlayerStatus } from '../components/youtube/playerStatus'
import { describeError } from '../lib/errors'
import { formatMinutes, totalMinutes, youtubeWatchUrl } from '../lib/format'
import { useDocumentTitle } from '../lib/useDocumentTitle'

function TimeFacts({ recipe }: { recipe: Recipe }) {
  const total = totalMinutes(recipe)
  const facts = [
    recipe.servings ? { label: 'Rende', value: recipe.servings } : null,
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
    <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-line py-4 sm:flex sm:flex-wrap">
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

function DeleteRecipe({ recipe }: { recipe: Recipe }) {
  const navigate = useNavigate()
  const remove = useDeleteRecipe(recipe.id)
  const [confirming, setConfirming] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const deleteRef = useRef<HTMLButtonElement>(null)

  function cancel() {
    setConfirming(false)
    // O foco volta para "Excluir" (o botão "Cancelar" some da página).
    requestAnimationFrame(() => deleteRef.current?.focus())
  }

  if (!confirming) {
    return (
      <button
        ref={deleteRef}
        type="button"
        className="btn-ghost text-danger hover:text-danger"
        onClick={() => {
          setConfirming(true)
          // O foco vai para "Cancelar", a opção segura.
          requestAnimationFrame(() => cancelRef.current?.focus())
        }}
      >
        Excluir
      </button>
    )
  }
  return (
    <div
      role="alertdialog"
      aria-labelledby="confirmar-exclusao"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !remove.isPending) cancel()
      }}
      className="w-full rounded-lg border border-danger/40 bg-danger-tint p-4 sm:w-auto"
    >
      <p id="confirmar-exclusao" className="font-semibold">
        Excluir “{recipe.title}” do seu livro?
      </p>
      <p className="text-sm text-ink-soft">Suas anotações e o favorito somem junto.</p>
      {remove.isError && (
        <p className="mt-2 text-sm font-semibold text-danger">{describeError(remove.error)}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-danger"
          disabled={remove.isPending}
          onClick={() =>
            remove.mutate(undefined, {
              onSuccess: () =>
                navigate('/livro', { replace: true, state: { deleted: recipe.title } }),
            })
          }
        >
          {remove.isPending ? 'Excluindo…' : 'Sim, excluir'}
        </button>
        <button ref={cancelRef} type="button" className="btn-secondary" onClick={cancel}>
          Cancelar
        </button>
      </div>
    </div>
  )
}

function RecipeView({ recipe }: { recipe: Recipe }) {
  const location = useLocation()
  const playerRef = useRef<YouTubePlayerHandle>(null)
  const [activeStep, setActiveStep] = useState<number | null>(null)
  const [playerStatus, setPlayerStatus] = useState<PlayerStatus>('loading')
  const update = useUpdateRecipe(recipe.id)
  const justImported = (location.state as { imported?: boolean } | null)?.imported === true
  // Sem vídeo, os tempos dos passos viram texto e o player deixa de ficar fixo no celular.
  const videoUnavailable = isPlayerUnavailable(playerStatus)

  function seekToStep(step: Step) {
    if (step.video_timestamp_s === null) return
    setActiveStep(step.order)
    playerRef.current?.seekTo(step.video_timestamp_s)
  }

  return (
    <article className="mx-auto w-full max-w-6xl px-4 py-6 sm:py-10">
      <p className="mb-4 print:hidden">
        <Link to="/livro" className="link">
          ← Meu livro
        </Link>
      </p>
      {justImported && (
        <Alert tone="success" className="mb-4 print:hidden">
          Receita salva no seu livro.
        </Alert>
      )}

      <div className="page-sheet relative px-3 py-6 sm:px-8 sm:py-10 lg:px-12">
        <header className="max-w-3xl">
          {recipe.tags.length > 0 && (
            <p className="eyebrow">{recipe.tags.slice(0, 3).join(' · ')}</p>
          )}
          <h1 className="mt-2 text-3xl leading-tight font-semibold sm:text-5xl">{recipe.title}</h1>
          {recipe.summary && (
            <p className="mt-3 font-serif text-lg text-ink-soft italic sm:text-xl">
              {recipe.summary}
            </p>
          )}
          <p className="mt-3 text-sm text-ink-soft">
            Do vídeo{' '}
            <a
              className="link font-normal"
              href={youtubeWatchUrl(recipe.video.youtube_id)}
              target="_blank"
              rel="noreferrer"
            >
              {recipe.video.title}
            </a>
            {recipe.video.channel && <> · {recipe.video.channel}</>}
          </p>
          <TimeFacts recipe={recipe} />
          <div className="mt-4 flex flex-wrap items-center gap-2 print:hidden">
            <button
              type="button"
              className="btn-secondary"
              aria-pressed={recipe.is_favorite}
              onClick={() => update.mutate({ is_favorite: !recipe.is_favorite })}
            >
              <HeartIcon filled={recipe.is_favorite} className="size-5 text-terracotta" />
              {recipe.is_favorite ? 'Favorita' : 'Favoritar'}
            </button>
            <button type="button" className="btn-ghost" onClick={() => window.print()}>
              Imprimir
            </button>
            <DeleteRecipe recipe={recipe} />
          </div>
          {update.isError && (
            <Alert tone="error" className="mt-3">
              {describeError(update.error)}
            </Alert>
          )}
        </header>

        {/*
          Celular e tablet (uma coluna): o player fica fixo no topo enquanto se lê a receita; a
          coluna da esquerda vira `contents` para o player poder grudar ao longo da página toda.
          Desktop: player e ingredientes fixos à esquerda; se não couberem na altura da tela, só a
          lista de ingredientes rola, e o player continua à vista.
        */}
        <div className="mt-8 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-12">
          <div className="recipe-aside max-lg:contents lg:sticky lg:top-4 lg:flex lg:max-h-[calc(100dvh-2rem)] lg:flex-col lg:gap-8 lg:self-start">
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
              className="max-lg:mt-8 lg:flex lg:min-h-0 lg:flex-col print:mt-8"
            >
              <h2 id="ingredientes" className="mb-3 text-2xl font-semibold">
                Ingredientes
              </h2>
              <div className="recipe-ingredients lg:-mr-2 lg:min-h-0 lg:overflow-y-auto lg:pr-2">
                <IngredientList ingredients={recipe.ingredients} />
              </div>
            </section>
          </div>

          <div className="space-y-10 max-lg:mt-10 print:mt-10">
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
                className="rounded-lg border border-dashed border-terracotta/40 bg-terracotta-tint/50 px-5 py-4"
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

            {recipe.tags.length > 0 && (
              <section aria-labelledby="tags">
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
          </div>
        </div>
      </div>
    </article>
  )
}

export function RecipePage() {
  const { id = '' } = useParams()
  const recipe = useRecipe(id)
  useDocumentTitle(recipe.data?.title ?? 'Receita')

  if (recipe.isPending) return <LoadingPage label="Abrindo a receita…" />
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
  return <RecipeView recipe={recipe.data} />
}
