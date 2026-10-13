import type { Difficulty } from '../../api/types'
import { formatMinutes, totalMinutes } from '../../lib/format'

function ClockIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.5V8l2.5 1.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

const DIFFICULTY_DOTS: Record<Difficulty, number> = { fácil: 1, média: 2, difícil: 3 }

/** `srLabel={false}` quando um rótulo visível já diz "Dificuldade" (ex.: o <dt> da receita). */
export function DifficultyBadge({
  difficulty,
  srLabel = true,
}: {
  difficulty: Difficulty
  srLabel?: boolean
}) {
  const dots = DIFFICULTY_DOTS[difficulty]
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="flex gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={`size-1.5 rounded-full ${n <= dots ? 'bg-terracotta' : 'bg-line'}`}
          />
        ))}
      </span>
      <span>
        {srLabel && <span className="sr-only">Dificuldade: </span>}
        <span className="first-letter:uppercase">{difficulty}</span>
      </span>
    </span>
  )
}

/** Tempo total e dificuldade numa linha (cards e cabeçalho da receita). */
export function RecipeMeta({
  recipe,
  className = '',
}: {
  recipe: {
    prep_time_min: number | null
    cook_time_min: number | null
    difficulty: Difficulty | null
  }
  className?: string
}) {
  const total = totalMinutes(recipe)
  if (total === null && !recipe.difficulty) return null
  return (
    <p className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-soft ${className}`}>
      {total !== null && (
        <span className="inline-flex items-center gap-1.5">
          <ClockIcon />
          <span>
            <span className="sr-only">Tempo total: </span>
            {formatMinutes(total)}
          </span>
        </span>
      )}
      {recipe.difficulty && <DifficultyBadge difficulty={recipe.difficulty} />}
    </p>
  )
}

export function HeartIcon({
  filled,
  className = 'size-5',
}: {
  filled: boolean
  className?: string
}) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path
        d="M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}
