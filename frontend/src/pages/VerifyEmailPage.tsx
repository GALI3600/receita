import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useVerifyEmail } from '../api/queries'
import { ResendVerification } from '../components/ResendVerification'
import { Alert, AuthCard, Spinner } from '../components/ui'
import { describeError } from '../lib/errors'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useSession } from '../session/context'

function ResendOrLogin() {
  const { status, user } = useSession()
  if (status === 'authenticated' && user) {
    if (user.email_verified) {
      return (
        <p className="mt-4">
          Seu e-mail já está confirmado.{' '}
          <Link to="/nova" className="link">
            Importar uma receita
          </Link>
        </p>
      )
    }
    return (
      <div className="mt-4">
        <p className="text-ink-soft">
          Precisa de um link novo? Enviamos para <strong className="text-ink">{user.email}</strong>.
        </p>
        <ResendVerification className="mt-3" />
      </div>
    )
  }
  return (
    <p className="mt-4 text-ink-soft">
      Para pedir um link novo,{' '}
      <Link to="/entrar?next=%2Fverificar-email" className="link">
        entre na sua conta
      </Link>
      .
    </p>
  )
}

export function VerifyEmailPage() {
  useDocumentTitle('Confirmar e-mail')
  const [params] = useSearchParams()
  const token = params.get('token')
  const verify = useVerifyEmail()
  const { status } = useSession()
  const requested = useRef<string | null>(null)

  useEffect(() => {
    // Uma chamada por token (o StrictMode roda o efeito duas vezes em desenvolvimento).
    if (!token || requested.current === token) return
    requested.current = token
    verify.mutate(token)
  }, [token, verify])

  if (!token) {
    return (
      <AuthCard title="Confirme seu e-mail">
        <p className="text-ink-soft">
          Mandamos um link de confirmação para o seu e-mail. Abra a mensagem e clique em “Confirmar
          e-mail” para começar a importar receitas.
        </p>
        <ResendOrLogin />
      </AuthCard>
    )
  }

  if (verify.isError) {
    return (
      <AuthCard title="Não deu para confirmar">
        <Alert tone="error">{describeError(verify.error)}</Alert>
        <ResendOrLogin />
      </AuthCard>
    )
  }

  if (verify.isSuccess) {
    return (
      <AuthCard title="E-mail confirmado!">
        <Alert tone="success">Tudo certo. Agora é só colar o link de um vídeo de receita.</Alert>
        <Link
          to={status === 'authenticated' ? '/nova' : '/entrar?next=%2Fnova'}
          className="btn-primary mt-6 w-full"
        >
          {status === 'authenticated' ? 'Importar minha primeira receita' : 'Entrar'}
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Confirmando seu e-mail">
      <p className="flex items-center justify-center gap-3 text-ink-soft" role="status">
        <Spinner /> Só um instante…
      </p>
    </AuthCard>
  )
}
