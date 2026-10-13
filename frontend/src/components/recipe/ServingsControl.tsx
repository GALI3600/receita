import { useId } from 'react'

import { scaleServings } from '../../lib/quantity'

const MAX_FACTOR = 10

/** Porções com − e +: as quantidades dos ingredientes acompanham. */
export function ServingsControl({
  servings,
  base,
  count,
  onChange,
}: {
  /** Rendimento original ("6 unidades"). */
  servings: string
  /** Número de porções do original (6). */
  base: number
  count: number
  onChange: (count: number) => void
}) {
  const labelId = useId()
  const step = base >= 1 ? 1 : base
  const min = Math.min(base, 1)
  const max = Math.max(base * MAX_FACTOR, base + step)
  const text = scaleServings(servings, count)
  const changed = count !== base
  const button =
    'inline-flex size-11 items-center justify-center rounded-full border border-ink/25 bg-card text-xl leading-none font-semibold text-ink transition-colors hover:border-terracotta hover:text-terracotta disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-ink/25 disabled:hover:text-ink'

  return (
    <div
      role="group"
      aria-labelledby={labelId}
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-line bg-paper/70 px-3 py-2 print:border-0 print:bg-transparent print:p-0"
    >
      <span id={labelId} className="text-sm font-semibold tracking-wider text-ink-soft uppercase">
        Rende
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={`${button} print:hidden`}
          onClick={() => onChange(Math.max(min, count - step))}
          disabled={count - step < min - 1e-9}
          aria-label="Menos porções"
        >
          <span aria-hidden="true">−</span>
        </button>
        <output
          aria-live="polite"
          className="min-w-24 text-center font-serif text-lg font-semibold"
        >
          {text}
        </output>
        <button
          type="button"
          className={`${button} print:hidden`}
          onClick={() => onChange(Math.min(max, count + step))}
          disabled={count + step > max + 1e-9}
          aria-label="Mais porções"
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>
      {changed && (
        <button
          type="button"
          className="link inline-flex min-h-11 items-center text-sm print:hidden"
          onClick={() => onChange(base)}
        >
          Voltar para {servings}
        </button>
      )}
      {changed && (
        <p className="w-full text-sm text-ink-soft">
          Quantidades ajustadas de {servings} para {text}; confira as que não têm número.
        </p>
      )}
    </div>
  )
}
