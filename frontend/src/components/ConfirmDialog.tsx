import { useEffect, useId, useRef, type ReactNode } from 'react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel: string
  cancelLabel?: string
  tone?: 'danger' | 'primary'
  busy?: boolean
  /** Erro da ação, mostrado dentro do diálogo. */
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
}

/**
 * Confirmação modal com <dialog>: o navegador prende o foco dentro dele e deixa o resto da página
 * inerte. O foco começa em "Cancelar", a opção segura, e volta para quem abriu ao fechar.
 */
export function ConfirmDialog(props: ConfirmDialogProps) {
  return props.open ? <OpenDialog {...props} /> : null
}

function OpenDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = 'Cancelar',
  tone = 'primary',
  busy = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  // Esc dispara keydown e, em alguns navegadores, também o evento cancel: cancela uma vez só.
  const cancelledRef = useRef(false)
  const titleId = useId()
  const bodyId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    // jsdom (testes) não tem showModal: aí o diálogo só fica aberto, sem ser modal.
    if (typeof dialog.showModal === 'function') {
      if (!dialog.open) dialog.showModal()
    } else dialog.setAttribute('open', '')
    cancelRef.current?.focus()
    return () => {
      if (dialog.open && typeof dialog.close === 'function') dialog.close()
      // O foco volta para quem abriu (se ainda estiver na página).
      requestAnimationFrame(() => {
        if (opener?.isConnected && !document.querySelector('dialog[open]')) opener.focus()
      })
    }
  }, [])

  function cancelOnce() {
    if (busy || cancelledRef.current) return
    cancelledRef.current = true
    onCancel()
  }

  return (
    <dialog
      ref={ref}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={children ? bodyId : undefined}
      onCancel={(event) => {
        // Esc (ou o "voltar" do celular): quem fecha é o React; não fecha no meio da ação.
        event.preventDefault()
        cancelOnce()
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault()
          cancelOnce()
        }
      }}
      className="dialog-sheet"
    >
      <h2 id={titleId} className="text-2xl font-semibold">
        {title}
      </h2>
      {children && (
        <div id={bodyId} className="mt-2 text-ink-soft">
          {children}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm font-semibold text-danger">
          {error}
        </p>
      )}
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <button
          ref={cancelRef}
          type="button"
          className="btn-secondary"
          onClick={cancelOnce}
          disabled={busy}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          className={tone === 'danger' ? 'btn-danger' : 'btn-primary'}
          onClick={onConfirm}
          disabled={busy}
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
