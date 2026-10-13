import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Lê o `?token=` da URL uma vez e o tira da barra de endereço (e do histórico) logo em seguida,
 * para o link de uso único não ficar exposto. A página continua usando o valor guardado.
 */
export function useTokenFromUrl(): string | null {
  const [params, setParams] = useSearchParams()
  const [token] = useState(() => params.get('token'))
  const inUrl = params.has('token')

  useEffect(() => {
    if (!inUrl) return
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('token')
        return next
      },
      { replace: true },
    )
  }, [inUrl, setParams])

  return token
}
