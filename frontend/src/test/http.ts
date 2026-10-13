import { vi } from 'vitest'

export interface RecordedRequest {
  method: string
  path: string
  query: URLSearchParams
  headers: Headers
  body: unknown
  credentials: RequestCredentials | undefined
}

type Handler = (request: RecordedRequest) => Response | Promise<Response>

export function json(status: number, body?: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

export function apiError(
  status: number,
  code: string,
  message: string,
  headers: Record<string, string> = {},
) {
  return json(status, { error: { code, message } }, headers)
}

/**
 * Troca o fetch global por rotas falsas ("GET /api/auth/me": handler). Um handler pode ser uma
 * lista: cada chamada usa o próximo, e o último se repete. Devolve os pedidos recebidos.
 */
export function mockApi(routes: Record<string, Handler | Handler[]>) {
  const calls: RecordedRequest[] = []
  const counters = new Map<string, number>()
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), 'http://localhost')
    const method = (init.method ?? 'GET').toUpperCase()
    const request: RecordedRequest = {
      method,
      path: url.pathname,
      query: url.searchParams,
      headers: new Headers(init.headers),
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
      credentials: init.credentials,
    }
    calls.push(request)
    const key = `${method} ${url.pathname}`
    const route = routes[key]
    if (!route) return apiError(404, 'not_found', `rota não simulada: ${key}`)
    if (Array.isArray(route)) {
      const index = counters.get(key) ?? 0
      counters.set(key, index + 1)
      return route[Math.min(index, route.length - 1)](request)
    }
    return route(request)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}
