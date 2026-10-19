import { Link } from 'react-router-dom'

import type { RecipeSummary } from '../../api/types'
import { youtubeThumbnail } from '../../lib/format'
import { HeartIcon, RecipeMeta } from './RecipeMeta'

interface RecipeCardProps {
  recipe: RecipeSummary
}

/** Card no estilo capa de livro: foto do vídeo, lombada terracota e título em serifa. */
export function RecipeCard({ recipe }: RecipeCardProps) {
  return (
    <article className="group relative flex h-full flex-col overflow-hidden rounded-r-md rounded-l-sm border border-line bg-card shadow-cover transition-[box-shadow,translate] duration-200 focus-within:shadow-page hover:-translate-y-0.5 hover:shadow-page motion-reduce:hover:translate-y-0">
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 z-10 w-2 bg-gradient-to-r from-terracotta-dark to-terracotta"
      />
      <div className="relative ml-2 aspect-video overflow-hidden bg-paper-deep">
        <img
          src={youtubeThumbnail(recipe.video.youtube_id)}
          alt=""
          loading="lazy"
          className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />
        {recipe.is_favorite && (
          <span className="absolute top-2 right-2 rounded-full bg-card/95 p-1.5 text-terracotta shadow">
            <HeartIcon filled className="size-4" />
            <span className="sr-only">Favorita</span>
          </span>
        )}
      </div>
      <div className="ml-2 flex flex-1 flex-col gap-2 px-4 pt-3 pb-4">
        <h2 className="text-xl leading-snug font-semibold">
          <Link
            to={`/receitas/${recipe.id}`}
            className="after:absolute after:inset-0 after:content-[''] focus:outline-none focus-visible:underline"
          >
            {recipe.title}
          </Link>
        </h2>
        <RecipeMeta recipe={recipe} />
      </div>
    </article>
  )
}

export function RecipeCardSkeleton() {
  return (
    <div
      className="relative overflow-hidden rounded-r-md rounded-l-sm border border-line bg-card shadow-cover"
      aria-hidden="true"
    >
      <span className="absolute inset-y-0 left-0 w-2 bg-line" />
      <div className="ml-2 aspect-video animate-pulse bg-paper-deep" />
      <div className="ml-2 space-y-3 px-4 pt-4 pb-5">
        <div className="h-5 w-3/4 animate-pulse rounded bg-paper-deep" />
        <div className="h-4 w-1/3 animate-pulse rounded bg-paper-deep" />
        <div className="flex gap-2 pt-2">
          <div className="h-7 w-16 animate-pulse rounded-full bg-paper-deep" />
          <div className="h-7 w-20 animate-pulse rounded-full bg-paper-deep" />
        </div>
      </div>
    </div>
  )
}
