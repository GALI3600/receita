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
    <article className="group relative flex h-full flex-col overflow-hidden rounded-r-md rounded-l-sm border border-line bg-card shadow-cover transition-shadow focus-within:shadow-page hover:shadow-page">
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
    <div className="overflow-hidden rounded-md border border-line bg-card" aria-hidden="true">
      <div className="aspect-video animate-pulse bg-paper-deep" />
      <div className="space-y-2 p-4">
        <div className="h-5 w-3/4 animate-pulse rounded bg-paper-deep" />
        <div className="h-4 w-1/3 animate-pulse rounded bg-paper-deep" />
      </div>
    </div>
  )
}
