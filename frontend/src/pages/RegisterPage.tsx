import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useRegister } from '../api/queries'
import type { RegisterIn } from '../api/types'
import { Turnstile, type TurnstileHandle } from '../components/Turnstile'
import { Alert, AuthCard, Field } from '../components/ui'
import {
  MIN_PASSWORD,
  describeError,
  fieldErrorsFrom,
  validateEmail,
  validateNewPassword,
} from '../lib/errors'
import { TURNSTILE_SITE_KEY } from '../lib/config'
import { useDocumentTitle } from '../lib/useDocumentTitle'

type FormField = 'name' | 'email' | 'password'

const SERVER_FIELD_MESSAGES: Record<FormField, string> = {
  name: 'Informe um nome de até 100 caracteres.',
  email: 'Confira o e-mail.',
  password: `A senha precisa ter entre ${MIN_PASSWORD} e 128 caracteres.`,
}

export function RegisterPage({
  turnstileSiteKey = TURNSTILE_SITE_KEY,
}: {
  turnstileSiteKey?: string
}) {
  useDocumentTitle('Criar conta')
  const register = useRegister()
  const turnstileRef = useRef<TurnstileHandle>(null)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [captchaToken, setCaptchaToken] = useState<string | null>(null)
  const [captchaError, setCaptchaError] = useState<string | null>(null)
  const [errors, setErrors] = useState<Partial<Record<FormField, string>>>({})

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found: Partial<Record<FormField, string>> = {
      name: name.trim() ? undefined : 'Diga como podemos te chamar.',
      email: validateEmail(email) ?? undefined,
      password: validateNewPassword(password) ?? undefined,
    }
    setErrors(found)
    if (Object.values(found).some(Boolean)) return
    if (turnstileSiteKey && !captchaToken) {
      setCaptchaError('Confirme que você não é um robô.')
      return
    }
    setCaptchaError(null)
    const body: RegisterIn = { name: name.trim(), email: email.trim(), password }
    if (turnstileSiteKey && captchaToken) body['cf-turnstile-response'] = captchaToken
    register.mutate(body, {
      onError: (error) => {
        setErrors(fieldErrorsFrom(error, SERVER_FIELD_MESSAGES))
        // O token do Turnstile vale uma vez só: depois de uma tentativa, pede outro.
        turnstileRef.current?.reset()
      },
    })
  }

  if (register.isSuccess) {
    return (
      <AuthCard title="Verifique seu e-mail">
        <Alert tone="success" title="Quase lá!">
          {register.data.message}
        </Alert>
        <p className="mt-4 text-ink-soft">
          Mandamos o link para <strong className="text-ink">{email.trim()}</strong>. Se não chegar
          em alguns minutos, olhe a caixa de spam. Você já pode entrar, mas só consegue importar
          receitas depois de confirmar o e-mail.
        </p>
        <Link to="/entrar" className="btn-primary mt-6 w-full">
          Ir para a entrada
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Criar conta"
      intro="Cole links de vídeos e monte seu livro de receitas. É de graça."
    >
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {register.isError && <Alert tone="error">{describeError(register.error)}</Alert>}
        <Field
          label="Nome"
          name="name"
          autoComplete="name"
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={errors.name}
          required
        />
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
          autoComplete="new-password"
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          hint={`Pelo menos ${MIN_PASSWORD} caracteres.`}
          required
        />
        {turnstileSiteKey && (
          <div>
            <Turnstile
              ref={turnstileRef}
              siteKey={turnstileSiteKey}
              onToken={setCaptchaToken}
              onError={() =>
                setCaptchaError('Não conseguimos carregar o captcha. Recarregue a página.')
              }
            />
            {captchaError && (
              <p className="mt-1 text-sm font-semibold text-danger" role="alert">
                {captchaError}
              </p>
            )}
          </div>
        )}
        <button type="submit" className="btn-primary w-full" disabled={register.isPending}>
          {register.isPending ? 'Criando a conta…' : 'Criar conta'}
        </button>
      </form>
      <p className="mt-6 text-center text-ink-soft">
        Já tem conta?{' '}
        <Link to="/entrar" className="link">
          Entrar
        </Link>
      </p>
    </AuthCard>
  )
}
