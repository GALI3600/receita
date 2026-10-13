import { useMemo, type ReactNode } from 'react'

import { useLogout, useMe } from '../api/queries'
import { SessionContext, type SessionStatus, type SessionValue } from './context'

/** Sessão a partir de GET /auth/me (cookie httpOnly): quem está logado e a cota do dia. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const me = useMe()
  const logoutMutation = useLogout()
  const { data, isError, refetch } = me
  const { mutateAsync, isPending } = logoutMutation

  const value = useMemo<SessionValue>(() => {
    let status: SessionStatus
    if (data) status = 'authenticated'
    else if (data === null) status = 'anonymous'
    else if (isError) status = 'error'
    else status = 'loading'
    return {
      status,
      user: data ?? null,
      logout: async () => {
        await mutateAsync().catch(() => undefined)
      },
      isLoggingOut: isPending,
      retry: () => void refetch(),
    }
  }, [data, isError, refetch, mutateAsync, isPending])

  return <SessionContext value={value}>{children}</SessionContext>
}
