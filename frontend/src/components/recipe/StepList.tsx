import type { Step } from '../../api/types'
import { formatTimestamp } from '../../lib/format'

interface StepListProps {
  steps: Step[]
  activeOrder: number | null
  /** Chamado ao clicar no tempo de um passo; sem isso (vídeo indisponível) o tempo é só texto. */
  onSeek?: (step: Step) => void
}

/** Modo de preparo numerado; o tempo de cada passo leva o vídeo àquele momento. */
export function StepList({ steps, activeOrder, onSeek }: StepListProps) {
  if (steps.length === 0) {
    return <p className="text-ink-soft">O vídeo não traz o passo a passo.</p>
  }
  return (
    <ol className="space-y-4">
      {steps.map((step) => {
        const active = step.order === activeOrder
        const time = step.video_timestamp_s
        return (
          <li
            key={step.order}
            aria-current={active ? 'step' : undefined}
            className={`flex gap-4 rounded-lg border px-3 py-3 transition-colors sm:px-4 ${
              active ? 'border-terracotta/50 bg-terracotta-tint' : 'border-transparent'
            }`}
          >
            <span
              aria-hidden="true"
              className="w-8 shrink-0 text-right font-serif text-3xl leading-none font-semibold text-terracotta"
            >
              {step.order}
            </span>
            <div className="min-w-0 flex-1">
              <p className="sr-only">Passo {step.order}.</p>
              <p>{step.text}</p>
              {time !== null &&
                (onSeek ? (
                  <button
                    type="button"
                    onClick={() => onSeek(step)}
                    className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-full border border-terracotta/40 bg-card px-3 text-sm font-semibold text-terracotta hover:bg-terracotta-tint print:hidden"
                    aria-label={`Ver o passo ${step.order} no vídeo, em ${formatTimestamp(time)}`}
                  >
                    <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden="true">
                      <path d="M4 2.5v11l9-5.5z" fill="currentColor" />
                    </svg>
                    {formatTimestamp(time)}
                  </button>
                ) : (
                  <p className="mt-1 text-sm text-ink-soft">No vídeo em {formatTimestamp(time)}</p>
                ))}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
