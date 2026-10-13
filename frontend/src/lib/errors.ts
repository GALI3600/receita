import { ApiError, errorMessage } from '../api/client'
import { formatWait } from './format'

/** Mensagem do backend e, num 429 com Retry-After, quanto falta para tentar de novo. */
export function describeError(error: unknown): string {
  const message = errorMessage(error)
  if (error instanceof ApiError && error.status === 429 && error.retryAfter) {
    return `${message} Você poderá tentar de novo em ${formatWait(error.retryAfter)}.`
  }
  return message
}

/**
 * Erros de validação (422) por campo, com as mensagens do formulário em português.
 * `messages` traduz o nome do campo (sem o prefixo "body.") para o texto mostrado.
 */
export function fieldErrorsFrom<F extends string>(
  error: unknown,
  messages: Record<F, string>,
): Partial<Record<F, string>> {
  const result: Partial<Record<F, string>> = {}
  if (!(error instanceof ApiError) || !error.details) return result
  for (const detail of error.details) {
    const field = detail.field.replace(/^body\./, '') as F
    if (field in messages) result[field] = messages[field]
  }
  return result
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateEmail(value: string): string | null {
  if (!value.trim()) return 'Informe seu e-mail.'
  if (!EMAIL_RE.test(value.trim())) return 'Confira o e-mail: ele parece incompleto.'
  return null
}

export const MIN_PASSWORD = 8
export const MAX_PASSWORD = 128

export function validateNewPassword(value: string): string | null {
  if (value.length < MIN_PASSWORD)
    return `A senha precisa ter pelo menos ${MIN_PASSWORD} caracteres.`
  if (value.length > MAX_PASSWORD) return `A senha pode ter no máximo ${MAX_PASSWORD} caracteres.`
  return null
}
