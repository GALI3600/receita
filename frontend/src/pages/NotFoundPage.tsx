import { Link } from 'react-router-dom'

import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useSession } from '../session/context'

export function NotFoundPage() {
  useDocumentTitle('Página não encontrada')
  const { status } = useSession()
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center">
      <p className="font-serif text-7xl font-semibold text-terracotta" aria-hidden="true">
        404
      </p>
      <h1 className="mt-4 text-3xl font-semibold">Esta página não está no livro</h1>
      <p className="mt-2 text-ink-soft">
        O endereço pode ter mudado ou estar com um erro de digitação.
      </p>
      <Link to={status === 'authenticated' ? '/livro' : '/'} className="btn-primary mt-8">
        {status === 'authenticated' ? 'Ir para o meu livro' : 'Ir para o início'}
      </Link>
    </div>
  )
}
