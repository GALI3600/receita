import { apiFetch } from './client'
import type {
  ImportOut,
  LoginIn,
  Me,
  MessageOut,
  Recipe,
  RecipeFilters,
  RecipePage,
  RecipeUpdate,
  RegisterIn,
} from './types'

export const RECIPES_PAGE_SIZE = 24

export const authApi = {
  me: (signal?: AbortSignal) => apiFetch<Me>('/auth/me', { signal }),
  register: (body: RegisterIn) => apiFetch<MessageOut>('/auth/register', { method: 'POST', body }),
  login: (body: LoginIn) => apiFetch<Me>('/auth/login', { method: 'POST', body }),
  logout: () => apiFetch<void>('/auth/logout', { method: 'POST' }),
  verify: (token: string) => apiFetch<void>('/auth/verify', { method: 'POST', body: { token } }),
  resendVerification: () => apiFetch<MessageOut>('/auth/resend-verification', { method: 'POST' }),
  forgotPassword: (email: string) =>
    apiFetch<MessageOut>('/auth/forgot-password', { method: 'POST', body: { email } }),
  resetPassword: (token: string, password: string) =>
    apiFetch<void>('/auth/reset-password', { method: 'POST', body: { token, password } }),
}

export const importsApi = {
  create: (url: string) => apiFetch<ImportOut>('/imports', { method: 'POST', body: { url } }),
  get: (id: string, signal?: AbortSignal) =>
    apiFetch<ImportOut>(`/imports/${encodeURIComponent(id)}`, { signal }),
}

export const recipesApi = {
  list: (filters: RecipeFilters, cursor?: string | null, signal?: AbortSignal) =>
    apiFetch<RecipePage>('/recipes', {
      query: {
        q: filters.q?.trim(),
        tag: filters.tag,
        favorite: filters.favorite ? true : undefined,
        limit: RECIPES_PAGE_SIZE,
        cursor,
      },
      signal,
    }),
  get: (id: string, signal?: AbortSignal) =>
    apiFetch<Recipe>(`/recipes/${encodeURIComponent(id)}`, { signal }),
  update: (id: string, body: RecipeUpdate) =>
    apiFetch<Recipe>(`/recipes/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
  remove: (id: string) =>
    apiFetch<void>(`/recipes/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}

/** Link de download dos dados da conta (GET simples, o cookie vai junto). */
export const ACCOUNT_EXPORT_URL = '/api/account/export'
