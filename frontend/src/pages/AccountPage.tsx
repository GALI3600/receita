import { useNavigate } from 'react-router-dom'

import { ACCOUNT_EXPORT_URL } from '../api/endpoints'
import { ResendVerification } from '../components/ResendVerification'
import { formatDate, formatDateTime } from '../lib/format'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useCurrentUser, useSession } from '../session/context'

export function AccountPage() {
  useDocumentTitle('Minha conta')
  const user = useCurrentUser()
  const { logout, isLoggingOut } = useSession()
  const navigate = useNavigate()
  const { quota } = user
  const usedPercent = quota.limit > 0 ? Math.min(100, (quota.used / quota.limit) * 100) : 100

  async function onLogout() {
    await logout()
    navigate('/', { replace: true })
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8 sm:py-12">
      <p className="eyebrow">Conta</p>
      <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">Olá, {user.name}</h1>

      <section aria-labelledby="dados" className="page-sheet mt-6 px-5 py-6 sm:px-8">
        <h2 id="dados" className="text-xl font-semibold">
          Seus dados
        </h2>
        <dl className="mt-3 grid gap-3 sm:grid-cols-[10rem_1fr]">
          <dt className="font-semibold text-ink-soft">Nome</dt>
          <dd>{user.name}</dd>
          <dt className="font-semibold text-ink-soft">E-mail</dt>
          <dd className="break-all">
            {user.email}{' '}
            {user.email_verified ? (
              <span className="ml-1 rounded-full bg-sage-tint px-2 py-0.5 text-sm text-sage">
                confirmado
              </span>
            ) : (
              <span className="ml-1 rounded-full bg-mustard-tint px-2 py-0.5 text-sm">
                não confirmado
              </span>
            )}
          </dd>
          <dt className="font-semibold text-ink-soft">Conta criada em</dt>
          <dd>{formatDate(user.created_at)}</dd>
        </dl>
        {!user.email_verified && (
          <div className="mt-4 rounded-lg bg-mustard-tint px-4 py-3">
            <p>Confirme seu e-mail para importar receitas.</p>
            <ResendVerification className="mt-2" />
          </div>
        )}
      </section>

      <section aria-labelledby="cota" className="page-sheet mt-6 px-5 py-6 sm:px-8">
        <h2 id="cota" className="text-xl font-semibold">
          Receitas novas de hoje
        </h2>
        <p className="mt-2">
          Você usou <strong>{quota.used}</strong> de <strong>{quota.limit}</strong>; restam{' '}
          <strong>{quota.remaining}</strong>.
        </p>
        <div
          className="mt-3 h-3 overflow-hidden rounded-full bg-paper-deep"
          role="progressbar"
          aria-label="Cota de receitas novas usada hoje"
          aria-valuemin={0}
          aria-valuemax={quota.limit}
          aria-valuenow={quota.used}
        >
          <div className="h-full rounded-full bg-terracotta" style={{ width: `${usedPercent}%` }} />
        </div>
        <p className="mt-3 text-sm text-ink-soft">
          A cota volta em {formatDateTime(quota.resets_at)}. Vídeos que já estão no Receita e
          importações que falham não contam.
        </p>
      </section>

      <section aria-labelledby="privacidade" className="page-sheet mt-6 px-5 py-6 sm:px-8">
        <h2 id="privacidade" className="text-xl font-semibold">
          Privacidade
        </h2>
        <p className="mt-2 text-ink-soft">
          Baixe uma cópia de tudo o que guardamos sobre você: perfil, receitas e importações.
        </p>
        <a href={ACCOUNT_EXPORT_URL} className="btn-secondary mt-3" download>
          Exportar meus dados
        </a>
      </section>

      <div className="mt-8 text-center">
        <button type="button" className="btn-secondary" onClick={onLogout} disabled={isLoggingOut}>
          {isLoggingOut ? 'Saindo…' : 'Sair da conta'}
        </button>
      </div>
    </div>
  )
}
