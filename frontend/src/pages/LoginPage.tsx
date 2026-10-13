import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useLogin } from '../api/queries'
import { Alert, AuthCard, Field } from '../components/ui'
import { describeError, validateEmail } from '../lib/errors'
import { safeNext } from '../lib/navigation'
import { useDocumentTitle } from '../lib/useDocumentTitle'

export function LoginPage() {
  useDocumentTitle('Entrar')
  const [params] = useSearchParams()
  const next = params.get('next')
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({})

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = {
      email: validateEmail(email) ?? undefined,
      password: password ? undefined : 'Informe sua senha.',
    }
    setErrors(found)
    if (found.email || found.password) return
    // Com sucesso, a sessão muda e <RedirectIfAuthenticated> leva para o `next` (ou o livro).
    login.mutate({ email: email.trim(), password })
  }

  const cameFromProtected = next !== null && safeNext(next, '') !== ''

  return (
    <AuthCard
      title="Entrar"
      intro={cameFromProtected ? 'Entre na sua conta para continuar.' : 'Bom te ver de volta.'}
    >
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {login.isError && <Alert tone="error">{describeError(login.error)}</Alert>}
        <Field
          label="E-mail"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          required
        />
        <Field
          label="Senha"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          required
        />
        <button type="submit" className="btn-primary w-full" disabled={login.isPending}>
          {login.isPending ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
      <div className="mt-6 space-y-2 text-center">
        <p>
          <Link to="/esqueci-senha" className="link">
            Esqueci minha senha
          </Link>
        </p>
        <p className="text-ink-soft">
          Ainda não tem conta?{' '}
          <Link
            to={next ? `/cadastro?next=${encodeURIComponent(next)}` : '/cadastro'}
            className="link"
          >
            Criar conta
          </Link>
        </p>
      </div>
    </AuthCard>
  )
}
