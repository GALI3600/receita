import type { ImportOut, ImportStatus } from '../api/types'

export const TERMINAL_STATUSES: ReadonlySet<ImportStatus> = new Set(['done', 'failed'])

export function isTerminal(status: ImportStatus): boolean {
  return TERMINAL_STATUSES.has(status)
}

/** Etapas mostradas no progresso, na ordem em que o worker passa por elas. */
export const IMPORT_STAGES = [
  { status: 'fetching', label: 'Buscando vídeo' },
  { status: 'transcribing', label: 'Transcrevendo' },
  { status: 'generating', label: 'Escrevendo a receita' },
] as const satisfies ReadonlyArray<{ status: ImportStatus; label: string }>

export type StageState = 'done' | 'current' | 'upcoming'

/** Estado de cada etapa para o status atual (pending: nenhuma começou; done: todas feitas). */
export function stageStates(status: ImportStatus): StageState[] {
  if (status === 'done') return IMPORT_STAGES.map(() => 'done')
  const current = IMPORT_STAGES.findIndex((stage) => stage.status === status)
  if (current === -1) return IMPORT_STAGES.map(() => 'upcoming')
  return IMPORT_STAGES.map((_, index) =>
    index < current ? 'done' : index === current ? 'current' : 'upcoming',
  )
}

/** Frase curta do momento atual, para o leitor de tela (aria-live) e o título da página. */
export function statusAnnouncement(imp: ImportOut): string {
  switch (imp.status) {
    case 'pending':
      return imp.queue_position
        ? `Na fila: ${imp.queue_position}º lugar.`
        : 'Na fila, começando em instantes.'
    case 'fetching':
      return 'Buscando o vídeo no YouTube.'
    case 'transcribing':
      return imp.queue_position
        ? `Aguardando a transcrição: ${imp.queue_position}º na fila.`
        : 'Transcrevendo o vídeo.'
    case 'generating':
      return 'Escrevendo a receita.'
    case 'deferred':
      return 'Importação adiada.'
    case 'done':
      return 'Receita pronta!'
    case 'failed':
      return 'Não foi possível importar esse vídeo.'
  }
}

/**
 * Intervalo do polling de GET /imports/{id}, em ms, ou false para parar.
 *
 * Rápido no começo (muitos vídeos com legenda ficam prontos em segundos), mais espaçado com o
 * tempo e quando o import está longe na fila; adiado só volta a andar no dia seguinte.
 */
export function pollInterval(imp: ImportOut | undefined, elapsedMs: number): number | false {
  if (!imp) return 1000
  if (isTerminal(imp.status)) return false
  if (imp.status === 'deferred') return 60_000
  if (imp.queue_position !== null && imp.queue_position > 5) return 10_000
  if (elapsedMs < 15_000) return 1000
  if (elapsedMs < 60_000) return 2000
  if (elapsedMs < 5 * 60_000) return 5000
  return 10_000
}
