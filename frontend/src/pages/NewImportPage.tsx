import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { isApiError } from '../api/client'
import { queryKeys, useCreateImport, useImport } from '../api/queries'
import type { ImportOut, Quota } from '../api/types'
import { ImportProgress } from '../components/ImportProgress'
import { ResendVerification } from '../components/ResendVerification'
import { Alert, Field, LoadingPage } from '../components/ui'
import { describeError } from '../lib/errors'
import { formatDateTime, validateYoutubeLink, youtubeThumbnail } from '../lib/format'
import { statusAnnouncement } from '../lib/importStatus'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useCurrentUser } from '../session/context'

const LIMIT_CODES = new Set(['quota_exceeded', 'rate_limited', 'too_many_failed_imports'])

function QuotaNote({ quota }: { quota: Quota }) {
  if (quota.remaining <= 0) {
    return (
      <Alert tone="warning" title="Você usou todas as receitas novas de hoje">
        A cota volta em {formatDateTime(quota.resets_at)}. Vídeos que já estão no Receita continuam
        liberados.
      </Alert>
    )
  }
  return (
    <p className="text-ink-soft" data-testid="quota-note">
      Hoje você ainda pode importar{' '}
      <strong className="text-ink">
        {quota.remaining} {quota.remaining === 1 ? 'receita nova' : 'receitas novas'}
      </strong>{' '}
      (de {quota.limit}). Vídeos que já estão no Receita não contam.
    </p>
  )
}

function EmailNotVerified({ emphasis }: { emphasis: boolean }) {
  const user = useCurrentUser()
  return (
    <Alert
      tone={emphasis ? 'error' : 'warning'}
      title="Confirme seu e-mail para importar receitas"
      live={emphasis ? 'assertive' : 'off'}
    >
      <p>
        Mandamos um link para <strong>{user.email}</strong>. Abra a mensagem e clique em “Confirmar
        e-mail”; depois volte aqui.
      </p>
      <ResendVerification className="mt-3" />
    </Alert>
  )
}

function VideoBadge({ imp }: { imp: ImportOut }) {
  return (
    <div className="flex items-center gap-3">
      <img
        src={youtubeThumbnail(imp.youtube_id, 'mq')}
        alt=""
        className="h-14 w-24 shrink-0 rounded object-cover shadow-cover"
      />
      <a href={imp.url} target="_blank" rel="noreferrer" className="link min-w-0 break-all text-sm">
        {imp.url}
      </a>
    </div>
  )
}

function ImportStatusView({ imp, onReset }: { imp: ImportOut; onReset: () => void }) {
  if (imp.status === 'failed') {
    return (
      <div className="space-y-5">
        <VideoBadge imp={imp} />
        <Alert tone="error" title="Não conseguimos importar esse vídeo">
          {imp.error?.message || 'Algo deu errado ao processar o vídeo.'}
        </Alert>
        <button type="button" className="btn-primary" onClick={onReset}>
          Tentar outro link
        </button>
      </div>
    )
  }
  if (imp.status === 'deferred') {
    return (
      <div className="space-y-5">
        <VideoBadge imp={imp} />
        <Alert tone="warning" title="Importação adiada">
          <p>{imp.error?.message || 'Sua receita vai ser escrita mais tarde.'}</p>
          <p className="mt-2">
            Pode fechar esta página: quando ficar pronta, a receita aparece no seu livro.
          </p>
        </Alert>
        <button type="button" className="btn-secondary" onClick={onReset}>
          Importar outro vídeo
        </button>
      </div>
    )
  }
  if (imp.status === 'done') return <LoadingPage label="Receita pronta! Abrindo…" />
  return (
    <div className="space-y-6">
      <VideoBadge imp={imp} />
      <ImportProgress imp={imp} />
      <p className="text-sm text-ink-soft">
        Isso leva de alguns segundos a poucos minutos. Pode sair desta página: a receita vai para o
        seu livro quando ficar pronta.
      </p>
    </div>
  )
}

