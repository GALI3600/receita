import type { ImportOut } from '../api/types'
import {
  IMPORT_STAGES,
  stageStates,
  statusAnnouncement,
  type StageState,
} from '../lib/importStatus'
import { Spinner } from './ui'

const STATE_LABEL: Record<StageState, string> = {
  done: 'concluído',
  current: 'em andamento',
  upcoming: 'a fazer',
}

function StageIcon({ state }: { state: StageState }) {
  if (state === 'current') return <Spinner className="size-6" />
  if (state === 'done') {
    return (
      <svg viewBox="0 0 24 24" className="size-6 text-sage" aria-hidden="true">
        <circle cx="12" cy="12" r="10" fill="currentColor" />
        <path d="m7.5 12.5 3 3 6-6.5" fill="none" stroke="white" strokeWidth="2.2" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" className="size-6 text-line" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

/** Progresso do import por etapas, com a posição na fila e um aviso para leitores de tela. */
export function ImportProgress({ imp }: { imp: ImportOut }) {
  const states = stageStates(imp.status)
  const queueNote =
    imp.status === 'pending'
      ? imp.queue_position
        ? `Seu vídeo está na fila: ${imp.queue_position}º lugar.`
        : 'Seu vídeo está na fila e começa em instantes.'
      : imp.status === 'transcribing' && imp.queue_position
        ? `Aguardando a vez na transcrição: ${imp.queue_position}º na fila.`
        : null

  return (
    <div>
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {statusAnnouncement(imp)}
      </p>
      {queueNote && (
        <p className="mb-4 rounded-md bg-paper-deep px-3 py-2 text-ink" data-testid="queue-note">
          {queueNote}
        </p>
      )}
      <ol className="space-y-3" aria-label="Etapas da importação">
        {IMPORT_STAGES.map((stage, index) => {
          const state = states[index]
          return (
            <li
              key={stage.status}
              aria-current={state === 'current' ? 'step' : undefined}
              className={`flex items-center gap-3 text-lg ${
                state === 'upcoming' ? 'text-ink-soft' : 'text-ink'
              } ${state === 'current' ? 'font-semibold' : ''}`}
            >
              <StageIcon state={state} />
              <span>
                {stage.label}
                {state === 'current' && '…'}
                <span className="sr-only"> ({STATE_LABEL[state]})</span>
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
