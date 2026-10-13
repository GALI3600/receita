import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useForgotPassword } from '../api/queries'
import { Alert, AuthCard, Field } from '../components/ui'
import { describeError, validateEmail } from '../lib/errors'
import { useDocumentTitle } from '../lib/useDocumentTitle'

export function ForgotPasswordPage() {
  useDocumentTitle('Esqueci minha senha')
  const forgot = useForgotPassword()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = validateEmail(email)
    setError(found)
    if (!found) forgot.mutate(email.trim())
  }

  if (forgot.isSuccess) {
    return (
      <AuthCard title="Confira seu e-mail">
        <Alert tone="success">{forgot.data.message}</Alert>
        <p className="mt-4 text-ink-soft">
          O link vale por pouco tempo e só pode ser usado uma vez.
        </p>
        <Link to="/entrar" className="btn-secondary mt-6 w-full">
          Voltar para a entrada
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Esqueci minha senha"
      intro="Informe o e-mail da sua conta e mandamos um link para criar uma senha nova."
    >
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {forgot.isError && <Alert tone="error">{describeError(forgot.error)}</Alert>}
        <Field
          label="E-mail"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={error}
          required
        />
        <button type="submit" className="btn-primary w-full" disabled={forgot.isPending}>
          {forgot.isPending ? 'Enviando…' : 'Enviar o link'}
        </button>
      </form>
      <p className="mt-6 text-center">
        <Link to="/entrar" className="link">
          Voltar para a entrada
        </Link>
      </p>
    </AuthCard>
  )
}
