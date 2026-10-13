import { useEffect } from 'react'
import { useBlocker } from 'react-router-dom'

import { ConfirmDialog } from './ConfirmDialog'

/**
 * Avisa antes de perder alterações não salvas: navegação dentro do site (links, voltar) abre uma
 * confirmação; fechar ou recarregar a aba cai no aviso do próprio navegador.
 */
export function UnsavedChangesGuard({
  when,
  message = 'As alterações que você fez ainda não foram salvas.',
  onLeave,
}: {
  when: boolean
  message?: string
  /** A pessoa confirmou que quer sair sem salvar. */
  onLeave?: () => void
}) {
  // Só bloqueia quando o caminho muda (trocar a query string da mesma página não perde nada).
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      when && currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (!when) return
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault()
      // Navegadores antigos só mostram o aviso com returnValue preenchido.
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [when])

  return (
    <ConfirmDialog
      open={blocker.state === 'blocked'}
      title="Sair sem salvar?"
      confirmLabel="Sair sem salvar"
      cancelLabel="Continuar editando"
      tone="danger"
      onConfirm={() => {
        onLeave?.()
        blocker.proceed?.()
      }}
      onCancel={() => blocker.reset?.()}
    >
      {message}
    </ConfirmDialog>
  )
}
