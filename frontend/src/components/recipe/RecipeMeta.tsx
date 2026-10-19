import { formatMinutes, totalMinutes } from '../../lib/format'

function ClockIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.5V8l2.5 1.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

/** Tempo total (cards e cabeçalho da receita). */
export function RecipeMeta({
  recipe,
  className = '',
}: {
  recipe: {
    prep_time_min: number | null
    cook_time_min: number | null
  }
  className?: string
}) {
  const total = totalMinutes(recipe)
  if (total === null) return null
  return (
    <p className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-soft ${className}`}>
      <span className="inline-flex items-center gap-1.5">
        <ClockIcon />
        <span>
          <span className="sr-only">Tempo total: </span>
          {formatMinutes(total)}
        </span>
      </span>
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
