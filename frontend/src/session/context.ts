import { createContext, useContext } from 'react'

import type { Me } from '../api/types'

export type SessionStatus = 'loading' | 'authenticated' | 'anonymous' | 'error'

export interface SessionValue {
  status: SessionStatus
  user: Me | null
  logout: () => Promise<void>
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