export function NewImportPage() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const importId = params.get('import')
  const create = useCreateImport()
  const current = useImport(importId)
  const [url, setUrl] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)

  const imp = current.data
  useDocumentTitle(imp && importId ? statusAnnouncement(imp) : 'Nova receita')

  useEffect(() => {
    if (!imp) return
    if (imp.status === 'done' && imp.recipe_id) {
      void client.invalidateQueries({ queryKey: queryKeys.recipes })
      void client.invalidateQueries({ queryKey: queryKeys.me })
      navigate(`/receitas/${imp.recipe_id}`, { replace: true, state: { imported: true } })
    } else if (imp.status === 'failed') {
      // Falhas não gastam a cota: atualiza o "ainda pode importar".
      void client.invalidateQueries({ queryKey: queryKeys.me })
    }
  }, [imp, client, navigate])

  function reset() {
    create.reset()
    setUrl('')
    setParams({}, { replace: false })
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const problem = validateYoutubeLink(url)
    setFieldError(problem)
    if (problem) return
    create.mutate(url.trim(), {
      onSuccess: (created) => {
        if (created.status === 'done' && created.recipe_id) {
          navigate(`/receitas/${created.recipe_id}`, { state: { imported: true } })
        } else {
          // O id vai para a URL: recarregar a página continua acompanhando o mesmo import.
          setParams({ import: created.id })
        }
      },
      onError: (error) => {
        if (isApiError(error, 'invalid_url') || isApiError(error, 'validation_error')) {
          setFieldError(error.message)
        }
      },
    })
  }

  const createError = create.error
  const notVerifiedError = isApiError(createError, 'email_not_verified')
  const limitError =
    createError !== null && isApiError(createError) && LIMIT_CODES.has(createError.code)
  const showGenericError =
    createError !== null &&
    !notVerifiedError &&
    !isApiError(createError, 'invalid_url') &&
    !isApiError(createError, 'validation_error')

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8 sm:py-12">
      <p className="eyebrow">Nova receita</p>
      <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">
        {importId ? 'Preparando sua receita' : 'Cole o link do vídeo'}
      </h1>

      <div className="page-sheet mt-6 px-5 py-6 sm:px-8 sm:py-8">
        {importId ? (
          current.isPending ? (
            <LoadingPage label="Carregando a importação…" />
          ) : current.isError ? (
            <div className="space-y-4">
              <Alert tone="error">{describeError(current.error)}</Alert>
              <button type="button" className="btn-primary" onClick={reset}>
                Importar outro vídeo
              </button>
            </div>
          ) : (
            <ImportStatusView imp={current.data} onReset={reset} />
          )
        ) : (
          <div className="space-y-5">
            {!user.email_verified && <EmailNotVerified emphasis={notVerifiedError} />}
            {user.email_verified && notVerifiedError && <EmailNotVerified emphasis />}
            <form noValidate onSubmit={onSubmit} className="space-y-4">
              <Field
                label="Link do vídeo no YouTube"
                name="url"
                type="url"
                inputMode="url"
                autoComplete="off"
                placeholder="https://www.youtube.com/watch?v=…"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value)
                  if (fieldError) setFieldError(null)
                }}
                error={fieldError}
                hint="Funciona com links do youtube.com, youtu.be e Shorts."
                required
              />
              {showGenericError && (
                <Alert tone={limitError ? 'warning' : 'error'}>{describeError(createError)}</Alert>
              )}
              <button
                type="submit"
                className="btn-primary w-full sm:w-auto"
                disabled={create.isPending}
              >
                {create.isPending ? 'Enviando…' : 'Importar receita'}
              </button>
            </form>
            <QuotaNote quota={user.quota} />
          </div>
        )}
      </div>

      <p className="mt-6 text-center">
        <Link to="/livro" className="link">
          Voltar para o livro
        </Link>
      </p>
    </div>
  )
}
