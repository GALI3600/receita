import { describe, expect, it } from 'vitest'

import { apiError, json, mockApi } from '../test/http'
import { ApiError, apiFetch, buildUrl, errorMessage, parseRetryAfter, toApiError } from './client'

describe('apiFetch', () => {
  it('envia o cookie (same-origin) e não manda o header anti-CSRF em GET', async () => {
    const { calls } = mockApi({ 'GET /api/auth/me': () => json(200, { id: 'u1' }) })

    await expect(apiFetch('/auth/me')).resolves.toEqual({ id: 'u1' })

    expect(calls[0].credentials).toBe('same-origin')
    expect(calls[0].headers.has('X-Requested-With')).toBe(false)
  })

  it.each(['POST', 'PATCH', 'DELETE'] as const)('manda X-Requested-With em %s', async (method) => {
    const { calls } = mockApi({ [`${method} /api/recipes/r1`]: () => json(200, {}) })

    await apiFetch('/recipes/r1', { method, body: method === 'DELETE' ? undefined : { a: 1 } })

    expect(calls[0].headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    if (method !== 'DELETE') {
      expect(calls[0].headers.get('Content-Type')).toBe('application/json')
      expect(calls[0].body).toEqual({ a: 1 })
    }
  })

  it('devolve undefined em 204', async () => {
    mockApi({ 'POST /api/auth/logout': () => new Response(null, { status: 204 }) })
    await expect(apiFetch('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
  })

  it('transforma o erro padrão em ApiError com code, message, status e retryAfter', async () => {
    mockApi({
      'POST /api/imports': () =>
        apiError(429, 'quota_exceeded', 'Você chegou ao limite de hoje.', {
          'Retry-After': '3600',
        }),
    })

    const error = await apiFetch('/imports', { method: 'POST', body: { url: 'x' } }).catch(
      (e: unknown) => e,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 429,
      code: 'quota_exceeded',
      message: 'Você chegou ao limite de hoje.',
      retryAfter: 3600,
    })
  })

  it('mantém os detalhes dos erros de validação', async () => {
    const details = [{ field: 'body.email', type: 'value_error', message: 'invalid' }]
    mockApi({
      'POST /api/auth/register': () =>
        json(422, { error: { code: 'validation_error', message: 'Dados inválidos.', details } }),
    })

    const error = (await apiFetch('/auth/register', { method: 'POST', body: {} }).catch(
      (e: unknown) => e,
    )) as ApiError

    expect(error.code).toBe('validation_error')
    expect(error.details).toEqual(details)
  })

  it('usa uma mensagem em português quando o corpo não é o erro padrão', async () => {
    mockApi({ 'GET /api/recipes': () => new Response('<html>Bad Gateway</html>', { status: 502 }) })

    const error = (await apiFetch('/recipes').catch((e: unknown) => e)) as ApiError

    expect(error.status).toBe(502)
    expect(error.code).toBe('http_502')
    expect(error.message).toMatch(/servidor está com problemas/)
  })

  it('falha de rede vira ApiError network_error', async () => {
    mockApi({
      'GET /api/auth/me': () => {
        throw new TypeError('Failed to fetch')
      },
    })

    const error = (await apiFetch('/auth/me').catch((e: unknown) => e)) as ApiError

    expect(error.status).toBe(0)
    expect(error.code).toBe('network_error')
    expect(errorMessage(error)).toMatch(/conexão/)
  })
})

describe('buildUrl', () => {
  it('prefixa /api e ignora parâmetros vazios', () => {
    expect(
      buildUrl('/recipes', { q: 'bolo de milho', tag: '', favorite: true, cursor: null }),
    ).toBe('/api/recipes?q=bolo+de+milho&favorite=true')
  })
})

describe('parseRetryAfter', () => {
  it('lê segundos e datas HTTP', () => {
    expect(parseRetryAfter('120')).toBe(120)
    expect(parseRetryAfter(null)).toBeNull()
    expect(parseRetryAfter('amanhã')).toBeNull()
    const now = Date.parse('2026-10-13T10:00:00Z')
    expect(parseRetryAfter('Tue, 13 Oct 2026 10:01:30 GMT', now)).toBe(90)
  })
})

describe('toApiError', () => {
  it('não quebra com corpo vazio', async () => {
    const error = await toApiError(new Response(null, { status: 401 }))
    expect(error.message).toBe('Entre na sua conta para continuar.')
  })
})
