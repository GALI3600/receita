import { useEffect } from 'react'

const APP_NAME = 'Receita'

/** Atualiza o título da aba (útil também para leitores de tela ao trocar de página). */
export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME
  }, [title])
}
