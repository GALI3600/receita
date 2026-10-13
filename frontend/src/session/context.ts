import { createContext, useContext } from 'react'

import type { Me } from '../api/types'

export type SessionStatus = 'loading' | 'authenticated' | 'anonymous' | 'error'

export interface SessionValue {
  status: SessionStatus
  user: Me | null
  /** Anônimo porque a pessoa saiu da conta agora (e não porque a sessão expirou). */
  signedOut: boolean
  /** Saiu porque acabou de excluir a conta (a apresentação mostra o aviso). */
  accountDeleted: boolean
  /** Encerra a sessão; rejeita (e mantém a sessão) se o servidor não confirmar. */
  logout: () => Promise<void>
  /** Esquece a sessão só na interface, depois de o servidor já tê-la encerrado (conta excluída). */
  endAfterAccountDeleted: () => void
  isLoggingOut: boolean
  retry: () => void
}

export const SessionContext = createContext<SessionValue | null>(null)

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession precisa estar dentro de <SessionProvider>')
  return value
}

/** Usuário logado dentro de uma rota protegida (RequireAuth garante que existe). */
export function useCurrentUser(): Me {
  const { user } = useSession()
  if (!user) throw new Error('useCurrentUser fora de uma rota protegida')
  return user
}
