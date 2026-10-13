import { apiFetch } from './client'
import type {
  ImportOut,
  LoginIn,
  Me,
  MessageOut,
  Recipe,
  RecipeFilters,
  RecipePage,
  RecipeTags,
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
  tags: (signal?: AbortSignal) => apiFetch<RecipeTags>('/recipes/tags', { signal }),
  get: (id: string, signal?: AbortSignal) =>
    apiFetch<Recipe>(`/recipes/${encodeURIComponent(id)}`, { signal }),
  update: (id: string, body: RecipeUpdate) =>
    apiFetch<Recipe>(`/recipes/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
  remove: (id: string) =>
    apiFetch<void>(`/recipes/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  reset: (id: string) =>
    apiFetch<Recipe>(`/recipes/${encodeURIComponent(id)}/reset`, { method: 'POST' }),
}

export const accountApi = {
  /** Todos os dados da conta (LGPD), para baixar como arquivo JSON. */
  export: () => apiFetch<unknown>('/account/export'),
  remove: (password: string) =>
    apiFetch<void>('/account', { method: 'DELETE', body: { password } }),
}

/** Nome do arquivo baixado (o mesmo do Content-Disposition do backend). */
export const ACCOUNT_EXPORT_FILENAME = 'receita-meus-dados.json'
