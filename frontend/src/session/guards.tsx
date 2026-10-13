import type { ReactNode } from 'react'
import { Navigate, useLocation, useSearchParams } from 'react-router-dom'

import { LoadingPage } from '../components/ui'
import { loginPath, safeNext } from '../lib/navigation'
import { useSession } from './context'

function SessionError() {
  const { retry } = useSession()
  return (
    <div className="mx-auto max-w-md px-4 py-16 text-center" role="alert">
      <h1 className="text-2xl">Não conseguimos carregar sua conta</h1>
      <p className="mt-2 text-ink-soft">O servidor não respondeu. Tente de novo em instantes.</p>
      <button type="button" className="btn-primary mt-6" onClick={retry}>
        Tentar de novo
      </button>
    </div>
  )
}

/**
 * Rota que exige login: sem sessão, vai para /entrar?next=<caminho atual> (ou para a
 * apresentação, logo depois de a pessoa sair da conta).
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, signedOut, accountDeleted } = useSession()
  const location = useLocation()
  if (status === 'loading') return <LoadingPage />
  if (status === 'error') return <SessionError />
  if (status === 'anonymous') {
    // Quem acabou de sair vai para a apresentação; sessão expirada, para o login (com volta).
    const target = signedOut ? '/' : loginPath(location.pathname + location.search)
    return (
      <Navigate to={target} replace state={accountDeleted ? { accountDeleted: true } : undefined} />
    )
  }
  return children
}

/** Telas de quem não está logado (entrar, cadastro): logado, segue para o `next` ou o livro. */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useSession()
  const [params] = useSearchParams()
  if (status === 'loading') return <LoadingPage />
  if (status === 'authenticated') return <Navigate to={safeNext(params.get('next'))} replace />
  return children
}
