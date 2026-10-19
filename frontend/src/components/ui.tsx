import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react'

export function Spinner({ className = 'size-5' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin text-terracotta ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export function LoadingPage({ label = 'Carregando…' }: { label?: string }) {
  return (
    <div
      className="flex min-h-[50vh] items-center justify-center gap-3 text-ink-soft"
      role="status"
    >
      <Spinner />
      <span>{label}</span>
    </div>
  )
}

type AlertTone = 'info' | 'success' | 'warning' | 'error'

const ALERT_STYLES: Record<AlertTone, string> = {
  info: 'border-line bg-paper-deep',
  success: 'border-sage/40 bg-sage-tint',
  warning: 'border-mustard-line/60 bg-mustard-tint',
  error: 'border-danger/40 bg-danger-tint',
}

export function Alert({
  tone = 'info',
  title,
  children,
  live = tone === 'error' ? 'assertive' : 'polite',
  className = '',
}: {
  tone?: AlertTone
  title?: ReactNode
  children?: ReactNode
  live?: 'polite' | 'assertive' | 'off'
  className?: string
}) {
  const role = live === 'assertive' ? 'alert' : live === 'polite' ? 'status' : undefined
  return (
    <div
      role={role}
      className={`rounded-lg border px-4 py-3 text-ink ${ALERT_STYLES[tone]} ${className}`}
    >
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={title ? 'mt-1 text-ink' : 'text-ink'}>{children}</div>}
    </div>
  )
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string | null
  hint?: ReactNode
}

function EyeIcon({ className = 'size-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" aria-hidden="true">
      <path
        d="M1.5 10S4.5 4 10 4s8.5 6 8.5 6-3 6-8.5 6-8.5-6-8.5-6Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function EyeOffIcon({ className = 'size-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" aria-hidden="true">
      <path
        d="M1.5 10S4.5 4 10 4s8.5 6 8.5 6-3 6-8.5 6-8.5-6-8.5-6Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M3 3l14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

/** Campo com rótulo, dica e erro ligados por aria-describedby.
 *  Para `type="password"`, mostra um botão de olho para alternar a visibilidade. */
export function Field({ label, error, hint, id, className = '', type, ...input }: FieldProps) {
  const generated = useId()
  const inputId = id ?? generated
  const hintId = `${inputId}-hint`
  const errorId = `${inputId}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')
  const isPassword = type === 'password'
  const [visible, setVisible] = useState(false)
  return (
    <div className={className}>
      <label htmlFor={inputId} className="mb-1 block font-semibold text-ink">
        {label}
      </label>
      <div className={isPassword ? 'relative' : undefined}>
        <input
          id={inputId}
          type={isPassword ? (visible ? 'text' : 'password') : type}
          className={isPassword ? 'field-input pr-10' : 'field-input'}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          {...input}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setVisible((value) => !value)}
            className="absolute inset-y-0 right-2 flex items-center text-ink-soft hover:text-ink"
            aria-label={visible ? 'Ocultar senha' : 'Mostrar senha'}
          >
            {visible ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        )}
      </div>
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

/** Moldura das telas de conta (entrar, cadastro, senha): uma folha centralizada. */
export function AuthCard({
  title,
  intro,
  children,
}: {
  title: string
  intro?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="mx-auto w-full max-w-md px-4 py-10 sm:py-16">
      <div className="page-sheet px-5 py-8 sm:px-8">
        <p className="ornament mb-4 font-serif text-lg" aria-hidden="true">
          ❦
        </p>
        <h1 className="text-center text-3xl font-semibold">{title}</h1>
        {intro && <div className="mt-2 text-center text-ink-soft">{intro}</div>}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  )
}
