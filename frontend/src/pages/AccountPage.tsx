import { useId, useState, type FormEvent } from 'react'

import { isApiError } from '../api/client'
import { ACCOUNT_EXPORT_FILENAME } from '../api/endpoints'
import { useDeleteAccount, useExportAccount } from '../api/queries'
import { ResendVerification } from '../components/ResendVerification'
import { Alert, Field, Spinner } from '../components/ui'
import { describeError } from '../lib/errors'
import { formatDate, formatDateTime } from '../lib/format'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useCurrentUser, useSession } from '../session/context'

/** Oferece `data` para baixar como arquivo JSON. */
function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Dá tempo de o navegador começar o download antes de liberar o arquivo.
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

function ExportData() {
  const exportAccount = useExportAccount()
  const [done, setDone] = useState(false)

  return (
    <section aria-labelledby="privacidade" className="page-sheet px-5 py-6 sm:px-8">
      <h2 id="privacidade" className="text-xl font-semibold">
        Seus dados
      </h2>
      <p className="mt-2 text-ink-soft">
        Baixe uma cópia de tudo o que guardamos sobre você: perfil, receitas (com as suas edições e
        notas) e o histórico de importações, num arquivo JSON.
      </p>
      <button
        type="button"
        className="btn-secondary mt-4"
        disabled={exportAccount.isPending}
        onClick={() => {
          setDone(false)
          exportAccount.mutate(undefined, {
            onSuccess: (data) => {
              downloadJson(data, ACCOUNT_EXPORT_FILENAME)
              setDone(true)
            },
          })
        }}
      >
        {exportAccount.isPending ? (
          <>
            <Spinner /> Preparando o arquivo…
          </>
        ) : (
          'Exportar meus dados'
        )}
      </button>
      <div aria-live="polite">
        {done && !exportAccount.isPending && (
          <p className="mt-3 text-sm text-sage">
            Pronto: o arquivo {ACCOUNT_EXPORT_FILENAME} foi baixado.
          </p>
        )}
      </div>
      {exportAccount.isError && (
        <Alert tone="error" className="mt-3">
          {describeError(exportAccount.error)}
        </Alert>
      )}
    </section>
  )
}

