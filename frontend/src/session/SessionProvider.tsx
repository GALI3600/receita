import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import { useLocation } from 'react-router-dom'

import { clearSession, useLogout, useMe } from '../api/queries'
import { SessionContext, type SessionStatus, type SessionValue } from './context'

/** Sessão a partir de GET /auth/me (cookie httpOnly): quem está logado e a cota do dia. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const me = useMe()
  const logoutMutation = useLogout()
  const { data, isError, refetch } = me
  const { mutateAsync, isPending } = logoutMutation
  // A pessoa clicou em "Sair": as rotas protegidas mandam para a apresentação, não para o login.
  // Vale só até chegar lá: depois, abrir uma rota protegida volta a levar ao login.
  const [signedOut, setSignedOut] = useState(false)
  const [previousData, setPreviousData] = useState(data)
  const { pathname } = useLocation()
  if (data !== previousData) {
    setPreviousData(data)
    if (data) setSignedOut(false)
  }
  if (signedOut && data === null && pathname === '/') setSignedOut(false)

  const value = useMemo<SessionValue>(() => {
    let status: SessionStatus
    if (data) status = 'authenticated'
    else if (data === null) status = 'anonymous'
    else if (isError) status = 'error'
    else status = 'loading'
    return {
      status,
      user: data ?? null,
      signedOut: status === 'anonymous' && signedOut,
      logout: async () => {
        // Falhou (rede, 5xx): o erro sobe para a tela e a sessão continua como está.
        await mutateAsync()
        // Primeiro marca a saída, depois limpa a sessão: quando as rotas virem o usuário
        // anônimo, já sabem que foi um logout.
        flushSync(() => setSignedOut(true))
        clearSession(client)
      },
      isLoggingOut: isPending,
      retry: () => void refetch(),
    }
  }, [data, isError, refetch, mutateAsync, isPending, signedOut, client])

  return <SessionContext value={value}>{children}</SessionContext>
}
