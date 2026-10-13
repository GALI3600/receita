import type { ErrorResponse, FieldError } from './types'

/** Prefixo das rotas da API: o Vite (e o proxy reverso em produção) repassa /api para o backend. */
export const API_BASE = '/api'

/** Header anti-CSRF exigido pelo backend em todo pedido que muda estado. */
export const CSRF_HEADER = 'X-Requested-With'

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

const NETWORK_ERROR_MESSAGE =
  'Não conseguimos falar com o servidor. Confira sua conexão e tente de novo.'

const FALLBACK_MESSAGES: Record<number, string> = {
  401: 'Entre na sua conta para continuar.',
  403: 'Você não tem permissão para fazer isso.',
  404: 'Não encontramos o que você procurou.',
  429: 'Muitas tentativas em pouco tempo. Espere um pouco e tente de novo.',
}

/** Erro da API no formato padrão `{"error": {"code", "message", "details?"}}`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: FieldError[]
  /** Segundos até poder tentar de novo (header Retry-After dos 429), se veio. */
  readonly retryAfter: number | null

  constructor(
    status: number,
    code: string,
    message: string,
    options: { details?: FieldError[]; retryAfter?: number | null } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = options.details
    this.retryAfter = options.retryAfter ?? null
  }
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code)
}

/** Mensagem para mostrar ao usuário a partir de qualquer erro. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Algo deu errado. Tente de novo em alguns instantes.'
}

/** Lê o Retry-After em segundos (aceita número de segundos ou data HTTP). */
export function parseRetryAfter(value: string | null, now: number = Date.now()): number | null {
  if (!value) return null
  const trimmed = value.trim()
  if (/^\d+$/.test(trimmed)) return Number(trimmed)
  const date = Date.parse(trimmed)
  if (Number.isNaN(date)) return null
  return Math.max(0, Math.ceil((date - now) / 1000))
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  if (typeof body !== 'object' || body === null || !('error' in body)) return false
  const error = (body as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

/** Converte uma resposta de erro (já sabida não-ok) em ApiError. */
export async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = parseRetryAfter(response.headers.get('Retry-After'))
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Corpo vazio ou que não é JSON (ex.: erro do proxy): usa a mensagem genérica.
  }
  if (isErrorResponse(body)) {
    return new ApiError(response.status, body.error.code, body.error.message, {
      details: body.error.details,
      retryAfter,
    })
  }
  const message =
    FALLBACK_MESSAGES[response.status] ??
    (response.status >= 500
      ? 'O servidor está com problemas. Tente de novo em alguns minutos.'
      : 'Não foi possível atender o pedido.')
  return new ApiError(response.status, `http_${response.status}`, message, { retryAfter })
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | null | undefined>
  signal?: AbortSignal
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const search = params.toString()
  return `${API_BASE}${path}${search ? `?${search}` : ''}`
}

/** Chama a API com o cookie de sessão; devolve o JSON (ou undefined em 204) ou lança ApiError. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (MUTATING_METHODS.has(method)) headers[CSRF_HEADER] = 'XMLHttpRequest'
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'same-origin',
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', NETWORK_ERROR_MESSAGE)
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}