function DeleteAccount() {
  const { endAfterAccountDeleted } = useSession()
  const remove = useDeleteAccount()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const confirmId = useId()

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const missingPassword = password ? null : 'Digite sua senha para confirmar.'
    const missingConfirm = confirmed ? null : 'Marque a caixa para confirmar.'
    setPasswordError(missingPassword)
    setConfirmError(missingConfirm)
    if (missingPassword) {
      document.getElementById('excluir-senha')?.focus()
      return
    }
    if (missingConfirm) {
      document.getElementById(confirmId)?.focus()
      return
    }
    remove.mutate(password, {
      onSuccess: () => endAfterAccountDeleted(),
      onError: (error) => {
        if (isApiError(error, 'invalid_password')) {
          setPasswordError(error.message)
          document.getElementById('excluir-senha')?.focus()
        }
      },
    })
  }

  const generalError =
    remove.isError && !isApiError(remove.error, 'invalid_password')
      ? describeError(remove.error)
      : null

  return (
    <section
      aria-labelledby="excluir-conta"
      className="page-sheet border-danger/30 px-5 py-6 sm:px-8"
    >
      <h2 id="excluir-conta" className="text-xl font-semibold">
        Excluir conta
      </h2>
      <p className="mt-2 text-ink-soft">
        Apaga sua conta, todas as receitas do seu livro, as notas e o histórico de importações. Não
        dá para desfazer; se quiser guardar alguma coisa, exporte seus dados antes.
      </p>
      {!open ? (
        <button
          type="button"
          className="btn-secondary mt-4 border-danger/50 text-danger hover:border-danger hover:bg-danger-tint"
          onClick={() => {
            setOpen(true)
            requestAnimationFrame(() => document.getElementById('excluir-senha')?.focus())
          }}
        >
          Quero excluir minha conta
        </button>
      ) : (
        <form
          onSubmit={onSubmit}
          noValidate
          className="mt-4 space-y-4 rounded-lg border border-danger/40 bg-danger-tint/60 p-4"
        >
          <Field
            id="excluir-senha"
            label="Sua senha"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={passwordError}
          />
          <div>
            <label htmlFor={confirmId} className="flex cursor-pointer items-start gap-3">
              <input
                id={confirmId}
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                className="mt-1 size-5 shrink-0 accent-danger"
                aria-invalid={confirmError ? true : undefined}
                aria-describedby={confirmError ? `${confirmId}-erro` : undefined}
              />
              <span>
                Entendo que minha conta e todas as minhas receitas serão apagadas para sempre.
              </span>
            </label>
            {confirmError && (
              <p id={`${confirmId}-erro`} className="mt-1 text-sm font-semibold text-danger">
                {confirmError}
              </p>
            )}
          </div>
          {generalError && <Alert tone="error">{generalError}</Alert>}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn-danger" disabled={remove.isPending}>
              {remove.isPending ? 'Excluindo…' : 'Excluir minha conta para sempre'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={remove.isPending}
              onClick={() => {
                setOpen(false)
                setPassword('')
                setConfirmed(false)
                setPasswordError(null)
                setConfirmError(null)
                remove.reset()
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

export function AccountPage() {
  useDocumentTitle('Minha conta')
  const user = useCurrentUser()
  const { logout, isLoggingOut } = useSession()
  const [logoutError, setLogoutError] = useState<unknown>(null)
  const { quota } = user
  const usedPercent = quota.limit > 0 ? Math.min(100, (quota.used / quota.limit) * 100) : 100

  // Com sucesso, a sessão acaba e <RequireAuth> leva para a apresentação.
  async function onLogout() {
    setLogoutError(null)
    try {
      await logout()
    } catch (error) {
      setLogoutError(error)
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8 sm:py-12">
      <p className="eyebrow">Conta</p>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-semibold sm:text-4xl">Olá, {user.name}</h1>
        <button type="button" className="btn-secondary" onClick={onLogout} disabled={isLoggingOut}>
          {isLoggingOut ? 'Saindo…' : 'Sair da conta'}
        </button>
      </div>
      {logoutError !== null && (
        <Alert tone="error" title="Não conseguimos sair da conta" className="mt-4">
          {describeError(logoutError)} Sua sessão continua aberta neste navegador; tente de novo.
        </Alert>
      )}

      <div className="mt-6 space-y-6">
        <section aria-labelledby="dados" className="page-sheet px-5 py-6 sm:px-8">
          <h2 id="dados" className="text-xl font-semibold">
            Perfil
          </h2>
          <dl className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-[10rem_1fr]">
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

        <section aria-labelledby="cota" className="page-sheet px-5 py-6 sm:px-8">
          <h2 id="cota" className="text-xl font-semibold">
            Receitas novas de hoje
          </h2>
          <p className="mt-2">
            Você usou <strong>{quota.used}</strong> de <strong>{quota.limit}</strong>; restam{' '}
            <strong>{quota.remaining}</strong>.
          </p>
          <div
            className="mt-3 h-3 overflow-hidden rounded-full bg-paper-deep ring-1 ring-line"
            role="progressbar"
            aria-label="Cota de receitas novas usada hoje"
            aria-valuemin={0}
            aria-valuemax={quota.limit}
            aria-valuenow={quota.used}
            aria-valuetext={`${quota.used} de ${quota.limit}`}
          >
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${
                quota.remaining === 0 ? 'bg-danger' : 'bg-terracotta'
              }`}
              style={{ width: `${usedPercent}%` }}
            />
          </div>
          <p className="mt-3 text-sm text-ink-soft">
            A cota volta em {formatDateTime(quota.resets_at)}. Vídeos que já estão no Receita e
            importações que falham não contam.
          </p>
        </section>

        <ExportData />
        <DeleteAccount />
      </div>
    </div>
  )
}
