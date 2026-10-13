import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { isApiError } from '../api/client'
import { useResetPassword } from '../api/queries'
import { Alert, AuthCard, Field } from '../components/ui'
import { MIN_PASSWORD, describeError, validateNewPassword } from '../lib/errors'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { useTokenFromUrl } from '../lib/useTokenFromUrl'

export function ResetPasswordPage() {
  useDocumentTitle('Nova senha')
  const token = useTokenFromUrl()
  const reset = useResetPassword()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({})

  if (!token) {
    return (
      <AuthCard title="Link incompleto">
        <Alert tone="error">
          Este endereço não tem o código de redefinição. Abra o link do e-mail de novo ou peça
          outro.
        </Alert>
        <Link to="/esqueci-senha" className="btn-primary mt-6 w-full">
          Pedir um link novo
        </Link>
      </AuthCard>
    )
  }

  if (reset.isSuccess) {
    return (
      <AuthCard title="Senha alterada">
        <Alert tone="success">
          Pronto! Por segurança, encerramos as sessões abertas. Entre com a senha nova.
        </Alert>
        <Link to="/entrar" className="btn-primary mt-6 w-full">
          Entrar
        </Link>
      </AuthCard>
    )
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = {
      password: validateNewPassword(password) ?? undefined,
      confirm: password === confirm ? undefined : 'As duas senhas não são iguais.',
    }
    setErrors(found)
    if (!found.password && !found.confirm && token) reset.mutate({ token, password })
  }

  const invalidToken = isApiError(reset.error, 'invalid_token')

  return (
    <AuthCard title="Escolha uma senha nova">
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {reset.isError && (
          <Alert tone="error">
            {describeError(reset.error)}{' '}
            {invalidToken && (
              <Link to="/esqueci-senha" className="link">
                Pedir um link novo
              </Link>
            )}
          </Alert>
        )}
        <Field
          label="Senha nova"
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
        <Field
          label="Repita a senha nova"
          type="password"
          name="confirm"
          autoComplete="new-password"
          maxLength={128}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
          required
        />
        <button type="submit" className="btn-primary w-full" disabled={reset.isPending}>
          {reset.isPending ? 'Salvando…' : 'Salvar a senha nova'}
        </button>
      </form>
    </AuthCard>
  )
}
