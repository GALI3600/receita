import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'

import { fieldId } from './formUtils'

interface ShellProps {
  fieldKey: string
  label: ReactNode
  error?: string
  hint?: ReactNode
  className?: string
  /** Rótulo menor, para os campos das linhas (ingredientes, passos). */
  compact?: boolean
  children: (props: {
    id: string
    'aria-invalid': true | undefined
    'aria-describedby': string | undefined
  }) => ReactNode
}

function FieldShell({
  fieldKey,
  label,
  error,
  hint,
  className = '',
  compact,
  children,
}: ShellProps) {
  const id = fieldId(fieldKey)
  const hintId = `${id}-dica`
  const errorId = `${id}-erro`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')
  return (
    <div className={className}>
      <label
        htmlFor={id}
        className={
          compact
            ? 'mb-0.5 block text-sm font-semibold text-ink-soft'
            : 'mb-1 block font-semibold text-ink'
        }
      >
        {label}
      </label>
      {children({
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': describedBy || undefined,
      })}
      {hint && (
        <p id={hintId} className="mt-1 text-sm text-ink-soft">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1 text-sm font-semibold text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

type CommonProps = Omit<ShellProps, 'children'>

export function TextInput({
  fieldKey,
  label,
  error,
  hint,
  className,
  compact,
  ...input
}: CommonProps & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <FieldShell {...{ fieldKey, label, error, hint, className, compact }}>
      {(aria) => <input type="text" className="field-input" {...aria} {...input} />}
    </FieldShell>
  )
}

export function TextArea({
  fieldKey,
  label,
  error,
  hint,
  className,
  compact,
  ...textarea
}: CommonProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <FieldShell {...{ fieldKey, label, error, hint, className, compact }}>
      {(aria) => <textarea className="field-input resize-y" rows={3} {...aria} {...textarea} />}
    </FieldShell>
  )
}

export function SelectField({
  fieldKey,
  label,
  error,
  hint,
  className,
  compact,
  children,
  ...select
}: CommonProps & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <FieldShell {...{ fieldKey, label, error, hint, className, compact }}>
      {(aria) => (
        <select className="field-input" {...aria} {...select}>
          {children}
        </select>
      )}
    </FieldShell>
  )
}

function ArrowIcon({ direction }: { direction: 'up' | 'down' }) {
  return (
    <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
      <path
        d={
          direction === 'up' ? 'M10 15V5m-4.5 4.5L10 5l4.5 4.5' : 'M10 5v10m-4.5-4.5L10 15l4.5-4.5'
        }
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
      <path
        d="M4 6h12M8 6V4.5h4V6m-6.5 0 .7 9.5a1 1 0 0 0 1 .9h5.6a1 1 0 0 0 1-.9L14.5 6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const ICON_BUTTON =
  'inline-flex size-11 items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-paper-deep hover:text-ink disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-transparent'

/** Botões de mover para cima/baixo e remover de uma linha do formulário. */
export function RowActions({
  idPrefix,
  itemLabel,
  index,
  count,
  onMove,
  onRemove,
}: {
  /** Prefixo dos ids dos botões (para devolver o foco depois de mover). */
  idPrefix: string
  /** "ingrediente 3", "passo 2"... */
  itemLabel: string
  index: number
  count: number
  onMove?: (delta: -1 | 1) => void
  onRemove: () => void
}) {
  return (
    <div className="flex shrink-0 items-center">
      {onMove && (
        <>
          <button
            id={`${idPrefix}-subir`}
            type="button"
            className={ICON_BUTTON}
            onClick={() => onMove(-1)}
            disabled={index === 0}
            aria-label={`Mover ${itemLabel} para cima`}
            title="Mover para cima"
          >
            <ArrowIcon direction="up" />
          </button>
          <button
            id={`${idPrefix}-descer`}
            type="button"
            className={ICON_BUTTON}
            onClick={() => onMove(1)}
            disabled={index === count - 1}
            aria-label={`Mover ${itemLabel} para baixo`}
            title="Mover para baixo"
          >
            <ArrowIcon direction="down" />
          </button>
        </>
      )}
      <button
        id={`${idPrefix}-remover`}
        type="button"
        className={`${ICON_BUTTON} hover:bg-danger-tint hover:text-danger`}
        onClick={onRemove}
        aria-label={`Remover ${itemLabel}`}
        title="Remover"
      >
        <TrashIcon />
      </button>
    </div>
  )
}
