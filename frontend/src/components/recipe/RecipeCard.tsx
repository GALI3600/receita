import { Link } from 'react-router-dom'

import type { RecipeSummary } from '../../api/types'
import { youtubeThumbnail } from '../../lib/format'
import { HeartIcon, RecipeMeta } from './RecipeMeta'

interface RecipeCardProps {
  recipe: RecipeSummary
  onTagClick?: (tag: string) => void
}

/** Card no estilo capa de livro: foto do vídeo, lombada terracota e título em serifa. */
export function RecipeCard({ recipe, onTagClick }: RecipeCardProps) {
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
          {/* O link cobre o card inteiro (pseudo-elemento), mas as tags continuam clicáveis. */}
          <Link
            to={`/receitas/${recipe.id}`}
            className="after:absolute after:inset-0 after:content-[''] focus:outline-none focus-visible:underline"
          >
            {recipe.title}
          </Link>
        </h2>
        <RecipeMeta recipe={recipe} />
        {recipe.rating !== null && (
          <p className="flex items-center gap-0.5 text-terracotta">
            {[1, 2, 3, 4, 5].map((n) => (
              <svg key={n} viewBox="0 0 24 24" className="size-4" aria-hidden="true">
                <path
                  d="m12 3.6 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"
                  fill={n <= (recipe.rating ?? 0) ? 'currentColor' : 'none'}
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
            ))}
            <span className="sr-only">Avaliação: {recipe.rating} de 5</span>
          </p>
        )}
        {recipe.tags.length > 0 && (
          <ul className="relative z-10 mt-auto flex flex-wrap gap-2 pt-1" aria-label="Tags">
            {recipe.tags.slice(0, 4).map((tag) => (
              <li key={tag}>
                {onTagClick ? (
                  <button
                    type="button"
                    className="tag-chip tag-chip-action hover:border-terracotta/50 hover:text-terracotta"
                    onClick={() => onTagClick(tag)}
                    aria-label={`Filtrar pela tag ${tag}`}
                  >
                    #{tag}
                  </button>
                ) : (
                  <span className="tag-chip">#{tag}</span>
                )}
              </li>
            ))}
          </ul>
        )}
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
